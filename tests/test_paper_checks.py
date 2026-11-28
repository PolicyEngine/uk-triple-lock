"""The scripts behind the working paper's /paper route fail what they should.

tests/test_paper.py checks that the real wrapper and the Dashboard workflow pass. These tests check the other side:
check-paper-route.sh fails each broken app in BROKEN (a loop, a wrong redirect, a missing file, the wrong bytes, the
wrong media type), and check-built-app.sh starts `next start` on 127.0.0.1, fails when it exits or the route check
fails, and refuses a port where something already listens. They test those cases only, not every way the scripts
could be weakened. They run bash and curl
against local stand-ins for the app (both are on CI's ubuntu-latest).
"""

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
BASE = "/uk/triple-lock"  # the dashboard's basePath (next.config.js)
PAPER = BASE + "/paper"
MANUSCRIPT = PAPER + "/web/index.html"
PDF = PAPER + "/web/index.pdf"
LOGO = BASE + "/assets/logos/policyengine-white.svg"
TYPES = {MANUSCRIPT: "text/html; charset=utf-8", PDF: "application/pdf", LOGO: "image/svg+xml"}


# ── check-paper-route.sh against a stand-in server ──────────────────────


def public_copy(tmp_path):
    """The checked-in files the route check compares, copied so a test cannot change them."""
    public = tmp_path / "public"
    for url in [PAPER + "/index.html", *TYPES]:
        file = url[len(BASE) + 1:]
        (public / file).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(DASHBOARD / "public" / file, public / file)
    return public


def stand_in(mode, public):
    """A server answering as the app would, broken in the way MODE names."""

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
            if path == PAPER:
                if mode == "loop":
                    return self.reply(308, location=PAPER + "/")
                body = (public / "paper/index.html").read_bytes()
                ctype = "text/plain; charset=utf-8" if mode == "wrapper as text" else html
                return self.reply(200, ctype, body + (b"\n" if mode == "changed wrapper" else b""))
            if path == PAPER + "/":
                if mode == "200 at the slash":
                    return self.reply(200, html, (public / "paper/index.html").read_bytes())
                return self.reply(308, location=BASE + "/" if mode == "wrong target" else PAPER)
            if path not in TYPES or (mode == "missing logo" and path == LOGO):
                return self.reply(404, "text/html", b"not found")
            body = (public / path[len(BASE) + 1:]).read_bytes()
            ctype = html if path == MANUSCRIPT else TYPES[path]
            if path == PDF and mode == "PDF as HTML":
                return self.reply(200, html, b"<html>app shell</html>")
            if path == PDF and mode == "truncated PDF":
                return self.reply(200, ctype, body[:1000], length=len(body))
            if path == PDF and mode == "PDF stub":
                return self.reply(200, ctype, b"%PDF-")
            if path == PDF and mode == "spaced inside type":
                ctype = "application / pdf"
            if path == LOGO and mode == "commented SVG":
                return self.reply(200, ctype, b"<!-- <svg -->")
            if path == MANUSCRIPT and mode == "changed manuscript":
                body += b"\n"
            if mode == "upper-case type":
                ctype = ctype.upper()
            return self.reply(200, ctype, body)

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
    "wrapper as text": "/paper came as 'text/plain",
    "200 at the slash": "/paper/ gave 200",
    "wrong target": "not 308 to",
    "missing logo": "policyengine-white.svg gave 404",
    "PDF as HTML": "index.pdf came as",
    "spaced inside type": "index.pdf came as 'application / pdf'",
    "truncated PDF": "curl exited 18",
    "PDF stub": "index.pdf is not public/paper/web/index.pdf",
    "commented SVG": "policyengine-white.svg is not public/",
    "changed manuscript": "is not public/paper/web/index.html",
    "changed wrapper": "/paper is not public/paper/index.html",
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
    # The stand-in records its arguments in next-args, so a test can tell whether and how it was started.
    next_bin.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "{tmp_path / "next-args"}"\n' + next_body + "\n")
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
    assert (tmp_path / "next-args").read_text().split() == ["start", "-H", "127.0.0.1", "-p", str(PORT)]
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


class _Listener:
    """Something on 127.0.0.1:PORT: an HTTP server, or a bare TCP listener that closes each connection at once or
    never answers it."""

    def __init__(self, kind):
        self.kind, self.held, self.stop = kind, [], threading.Event()
        if kind == "HTTP server":
            self.http = ThreadingHTTPServer(("127.0.0.1", PORT), _Ok)
            threading.Thread(target=self.http.serve_forever, daemon=True).start()
            return
        self.sock = socket.socket()
        # An earlier test's connections to the port can still be in TIME_WAIT; HTTPServer sets this too.
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", PORT))
        self.sock.listen()
        self.sock.settimeout(0.2)
        self.thread = threading.Thread(target=self.accept, daemon=True)
        self.thread.start()

    def accept(self):
        while not self.stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            if self.kind == "closes at once":
                conn.close()
            else:
                self.held.append(conn)

    def close(self):
        if self.kind == "HTTP server":
            self.http.shutdown()
            self.http.server_close()
            return
        self.stop.set()
        self.thread.join()
        for conn in self.held:
            conn.close()
        self.sock.close()


@pytest.mark.parametrize("kind", ["HTTP server", "closes at once", "never answers"])
def test_built_app_check_refuses_a_port_in_use(kind, tmp_path, free_port):
    """Anything listening on the port would answer the readiness probe and the route check in place of the build."""
    other = _Listener(kind)
    try:
        result, args = run_built_app_check(tmp_path, SERVE)
    finally:
        other.close()
    assert result.returncode != 0 and "already in use" in result.stdout, result.stdout + result.stderr
    assert not (tmp_path / "next-args").exists() and not args.exists()
