"""The working paper wrapper's URLs, checked the same way by tests/test_paper.py and scripts/check-paper-route.sh.

The wrapper (public/paper/index.html) is served at the bare /uk/triple-lock/paper, because policyengine.org strips
trailing slashes before it proxies to this app. There a relative link such as web/index.html resolves to
/uk/triple-lock/web/, so every URL the wrapper serves itself must be root-relative under the basePath.

The rules are an allow-list on purpose: the wrapper is one small static page, and a rule it cannot break is easier to
trust than a parser for everything HTML and CSS can load. A URL may sit only in <a href>, <img src>, <iframe src>,
<link href> or a <meta content> that starts with a scheme or a slash. Everything else that can load or open a URL is
rejected, not followed: any other URL attribute (srcset, ping, poster and the rest), an event handler, <script>,
<template>, <noscript>, <base>, <object>, <embed>, a meta refresh, an iframe srcdoc, the hidden and inert
attributes, and url(), @import, image-set(), src() or a backslash anywhere in CSS, comments included. So is markup
that Python's HTMLParser reads differently from a browser: a self-closing tag on a non-void element (a browser leaves
it open, and an <iframe/> swallows the rest of the page), a repeated attribute (a browser keeps the first value),
comments, CDATA and other declarations, processing instructions, <svg> and <math> content, and the raw-text elements
<xmp>, <noembed>, <noframes>, <plaintext> and <textarea>. To use one, first teach this module to follow it. The
checks read markup, not layout: they cannot see what CSS hides.

    python3 -I scripts/paper_links.py wrapper <wrapper.html>
        prints "<content type><TAB><url><TAB><file under public/, or - for the dashboard page>" for each local URL,
        or the problems on stderr with exit status 1
    python3 -I scripts/paper_links.py dashboard <page.html> <app/layout.jsx>
        exits 0 only if the page is this app's: the layout's title, and a script under the basePath's /_next/static/
"""

import posixpath
import re
import sys
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

BASE = "/uk/triple-lock"  # the dashboard's basePath (next.config.js)
PAPER = BASE + "/paper"
MANUSCRIPT = PAPER + "/web/index.html"
PDF = PAPER + "/web/index.pdf"
LOGO = BASE + "/assets/logos/policyengine-white.svg"
CANONICAL = "https://policyengine.org" + PAPER  # the only absolute URL into this app's zone the wrapper may carry
ABSOLUTE_OK = ("https://policyengine.org/", "https://github.com/PolicyEngine/")
# Pages the app routes rather than serves from public/: the dashboard (no file), and the wrapper itself (a rewrite).
ROUTES = {BASE: None, PAPER: "paper/index.html"}
CONTENT_TYPES = {".html": "text/html", ".svg": "image/svg+xml", ".pdf": "application/pdf", ".png": "image/png",
                 ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".css": "text/css"}
URL_PLACES = {("a", "href"), ("img", "src"), ("iframe", "src"), ("link", "href")}
URL_ATTRS = {"src", "href", "srcset", "imagesrcset", "ping", "poster", "data", "action", "formaction", "xlink:href",
             "background", "cite", "longdesc", "manifest", "codebase", "archive", "lowsrc", "dynsrc", "profile",
             "usemap"}
BANNED_TAGS = {"base", "script", "template", "noscript", "object", "embed", "applet", "frame", "frameset", "portal",
               "svg", "math", "xmp", "noembed", "noframes", "plaintext", "textarea"}
