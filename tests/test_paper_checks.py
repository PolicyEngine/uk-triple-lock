"""The checks behind the working paper's /paper route fail what they should.

tests/test_paper.py checks that the real wrapper and workflow pass. These tests check the other side, so that a later
edit cannot drop a rule while CI stays green: dashboard/scripts/paper_links.py rejects each kind of wrapper it cannot
follow, each for the reason it names, and accepts equivalent markup; check-paper-route.sh fails a loop, a wrong
redirect, a missing file, the wrong bytes or media type, and a dashboard page without its paper link or scripts; and
check-built-app.sh fails when the server or the route check fails. The script tests run bash and curl against local
stand-ins for the app (both are on CI's ubuntu-latest).
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

# A small wrapper that meets every rule. The cases below change this fixed text, not the real wrapper, so an
# equivalent edit to the real one (quoting, spacing, order) cannot break them; tests/test_paper.py checks the real one.
VERSION = "r1-20260101"
MANUSCRIPT = f"{L.MANUSCRIPT}?v={VERSION}"
IFRAME = f'<iframe src="{MANUSCRIPT}"'
IFRAME_END = 'referrerpolicy="same-origin"></iframe>'
SANDBOX = "allow-same-origin allow-scripts allow-popups allow-popups-to-escape-sandbox"
LOGO = f'<img src="{L.LOGO}" alt="PolicyEngine">'
PDF = f'<a href="{L.PDF}">Download PDF</a>'
DASHBOARD_LINK = f'<a href="{L.BASE}">Live dashboard</a>'
TOP = '<a href="#paper-top">Back to top</a>'
H1 = "<h1>A working paper</h1>"
HEAD_END = "</head>"
STYLE_END = "</style>"
FIXTURE = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A working paper | PolicyEngine</title>
<meta property="og:url" content="{L.CANONICAL}">
<link rel="canonical" href="{L.CANONICAL}">
<style>
  .wrap {{ max-width: 960px; }}
</style>
</head>
<body id="paper-top">
<nav class="pe-shell-header" aria-label="Site header">
  <a href="https://policyengine.org/uk" aria-label="PolicyEngine UK home">{LOGO}</a>
</nav>
<main class="wrap">
  {H1}
  <nav class="paper-actions" aria-label="Paper actions">
    <a href="{MANUSCRIPT}">Open standalone HTML</a>
    {PDF}
    {DASHBOARD_LINK}
    <a href="https://github.com/PolicyEngine/uk-triple-lock">Code and artifacts</a>
  </nav>
  <div class="paper-frame-card">
    {IFRAME}
            title="The manuscript" loading="lazy"
            sandbox="{SANDBOX}"
            {IFRAME_END}
  </div>
  <p class="paper-foot">{TOP} <a href="{MANUSCRIPT}">Open manuscript in a new page</a></p>
</main>
<footer class="pe-shell-footer">
  <a href="https://policyengine.org/uk" aria-label="PolicyEngine UK home">{LOGO}</a>
  <p>&copy; 2026 PolicyEngine</p>
</footer>
</body>
</html>
"""


def fixture_with(old, new):
    assert FIXTURE.count(old) >= 1, f"{old!r} is not in the fixture"
    return FIXTURE.replace(old, new, 1)


def added(markup):
    """The fixture with MARKUP after its heading, so every required link is still there."""
    return fixture_with(H1, H1 + markup)


def test_the_fixture_passes():
    problems, local = L.check_wrapper(FIXTURE)
    assert not problems, problems
    assert local == sorted({("application/pdf", L.PDF, "paper/web/index.pdf"),
                            ("image/svg+xml", L.LOGO, "assets/logos/policyengine-white.svg"),
                            ("text/html", L.BASE, None), ("text/html", MANUSCRIPT, "paper/web/index.html")})


