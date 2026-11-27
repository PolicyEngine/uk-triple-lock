"""The working paper wrapper's links, checked the same way by tests/test_paper.py and scripts/check-paper-route.sh.

The wrapper (public/paper/index.html) is served at the bare /uk/triple-lock/paper, because policyengine.org strips
trailing slashes before it proxies to this app. There a relative link such as web/index.html resolves to
/uk/triple-lock/web/, so every URL the wrapper serves itself must be root-relative under the basePath. This module
reads every URL the page references (src, href, srcset, CSS url() and the rest), whatever its quoting or spacing,
and applies that rule. It also requires the links the wrapper must carry, and gives each local URL the content type
it must be served with.

    python3 -I scripts/paper_links.py wrapper <wrapper.html>
        prints "<content type><TAB><url>" for each local URL, or the problems on stderr with exit status 1
    python3 -I scripts/paper_links.py manuscript <manuscript.html> <wrapper.html>
        exits 0 only if the file is the rendered manuscript whose title is the wrapper's heading
"""

import posixpath
import re
import sys
from html.parser import HTMLParser
from urllib.parse import unquote

BASE = "/uk/triple-lock"  # the dashboard's basePath (next.config.js)
PAPER = BASE + "/paper"
MANUSCRIPT = PAPER + "/web/index.html"
PDF = PAPER + "/web/index.pdf"
LOGO = BASE + "/assets/logos/policyengine-white.svg"
ABSOLUTE_OK = ("https://policyengine.org/", "https://github.com/PolicyEngine/")
# Pages the app routes rather than serves from public/: the dashboard, and the wrapper itself (a rewrite).
ROUTES = {BASE: None, PAPER: "paper/index.html"}
CONTENT_TYPES = {".html": "text/html", ".svg": "image/svg+xml", ".pdf": "application/pdf", ".png": "image/png",
                 ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".css": "text/css"}
URL_ATTRS = {"src", "href", "poster", "data", "action", "formaction", "xlink:href", "background", "cite",
             "longdesc", "manifest", "ping"}
SRCSET_ATTRS = {"srcset", "imagesrcset"}
CSS_URL = re.compile(r"""url\(\s*(['"]?)(.*?)\1\s*\)|@import\s+(['"])(.*?)\3""")


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls, self.ids, self.problems = [], set(), []
        self.h1, self.title = "", ""
        self._in = None

    def handle_starttag(self, tag, attrs):
        attrs = [(name, value or "") for name, value in attrs]
        names = {name for name, _ in attrs}
        if tag == "base":
            self.problems.append("<base> changes how every relative URL on the page resolves")
        if tag == "iframe" and "srcdoc" in names:
            self.problems.append("an <iframe srcdoc> embeds a page the checks cannot follow")
        if tag == "meta" and any(n == "http-equiv" and v.lower() == "refresh" for n, v in attrs):
            self.problems.append("a <meta http-equiv=refresh> sends the reader elsewhere")
        for name, value in attrs:
            if name == "id" and value:
                self.ids.add(value)
            elif name in URL_ATTRS:
                self.urls.append((tag, name, value))
            elif name in SRCSET_ATTRS:
                for candidate in value.split(","):
                    if candidate.strip():
                        self.urls.append((tag, name, candidate.split()[0]))
            elif name == "style":
                self.urls += [(tag, "style", m.group(2) or m.group(4)) for m in CSS_URL.finditer(value)]
        if tag in ("style", "h1", "title"):
            self._in = tag

    def handle_endtag(self, tag):
        if tag == self._in:
            self._in = None

    def handle_data(self, data):
        if self._in == "style":
            self.urls += [("style", "url()", m.group(2) or m.group(4)) for m in CSS_URL.finditer(data)]
        elif self._in == "h1":
            self.h1 += data
        elif self._in == "title":
            self.title += data


def parse(html):
    page = _Page()
    page.feed(html)
    page.close()
    return page


def path_of(url):
    return unquote(url.split("?", 1)[0].split("#", 1)[0])


def content_type(url):
    path = path_of(url)
    if path in ROUTES:
        return "text/html"
    return CONTENT_TYPES.get(posixpath.splitext(path)[1].lower())


def check_wrapper(html):
    """Return (problems, local): every rule the wrapper breaks, and the URLs it serves itself as (type, url)."""
    page = parse(html)
    problems, local = list(page.problems), []
    for tag, attr, url in page.urls:
        where = f"<{tag} {attr}={url!r}>"
        if url.startswith("https://"):
            if not url.startswith(ABSOLUTE_OK):
                problems.append(f"{where} points outside policyengine.org and PolicyEngine's GitHub")
        elif url.startswith("#"):
            if url[1:] not in page.ids:
                problems.append(f"{where} names no element")
        elif url == BASE or url.startswith(BASE + "/"):
            path = path_of(url)
            if posixpath.normpath(path) != path:
                problems.append(f"{where} has a trailing slash or a . or .. segment")
            elif content_type(url) is None:
                problems.append(f"{where} needs an expected content type in paper_links.CONTENT_TYPES")
            else:
                local.append((tag, attr, url))
        else:
            problems.append(f"{where} is not https, an in-page fragment or root-relative under {BASE}")

    def count(tag, attr, match):
        return sum(1 for t, a, u in local if t == tag and a == attr and match(u))

    versioned = MANUSCRIPT + "?v="
    for what, found, ok, want in [
        ("links to the dashboard", count("a", "href", lambda u: u == BASE), lambda n: n >= 1, "at least 1"),
        ("PolicyEngine logos", count("img", "src", lambda u: u == LOGO), lambda n: n == 2, "2"),
        ("manuscript iframes", count("iframe", "src", lambda u: u.startswith(versioned)), lambda n: n == 1, "1"),
        ("manuscript links", count("a", "href", lambda u: u.startswith(versioned)), lambda n: n >= 2, "at least 2"),
        ("PDF links", count("a", "href", lambda u: u == PDF), lambda n: n >= 1, "at least 1"),
        ("back-to-top links", sum(u == "#paper-top" for t, _, u in page.urls if t == "a"), lambda n: n >= 1,
         "at least 1"),
    ]:
        if not ok(found):
            problems.append(f"{found} {what}, want {want}")
    manuscript_urls = [u for _, _, u in local if path_of(u) == MANUSCRIPT]
    versions = {u.split("?v=", 1)[1].split("#", 1)[0] if "?v=" in u else "" for u in manuscript_urls}
    if len(versions) != 1 or "" in versions:
        problems.append(f"the manuscript URLs carry versions {sorted(versions)}, want one shared ?v= version")
    return problems, sorted({(content_type(u), u) for _, _, u in local})


def is_manuscript(html, title):
    """The rendered manuscript, not a fallback page: Quarto's title block, and the wrapper's heading as its title."""
    page = parse(html)
    norm = " ".join
    return "title-block-header" in page.ids and norm(page.title.split()) == norm(title.split()) != ""


def main(argv):
    if len(argv) == 3 and argv[1] == "wrapper":
        problems, local = check_wrapper(open(argv[2], encoding="utf-8").read())
        if problems:
            sys.stderr.write("".join(f"FAIL: {p}\n" for p in problems))
            return 1
        sys.stdout.write("".join(f"{ctype}\t{url}\n" for ctype, url in local))
        return 0
    if len(argv) == 4 and argv[1] == "manuscript":
        title = parse(open(argv[3], encoding="utf-8").read()).h1
        return 0 if is_manuscript(open(argv[2], encoding="utf-8").read(), title) else 1
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
