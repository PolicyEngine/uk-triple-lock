"""The checks behind the working paper's /paper route fail what they should.

tests/test_paper.py checks that the real wrapper and workflow pass. These tests check the other side, so that a later
edit cannot drop a rule while CI stays green: dashboard/scripts/paper_links.py rejects each kind of wrapper it cannot
follow, check-paper-route.sh fails a loop, a wrong redirect, a missing file or the wrong bytes, and check-built-app.sh
fails when the server or the route check fails. The script tests run bash and curl against local stand-ins for the
app (both are on CI's ubuntu-latest).
"""

import re
import shutil
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
SCRIPTS = DASHBOARD / "scripts"
sys.path.insert(0, str(SCRIPTS))

import paper_links as L  # noqa: E402

WRAPPER = (DASHBOARD / "public" / "paper" / "index.html").read_text()
IFRAME = '<iframe src="/uk/triple-lock/paper/web/index.html?v='
VERSION = re.search(r'index\.html\?v=([^"]+)"', WRAPPER).group(1)
LOGO = f'src="{L.LOGO}"'
PDF = f'href="{L.PDF}"'
MAIN = '<main class="wrap">'
STYLE_END = "</style>"


def wrapper_with(old, new):
    assert old in WRAPPER, f"update this case: {old!r} is no longer in the wrapper"
    return WRAPPER.replace(old, new, 1)


# (what, text in the wrapper, replacement): each makes a wrapper the checks cannot vouch for.
REJECTED = [
    ("a relative logo", LOGO, "src='assets/missing.svg'"),
    ("a relative PDF link", PDF, 'href = "web/index.pdf"'),
    ("a missing dashboard link", '<a href="/uk/triple-lock">Live dashboard</a>', ""),
    ("one logo", LOGO, 'src="https://policyengine.org/logo.svg"'),
    ("no back-to-top link", '<a href="#paper-top">', '<a href="/uk/triple-lock">'),
    ("a fragment naming no element", '<a href="#paper-top">', '<a href="#nowhere">'),
    ("two manuscript versions", "?v=", "?v=other-"),
    ("an http link", 'href="https://policyengine.org/uk/research"', 'href="http://example.com/"'),
    ("an absolute URL into the zone", LOGO, 'src="https://policyengine.org/uk/triple-lock/assets/logos/x.svg"'),
    ("an upper-case absolute URL into the zone", PDF, 'href="https://policyengine.org/UK/Triple-Lock/x.pdf"'),
    ("an encoded slash into the zone", PDF, 'href="https://policyengine.org/uk/triple-lock%2Fx.pdf"'),
    ("a dot segment in an absolute URL", PDF, 'href="https://policyengine.org/uk/x/../triple-lock/x.pdf"'),
    ("an empty segment in an absolute URL", PDF, 'href="https://policyengine.org//uk/triple-lock/x.pdf"'),
    ("a trailing slash", PDF, 'href="/uk/triple-lock/paper/web/"'),
    ("a dot segment", PDF, 'href="/uk/triple-lock/paper/./web/index.pdf"'),
    ("a percent-encoded dot segment", PDF, 'href="/uk/triple-lock/paper/%2e%2e/web/index.pdf"'),
    ("a backslash", PDF, 'href="/uk/triple-lock/paper\\web/index.pdf"'),
    ("brackets in a query", PDF, 'href="/uk/triple-lock/paper/web/index.pdf?x=[abc]"'),
    ("a tab in a URL", PDF, 'href="/uk/triple-lock/paper/web/index.p\tdf"'),
    ("a file type with no expected content type", PDF, 'href="/uk/triple-lock/data/results.json"'),
    ("srcset", 'alt="PolicyEngine">', f'srcset="{L.LOGO}?a=1,2 2x" alt="PolicyEngine">'),
    ("ping", '<a href="#paper-top">', '<a href="#paper-top" ping="web/broken">'),
    ("an svg image href", MAIN, MAIN + '<svg><image href="/uk/triple-lock/x.svg"/></svg>'),
    ("an area href", MAIN, MAIN + f'<map><area href="{L.PDF}"></map>'),
    ("an event handler", '<a href="/uk/triple-lock">', '<a href="/uk/triple-lock" onclick="location=\'x\'">'),
    ("a script", MAIN, MAIN + "<script>fetch('x')</script>"),
    ("a template", IFRAME, "<template>" + IFRAME),
    ("a noscript", MAIN, MAIN + f"<noscript><img {LOGO}></noscript>"),
    ("the hidden attribute", '<a href="#paper-top">', '<a hidden href="#paper-top">'),
    ("a base element", '<meta charset="utf-8">', '<meta charset="utf-8"><base href="/uk/triple-lock/paper/">'),
    ("a meta refresh", '<meta charset="utf-8">',
     '<meta charset="utf-8"><meta http-equiv="Refresh" content="0; url=/x">'),
    ("an iframe srcdoc", 'loading="lazy"', 'loading="lazy" srcdoc="<p>x</p>"'),
    ("a meta content URL into the zone", '<meta property="og:type"',
     '<meta property="og:image" content="https://policyengine.org/uk/triple-lock/x.png"><meta property="og:type"'),
    ("CSS url() in upper case", STYLE_END, "a { background: URL(web/missing.svg) }" + STYLE_END),
    ("CSS @import after a comment", "<style>", '<style>@import/**/"web/missing.css";'),
    ("CSS url() inside a comment", STYLE_END, "/* url(web/missing.svg) */" + STYLE_END),
    ("CSS image-set()", STYLE_END, "a { background: image-set('x.png' 1x) }" + STYLE_END),
    ("a CSS escape", STYLE_END, "a { background: u\\72l(x.png) }" + STYLE_END),
    ("CSS url() in a style attribute", MAIN, '<main class="wrap" style="background: url(bg.png)">'),
    ("a self-closing iframe", 'referrerpolicy="same-origin"></iframe>', 'referrerpolicy="same-origin" />'),
    ("a repeated src", IFRAME, '<iframe src="https://policyengine.org/uk/research" ' + IFRAME[len("<iframe "):]),
    ("a repeated sandbox", 'sandbox="allow', 'sandbox="" sandbox="allow'),
    ("CDATA", MAIN, MAIN + '<![CDATA[ <a href="web/broken.pdf">x</a> ]]>'),
    ("svg content", MAIN, MAIN + "<svg><style>a{}</style></svg>"),
    ("an HTML comment", MAIN, MAIN + "<!-- x -->"),
    ("a processing instruction", MAIN, MAIN + "<?x y?>"),
    ("xmp", MAIN, MAIN + "<xmp>x</xmp>"),
]