# (what, the wrapper, the problem it must report): each is a wrapper the checks cannot vouch for, and each must fail
# for the reason named, not for another rule it happens to break.
REJECTED = [
    # URLs
    ("a relative logo", added('<img src="assets/missing.svg" alt="x">'), "is not https, an in-page fragment"),
    ("a relative PDF link", added('<a href = "web/index.pdf">PDF</a>'), "is not https, an in-page fragment"),
    ("an http link", added('<a href="http://example.com/">x</a>'), "is not https, an in-page fragment"),
    ("a missing dashboard link", fixture_with(DASHBOARD_LINK, ""), "0 links to the dashboard"),
    ("one logo", fixture_with(LOGO, '<img src="https://policyengine.org/logo.svg" alt="x">'), "1 PolicyEngine logos"),
    ("no back-to-top link", fixture_with(TOP, f'<a href="{L.BASE}">Back</a>'), "0 back-to-top links"),
    ("a fragment naming no element", added('<a href="#nowhere">x</a>'), "names no element"),
    ("two manuscript versions", fixture_with(f'{MANUSCRIPT}">Open manuscript', f'{L.MANUSCRIPT}?v=other">Open'),
     "want one shared ?v= version"),
    ("an absolute URL into the zone", added('<img src="https://policyengine.org/uk/triple-lock/x.svg" alt="x">'),
     "is an absolute URL into this app"),
    ("an upper-case absolute URL into the zone", added('<a href="https://policyengine.org/UK/Triple-Lock/x.pdf">x</a>'),
     "is an absolute URL into this app"),
    ("an encoded slash into the zone", added('<a href="https://policyengine.org/uk/triple-lock%2Fx.pdf">x</a>'),
     "is an absolute URL into this app"),
    ("a meta content URL into the zone",
     fixture_with(HEAD_END, '<meta property="og:image" content="https://policyengine.org/uk/triple-lock/x.png">'
                  + HEAD_END), "is an absolute URL into this app"),
    ("a dot segment in an absolute URL", added('<a href="https://policyengine.org/uk/x/../triple-lock/x.pdf">x</a>'),
     "has a . or .. segment or an empty one"),
    ("an empty segment in an absolute URL", added('<a href="https://policyengine.org//uk/triple-lock/x.pdf">x</a>'),
     "has a . or .. segment or an empty one"),
    ("a trailing slash", added('<a href="/uk/triple-lock/paper/web/">x</a>'), "has a trailing slash"),
    ("a dot segment", added('<a href="/uk/triple-lock/paper/./web/index.pdf">x</a>'), "has a trailing slash or a ."),
    ("a percent-encoded dot segment", added('<a href="/uk/triple-lock/paper/%2e%2e/web/index.pdf">x</a>'),
     "has a character outside"),
    ("a backslash", added('<a href="/uk/triple-lock/paper\\web/index.pdf">x</a>'), "has a character outside"),
    ("brackets in a query", added('<a href="/uk/triple-lock/paper/web/index.pdf?x=[abc]">x</a>'),
     "has a character outside"),
    ("a tab in a URL", added('<a href="/uk/triple-lock/paper/web/index.p\tdf">x</a>'), "has a character outside"),
    ("a file type with no expected content type", added('<a href="/uk/triple-lock/data/results.json">x</a>'),
     "needs an expected content type"),
    # Required links a reader cannot use
    ("an empty PDF link", fixture_with(PDF, f'<a href="{L.PDF}"> </a>'), "0 PDF links"),
    # Elements and attributes outside the allow-list
    ("srcset", fixture_with(LOGO, f'<img src="{L.LOGO}" srcset="{L.LOGO}?a=1,2 2x" alt="PolicyEngine">'),
     "<img srcset> is not an attribute"),
    ("ping", fixture_with(TOP, '<a href="#paper-top" ping="web/broken">Back to top</a>'), "<a ping> is not an attribute"),
    ("an event handler", fixture_with(DASHBOARD_LINK, f'<a href="{L.BASE}" onclick="x()">Live dashboard</a>'),
     "<a onclick> is not an attribute"),
    ("the hidden attribute", fixture_with(TOP, '<a hidden href="#paper-top">Back to top</a>'),
     "<a hidden> is not an attribute"),
    ("a style attribute", fixture_with('<main class="wrap">', '<main class="wrap" style="color: red">'),
     "<main style> is not an attribute"),
    ("an iframe srcdoc", fixture_with('loading="lazy"', 'loading="lazy" srcdoc="x"'), "<iframe srcdoc> is not"),
    ("a meta refresh", fixture_with(HEAD_END, '<meta http-equiv="Refresh" content="0; url=/x">' + HEAD_END),
     "<meta http-equiv> is not an attribute"),
    ("a meta content security policy",
     fixture_with(HEAD_END, "<meta http-equiv=\"Content-Security-Policy\" content=\"frame-src 'none'\">" + HEAD_END),
     "<meta http-equiv> is not an attribute"),
    ("another charset", fixture_with('<meta charset="utf-8">', '<meta charset="iso-2022-jp">'), "a <meta> carries"),
    ("a stylesheet link", fixture_with(HEAD_END, f'<link rel="stylesheet" href="{L.BASE}/paper/web/pe-paper.css">'
                                       + HEAD_END), 'a <link> may only be rel="canonical"'),
    ("an svg image href", added('<svg><image href="/uk/triple-lock/x.svg"/></svg>'), "<svg> is not an element"),
    ("an area href", added(f'<map><area href="{L.PDF}"></map>'), "<map> is not an element"),
    ("a script", added("<script>fetch('x')</script>"), "<script> is not an element"),
    ("a template", fixture_with(IFRAME, "<template>" + IFRAME).replace(IFRAME_END, IFRAME_END + "</template>"),
     "<template> is not an element"),
    ("a closed dialog", fixture_with(IFRAME, "<dialog>" + IFRAME).replace(IFRAME_END, IFRAME_END + "</dialog>"),
     "<dialog> is not an element"),
    ("a closed details", fixture_with(IFRAME, "<details>" + IFRAME).replace(IFRAME_END, IFRAME_END + "</details>"),
     "<details> is not an element"),
    ("a noscript", added(f"<noscript>{LOGO}</noscript>"), "<noscript> is not an element"),
    ("a base element", fixture_with(HEAD_END, '<base href="/uk/triple-lock/paper/">' + HEAD_END),
     "<base> is not an element"),
    ("xmp", added("<xmp>x</xmp>"), "<xmp> is not an element"),
    # CSS
    ("CSS url() in upper case", fixture_with(STYLE_END, "a { background: URL(web/missing.svg) }" + STYLE_END),
     "CSS that can load"),
    ("CSS @import after a comment", fixture_with("<style>", '<style>@import/**/"web/missing.css";'),
     "CSS that can load"),
    ("CSS image-set()", fixture_with(STYLE_END, "a { background: image-set('x.png' 1x) }" + STYLE_END),
     "CSS that can load"),
    ("CSS image()", fixture_with(STYLE_END, "a { background: image('x.png') }" + STYLE_END), "CSS that can load"),
    ("CSS url() after an unclosed string's line", fixture_with(STYLE_END, 'a { content: "x\n} b { background: '
                                                                           'url(x.png) }' + STYLE_END),
     "CSS that can load"),
    ("CSS url() after a string holding /*", fixture_with(STYLE_END, 'a { content: "/*" } b { background: url(x.png) }'
                                                                    " /* */" + STYLE_END), "CSS that can load"),
    ("a CSS escape", fixture_with(STYLE_END, "a { background: u\\72l(x.png) }" + STYLE_END), "a backslash outside"),
    ("a backslash in a CSS string", fixture_with(STYLE_END, 'a { content: "\\"; b: url(x)" }' + STYLE_END),
     "a backslash outside"),
    # Markup that Python's parser and a browser read apart
    ("no doctype", fixture_with("<!DOCTYPE html>\n", ""), "does not start with <!DOCTYPE html>"),
    ("a second doctype", fixture_with('<html lang="en">', '<html lang="en"><!DOCTYPE html>'), "must come first, once"),
    ("a self-closing iframe", fixture_with(IFRAME_END, 'referrerpolicy="same-origin" />'), "does not close in HTML"),
    ("a repeated src", fixture_with(IFRAME, '<iframe src="https://policyengine.org/uk/research" ' + IFRAME[8:]),
     "repeats an attribute"),
    ("a repeated sandbox", fixture_with(f'sandbox="{SANDBOX}"', f'sandbox="" sandbox="{SANDBOX}"'),
     "repeats an attribute"),
    ("a link inside the iframe", fixture_with(IFRAME_END, f'referrerpolicy="same-origin">{PDF}</iframe>'),
     "inside <iframe>"),
    ("text inside the iframe", fixture_with(IFRAME_END, 'referrerpolicy="same-origin">fallback</iframe>'),
     "inside <iframe>"),
    ("a link inside the title", fixture_with("<title>A working paper", f"<title>A working paper {PDF}"),
     "inside <title>"),
    ("a block inside a paragraph", fixture_with(f"<p class=\"paper-foot\">{TOP}", f"<p class=\"paper-foot\"><div>{TOP}"
                                                f"</div>"), "inside an open <p>"),
    ("a link inside a link", fixture_with(TOP, f'<a href="{L.BASE}">x {TOP}</a>'), "a link inside a link"),
    ("a heading inside a heading", fixture_with(H1, "<h1>A <h2>working</h2> paper</h1>"), "inside a heading"),
    ("misnested end tags", fixture_with(TOP, '<strong><a href="#paper-top">Back to top</strong></a>'),
     "does not close the innermost open element"),
    ("an element never closed", fixture_with("</html>", ""), "<html> is never closed"),
    ("an end tag for a void element", added("<br></br>"), "<br> has no end tag"),
    ("attributes with no space between", added(f'<a href="{L.BASE}"title="x">Dashboard</a>'),
     'is not written as plain name="value" pairs'),
    ("a slash before an attribute", added(f'<a/href="{L.PDF}">PDF</a>'), 'is not written as plain name="value" pairs'),
    ("an & not written as &amp;", added(f'<a href="{L.PDF}?a=1&ampv=2">PDF</a>'), "not written as &amp;"),
    ("a control character", added("<p>\x0b</p>"), "a control character"),
    ("a no-break space between sandbox tokens", fixture_with("allow-same-origin allow-scripts",
                                                             "allow-same-origin allow-scripts"),
     "sandbox tokens are"),
    ("a missing sandbox token", fixture_with("allow-scripts ", ""), "sandbox tokens are"),
    ("CDATA", added('<![CDATA[ <a href="web/broken.pdf">x</a> ]]>'), "CDATA"),
    ("an HTML comment", added("<!-- x -->"), "an HTML comment"),
    ("a processing instruction", added("<?x y?>"), "a processing instruction"),
]