BANNED_ATTRS = {"hidden", "inert", "srcdoc"}
CSS_LOADS = re.compile(r"url\(|@import|image-set\(|src\(|\\", re.I)
LOCAL_URL = re.compile(r"[A-Za-z0-9._~/-]+(\?[A-Za-z0-9._~=&-]*)?(#[A-Za-z0-9._~-]*)?")
HTTPS_URL = re.compile(r"https://[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]+")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Page(HTMLParser):
    """Every element with its attributes and text, the URLs in the allowed places, and the rules the markup breaks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements, self.urls, self.ids, self.problems = [], [], set(), []
        self._open = []

    def handle_starttag(self, tag, attrs):
        attrs = [(name, value or "") for name, value in attrs]
        element = {"tag": tag, "attrs": dict(attrs), "text": ""}
        self.elements.append(element)
        if len({name for name, _ in attrs}) != len(attrs):
            self.problems.append(f"<{tag}> repeats an attribute; a browser keeps the first value, the checks the last")
        if tag in BANNED_TAGS:
            self.problems.append(f"<{tag}> is not allowed: the checks cannot read it the way a browser does")
        if tag == "meta" and element["attrs"].get("http-equiv", "").lower() == "refresh":
            self.problems.append("a <meta http-equiv=refresh> sends the reader elsewhere")
        for name, value in attrs:
            if name == "id" and value:
                self.ids.add(value)
            elif name in BANNED_ATTRS or name.startswith("on"):
                self.problems.append(f"<{tag} {name}> loads or hides content the checks cannot follow")
            elif (tag, name) in URL_PLACES or (tag == "meta" and name == "content" and value.startswith(("/", "http"))):
                self.urls.append((tag, name, value))
            elif name in URL_ATTRS:
                self.problems.append(f"<{tag} {name}> is not a place the checks follow URLs from")
            elif name == "style" and CSS_LOADS.search(value):
                self.problems.append(f"<{tag} style> has CSS that can load a URL the checks cannot follow")
        if tag not in VOID:
            self._open.append(element)

    def handle_startendtag(self, tag, attrs):
        if tag not in VOID:
            self.problems.append(f"<{tag} ... /> does not close in HTML: a browser reads what follows as its content")
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_comment(self, data):
        self.problems.append("an HTML comment, which a browser may end where Python's parser does not")

    def handle_decl(self, decl):
        if decl.lower() != "doctype html":
            self.problems.append(f"<!{decl}> is a declaration other than <!DOCTYPE html>")

    def unknown_decl(self, data):
        self.problems.append(f"<![{data[:20]}...]> is CDATA or a marked section, which a browser reads as a comment")

    def handle_pi(self, data):
        self.problems.append("a processing instruction, which a browser reads as a comment")

    def handle_endtag(self, tag):
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i]["tag"] == tag:
                del self._open[i:]
                break

    def handle_data(self, data):
        for element in self._open:
            element["text"] += data


def parse(html):
    page = _Page()
    page.feed(html)
    page.close()
    return page


def path_of(url):
    return url.split("?", 1)[0].split("#", 1)[0]


def content_type(url):
    path = path_of(url)
    if path in ROUTES:
        return "text/html"
    return CONTENT_TYPES.get(posixpath.splitext(path)[1].lower())


def public_file(url):
    """The file under public/ that a local URL serves, or None for a page the app renders."""
    path = path_of(url)
    return ROUTES[path] if path in ROUTES else path[len(BASE) + 1:]


def _url_problem(url, ids):
    """Why a URL breaks the rules, or None if it is local (root-relative under BASE) or allowed elsewhere."""
    if url.startswith("#"):
        return None if url[1:] in ids else "names no element"
    if url.startswith("https://"):
        if not HTTPS_URL.fullmatch(url) or not url.startswith(ABSOLUTE_OK):
            return "points outside policyengine.org and PolicyEngine's GitHub"
        parts = urlsplit(url)
        path = unquote(parts.path)
        if any(segment in (".", "..") for segment in path.split("/")) or "//" in path:
            return "has a . or .. segment or an empty one"
        in_zone = path.lower() == BASE or path.lower().startswith(BASE + "/")
        if parts.hostname in ("policyengine.org", "www.policyengine.org") and in_zone and url != CANONICAL:
            return f"is an absolute URL into this app; use a root-relative one (only {CANONICAL} may be absolute)"
        return None
    if not (url == BASE or url.startswith(BASE + "/")):
        return f"is not https, an in-page fragment or root-relative under {BASE}"
    if not LOCAL_URL.fullmatch(url):
        return "has a character outside letters, digits and -._~/ (and ?=& in the query)"
    path = path_of(url)
    if posixpath.normpath(path) != path:
        return "has a trailing slash or a . or .. segment"
    if content_type(url) is None:
        return "needs an expected content type in paper_links.CONTENT_TYPES"
    return None


def check_wrapper(html):
    """Return (problems, local): every rule the wrapper breaks, and each URL it serves itself as (type, url, file)."""
    page = parse(html)
    problems, local = list(page.problems), []
    if any(e["tag"] == "style" and CSS_LOADS.search(e["text"]) for e in page.elements):
        problems.append("a <style> block has CSS that can load a URL the checks cannot follow")
    for tag, attr, url in page.urls:
        problem = _url_problem(url, page.ids)
        if problem:
            problems.append(f"<{tag} {attr}={url!r}> {problem}")
        elif url == BASE or url.startswith(BASE + "/"):
            local.append((tag, attr, url))

    def count(tag, attr, match):
        return sum(1 for t, a, u in page.urls if t == tag and a == attr and match(u))

    versioned = MANUSCRIPT + "?v="
    for what, found, ok, want in [
        ("links to the dashboard", count("a", "href", lambda u: u == BASE), lambda n: n >= 1, "at least 1"),
        ("PolicyEngine logos", count("img", "src", lambda u: u == LOGO), lambda n: n == 2, "2"),
        ("manuscript iframes", count("iframe", "src", lambda u: u.startswith(versioned)), lambda n: n == 1, "1"),
        ("manuscript links", count("a", "href", lambda u: u.startswith(versioned)), lambda n: n >= 2, "at least 2"),
        ("PDF links", count("a", "href", lambda u: u == PDF), lambda n: n >= 1, "at least 1"),
        ("back-to-top links", count("a", "href", lambda u: u == "#paper-top"), lambda n: n >= 1, "at least 1"),
    ]:
        if not ok(found):
            problems.append(f"{found} {what}, want {want}")
    manuscript_urls = [u for _, _, u in local if path_of(u) == MANUSCRIPT]
    versions = {u.split("?v=", 1)[1].split("#", 1)[0] if "?v=" in u else "" for u in manuscript_urls}
    if len(versions) != 1 or "" in versions:
        problems.append(f"the manuscript URLs carry versions {sorted(versions)}, want one shared ?v= version")
    return problems, sorted({(content_type(u), u, public_file(u)) for _, _, u in local})


def is_dashboard(html, layout):
    """The app's own page: the root layout's title, and a script served from the basePath's /_next/static/."""
    title = re.search(r'\btitle:\s*"([^"]+)"', layout)
    page = parse(html)
    titles = [" ".join(e["text"].split()) for e in page.elements if e["tag"] == "title"]
    scripts = [e for e in page.elements if e["tag"] == "script"
               and e["attrs"].get("src", "").startswith(BASE + "/_next/static/")]
    return bool(title) and titles == [title.group(1)] and bool(scripts)


def main(argv):
    if len(argv) == 3 and argv[1] == "wrapper":
        problems, local = check_wrapper(open(argv[2], encoding="utf-8").read())
        if problems:
            sys.stderr.write("".join(f"FAIL: {p}\n" for p in problems))
            return 1
        sys.stdout.write("".join(f"{ctype}\t{url}\t{file or '-'}\n" for ctype, url, file in local))
        return 0
    if len(argv) == 4 and argv[1] == "dashboard":
        page, layout = (open(path, encoding="utf-8").read() for path in argv[2:])
        return 0 if is_dashboard(page, layout) else 1
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