# Equivalent markup the checks must still accept.
ACCEPTED = [
    ("a single-quoted iframe src", f'{IFRAME}{VERSION}"', f"<iframe src='{L.MANUSCRIPT}?v={VERSION}'"),
    ("an unquoted loading attribute", 'loading="lazy"', "loading=lazy"),
    ("reordered sandbox tokens", "allow-same-origin allow-scripts", "allow-scripts allow-same-origin"),
    ("the canonical address in a link", '<a href="https://github.com/PolicyEngine/uk-triple-lock">',
     f'<a href="{L.CANONICAL}">x</a><a href="https://github.com/PolicyEngine/uk-triple-lock">'),
    ("an image outside the zone in meta", '<meta property="og:type"',
     '<meta property="og:image" content="https://policyengine.org/images/x.png"><meta property="og:type"'),
    ("a self-closing void element", MAIN, MAIN + "<br/>"),
]


@pytest.mark.parametrize("what, old, new", REJECTED, ids=[case[0] for case in REJECTED])
def test_paper_links_rejects(what, old, new):
    problems, _ = L.check_wrapper(wrapper_with(old, new))
    assert problems, f"{what} passed the wrapper rules"


@pytest.mark.parametrize("what, old, new", ACCEPTED, ids=[case[0] for case in ACCEPTED])
def test_paper_links_accepts(what, old, new):
    problems, _ = L.check_wrapper(wrapper_with(old, new))
    assert not problems, problems


def dashboard_page(title, script=f"{L.BASE}/_next/static/chunks/main.js"):
    return f'<html><head><title>{title}</title><script src="{script}"></script></head><body>Loading...</body></html>'


def test_is_dashboard():
    layout = (DASHBOARD / "app" / "layout.jsx").read_text()
    title = re.search(r'\btitle:\s*"([^"]+)"', layout).group(1)
    assert L.is_dashboard(dashboard_page(title), layout)
    assert not L.is_dashboard(dashboard_page("Another app"), layout)
    assert not L.is_dashboard(dashboard_page(title, "/_next/static/chunks/main.js"), layout)
    assert not L.is_dashboard(dashboard_page(title).replace("</head>", "<title>x</title></head>"), layout)


# ── check-paper-route.sh against a stand-in server ──────────────────────


def public_copy(tmp_path):
    """The checked-in files the wrapper serves, copied so a test cannot change them."""
    public = tmp_path / "public"
    _, local = L.check_wrapper(WRAPPER)
    for file in {"paper/index.html"} | {file for _, _, file in local if file}:
        (public / file).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(DASHBOARD / "public" / file, public / file)
    return public