# Equivalent markup the checks must still accept.
ACCEPTED = [
    ("a single-quoted iframe src", fixture_with(IFRAME, f"<iframe src='{MANUSCRIPT}'")),
    ("an unquoted loading attribute", fixture_with('loading="lazy"', "loading=lazy")),
    ("reordered sandbox tokens", fixture_with("allow-same-origin allow-scripts", "allow-scripts allow-same-origin")),
    ("a newline between sandbox tokens", fixture_with("allow-same-origin allow-scripts",
                                                      "allow-same-origin\n  allow-scripts")),
    ("upper-case names", fixture_with(DASHBOARD_LINK, f'<A HREF="{L.BASE}">Live dashboard</A>')),
    ("the canonical address in a link", added(f'<a href="{L.CANONICAL}">x</a>')),
    ("an image outside the zone in meta",
     fixture_with(HEAD_END, '<meta property="og:image" content="https://policyengine.org/images/x.png">' + HEAD_END)),
    ("a self-closing void element", added("<br/>")),
    ("an &amp; in a URL", added(f'<a href="{L.PDF}?download=1&amp;x=2">PDF</a>')),
    ("url() inside a CSS comment", fixture_with(STYLE_END, "/* url(web/missing.svg) @import */" + STYLE_END)),
    ("url() inside a CSS string", fixture_with(STYLE_END, 'a::after { content: "url(x) @import" }' + STYLE_END)),
    ("an unclosed CSS comment at the end", fixture_with(STYLE_END, "/* url(x)" + STYLE_END)),
    ("a logo link with only an image", fixture_with(DASHBOARD_LINK, f'<a href="{L.BASE}">{LOGO}</a>').replace(
        f'<a href="https://policyengine.org/uk" aria-label="PolicyEngine UK home">{LOGO}</a>', "", 1)),
]