def stand_in(mode, public):
    """A server answering as the app would, broken in the way MODE names."""
    layout = (DASHBOARD / "app" / "layout.jsx").read_text()
    dashboard = dashboard_page(re.search(r'\btitle:\s*"([^"]+)"', layout).group(1)).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, ctype=None, body=b"", location=None, length=None):
            self.send_response(code)
            if ctype:
                self.send_header("Content-Type", ctype)
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Length", str(len(body) if length is None else length))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            html = "text/html ; charset=UTF-8" if mode == "spaced type" else "text/html; charset=utf-8"
            if path == L.PAPER:
                if mode == "loop":
                    return self.reply(308, location=L.PAPER + "/")
                body = (public / "paper/index.html").read_bytes()
                return self.reply(200, html, body + (b"\n" if mode == "changed wrapper" else b""))
            if path == L.PAPER + "/":
                if mode == "200 at the slash":
                    return self.reply(200, html, (public / "paper/index.html").read_bytes())
                return self.reply(308, location=L.BASE + "/" if mode == "wrong target" else L.PAPER)
            if path == L.BASE:
                return self.reply(200, html, b"<html><title>x</title></html>" if mode == "other page" else dashboard)
            file = public / path[len(L.BASE) + 1:]
            if not path.startswith(L.BASE + "/") or not file.is_file() or (mode == "missing logo" and path == L.LOGO):
                return self.reply(404, "text/html", b"not found")
            body = file.read_bytes()
            ctype = L.content_type(path)
            if path == L.PDF and mode == "PDF as HTML":
                return self.reply(200, html, b"<html>app shell</html>")
            if path == L.PDF and mode == "truncated PDF":
                return self.reply(200, ctype, body[:1000], length=len(body))
            if path == L.PDF and mode == "PDF stub":
                return self.reply(200, ctype, b"%PDF-")
            if path == L.LOGO and mode == "commented SVG":
                return self.reply(200, ctype, b"<!-- <svg -->")
            if path == L.MANUSCRIPT and mode == "changed manuscript":
                body += b"\n"
            if mode == "upper-case type" and ctype != "text/html":
                ctype = ctype.upper()
            return self.reply(200, ctype if ctype != "text/html" else html, body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run_route_check(mode, tmp_path):
    public = public_copy(tmp_path)
    server = stand_in(mode, public)
    try:
        origin = f"http://127.0.0.1:{server.server_address[1]}"
        return subprocess.run(["bash", str(SCRIPTS / "check-paper-route.sh"), origin, str(public)],
                              capture_output=True, text=True, timeout=180)
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("mode", ["working", "upper-case type", "spaced type"])
def test_route_check_passes_a_working_app(mode, tmp_path):
    result = run_route_check(mode, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


BROKEN = {
    "loop": "/paper gave 308",
    "200 at the slash": "/paper/ gave 200",
    "wrong target": "not 308 to",
    "missing logo": "policyengine-white.svg gave 404",
    "PDF as HTML": "index.pdf came as",
    "truncated PDF": "curl exited 18",
    "PDF stub": "index.pdf is not public/paper/web/index.pdf",
    "commented SVG": "policyengine-white.svg is not public/",
    "changed manuscript": "is not public/paper/web/index.html",
    "changed wrapper": "/paper is not public/paper/index.html",
    "other page": "is not this app's dashboard page",
}


@pytest.mark.parametrize("mode", BROKEN)
def test_route_check_fails_a_broken_app(mode, tmp_path):
    result = run_route_check(mode, tmp_path)
    assert result.returncode != 0 and BROKEN[mode] in result.stderr, result.stdout + result.stderr


# ── check-built-app.sh with a stand-in `next start` and route check ─────

PORT = 3123  # check-built-app.sh's port


def port_open():
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def run_built_app_check(tmp_path, next_body, route_rc=0):
    scripts = tmp_path / "dashboard" / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy(SCRIPTS / "check-built-app.sh", scripts)
    args = tmp_path / "route-args"
    (scripts / "check-paper-route.sh").write_text(f'printf "%s\\n" "$@" > "{args}"\nexit {route_rc}\n')
    next_bin = tmp_path / "dashboard" / "node_modules" / ".bin" / "next"
    next_bin.parent.mkdir(parents=True)
    next_bin.write_text("#!/usr/bin/env bash\n" + next_body + "\n")
    next_bin.chmod(0o755)
    result = subprocess.run(["bash", "scripts/check-built-app.sh"], cwd=tmp_path / "dashboard",
                            capture_output=True, text=True, timeout=180)
    return result, args


SERVE = f"""exec "{sys.executable}" -I -c '
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Length", "0"); self.end_headers()
    def log_message(self, *args):
        pass
HTTPServer(("127.0.0.1", {PORT}), H).serve_forever()'"""


@pytest.fixture
def free_port():
    assert not port_open(), f"port {PORT} is in use; check-built-app.sh needs it"
    yield
    assert not port_open(), "check-built-app.sh left its server running"


def test_built_app_check_runs_the_route_check(tmp_path, free_port):
    result, args = run_built_app_check(tmp_path, SERVE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert args.read_text().split() == [f"http://127.0.0.1:{PORT}"]


def test_built_app_check_fails_when_the_route_check_fails(tmp_path, free_port):
    result, args = run_built_app_check(tmp_path, SERVE, route_rc=1)
    assert result.returncode != 0 and args.is_file()


def test_built_app_check_fails_when_next_exits(tmp_path, free_port):
    result, args = run_built_app_check(tmp_path, "exit 3")
    assert result.returncode != 0 and "exited with status 3" in result.stdout and not args.exists()


class _Ok(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


def test_built_app_check_refuses_a_port_in_use(tmp_path, free_port):
    """Another server on the port would answer the readiness probe and the route check in place of the build."""
    other = ThreadingHTTPServer(("127.0.0.1", PORT), _Ok)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    try:
        result, args = run_built_app_check(tmp_path, SERVE)
    finally:
        other.shutdown()
        other.server_close()
    assert result.returncode != 0 and "already in use" in result.stdout and not args.exists()