@pytest.mark.parametrize("what, html, reason", REJECTED, ids=[case[0] for case in REJECTED])
def test_paper_links_rejects(what, html, reason):
    problems, _ = L.check_wrapper(html)
    assert any(reason in problem for problem in problems), f"{what}: want {reason!r}, got {problems}"


@pytest.mark.parametrize("what, html", ACCEPTED, ids=[case[0] for case in ACCEPTED])
def test_paper_links_accepts(what, html):
    problems, _ = L.check_wrapper(html)
    assert not problems, problems


def test_the_real_wrapper_passes():
    problems, _ = L.check_wrapper(WRAPPER)
    assert not problems, problems


SCRIPT = f"{L.BASE}/_next/static/chunks/main.js?dpl=dpl_1"


def dashboard_page(title, script=SCRIPT, link=f'<a href="{L.PAPER}">Read the working paper</a>'):
    """A page shaped like the built dashboard's: the layout's title, a script under the basePath and the paper link."""
    return (f'<!DOCTYPE html><html lang="en"><head><title>{title}</title><script src="{script}" async=""></script>'
            f'</head><body><main><p>{link}: the full method.</p><p>Loading...</p></main></body></html>')


def test_dashboard_scripts():
    layout = (DASHBOARD / "app" / "layout.jsx").read_text()
    title = re.search(r'\btitle:\s*"([^"]+)"', layout).group(1)
    assert L.dashboard_scripts(dashboard_page(title), layout) == [SCRIPT]
    for page in [
        dashboard_page("Another app"),
        dashboard_page(title).replace("</head>", "<title>x</title></head>"),
        dashboard_page(title, script="/_next/static/chunks/main.js"),
        dashboard_page(title, link=""),
        dashboard_page(title, link=f'<a href="{L.PAPER}/">Read the working paper</a>'),
        dashboard_page(title, link=f'<a href="{L.PAPER}">Something else</a>'),
        dashboard_page(title, link=f'<template><a href="{L.PAPER}">Read the working paper</a></template>'),
        dashboard_page(title, link=f'<span hidden><a href="{L.PAPER}">Read the working paper</a></span>'),
        dashboard_page(title).replace("<script ", "<template><script ").replace("</script>", "</script></template>"),
    ]:
        assert L.dashboard_scripts(page, layout) is None, page


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
    title = re.search(r'\btitle:\s*"([^"]+)"', layout).group(1)
    dashboard = dashboard_page(title, link="" if mode == "no paper link" else dashboard_page.__defaults__[1])

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
                return self.reply(200, html, b"<html><title>x</title></html>" if mode == "other page"
                                  else dashboard.encode())
            if self.path == SCRIPT:
                if mode == "missing script":
                    return self.reply(404, "text/html", b"not found")
                js = "text/html" if mode == "script as HTML" else "application/javascript; charset=UTF-8"
                return self.reply(200, js.upper() if mode == "upper-case type" else js, b"console.log(1)")
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
            if mode == "spaced inside type" and path == L.PDF:
                ctype = "application / pdf"
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
    "no paper link": "is not this app's dashboard page",
    "missing script": "main.js?dpl=dpl_1 gave 404",
    "script as HTML": "not JavaScript",
    "spaced inside type": "index.pdf came as 'application / pdf'",
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
