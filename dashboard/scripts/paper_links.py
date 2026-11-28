"""The working paper wrapper's URLs, checked the same way by tests/test_paper.py and scripts/check-paper-route.sh.

The wrapper (public/paper/index.html) is served at the bare /uk/triple-lock/paper, because policyengine.org strips
trailing slashes before it proxies to this app. There a relative link such as web/index.html resolves to
/uk/triple-lock/web/, so every URL the wrapper serves itself must be root-relative under the basePath.

The rules are an allow-list on purpose: the wrapper is one small static page, and a rule it cannot break is easier to
trust than a parser for everything HTML and CSS can do. The page may use only the elements and attributes in ELEMENTS
and GLOBAL_ATTRS, in markup that Python's HTMLParser and a browser read alike: it starts with <!DOCTYPE html>, writes
each start tag as plain name="value" pairs with any & as &amp;, closes every element it opens in order (so no browser
repair such as closing an open <p> or a link inside a link changes the tree), keeps markup and text out of <title>
and <iframe>, and has no comments, CDATA, processing instructions or control characters. A <meta> carries a utf-8
charset or a name or property with content (no http-equiv), and a <link> only rel="canonical". A URL may sit only in
<a href>, <img src>, <iframe src>, <link href> or a <meta content> that starts with a scheme or a slash. In the <style>
element, which is tokenized as CSS (comments skipped, strings read as strings), url(), @import, image(), image-set()
and src() are rejected, as is any backslash outside a comment. Required links count only when they can be used: an
<a> with text or an image. To use anything else, first teach this module to follow it. The checks read markup, not
layout: they cannot see what CSS hides.

    python3 -I scripts/paper_links.py wrapper <wrapper.html>
        prints "<content type><TAB><url><TAB><file under public/, or - for the dashboard page>" for each local URL,
        or the problems on stderr with exit status 1
    python3 -I scripts/paper_links.py dashboard <page.html> <app/layout.jsx>
        exits 0 only if the page is this app's dashboard: the layout's title, a visible "Read the working paper" link
        to the bare /paper, and a script under the basePath's /_next/static/; prints each such script's URL
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
# The manuscript is our own same-origin render; it needs its scripts for the figure lightbox, anchors and tooltips
# (issue #9, S1), so the sandbox allows them.
SANDBOX = {"allow-same-origin", "allow-scripts", "allow-popups", "allow-popups-to-escape-sandbox"}
# Pages the app routes rather than serves from public/: the dashboard (no file), and the wrapper itself (a rewrite).
ROUTES = {BASE: None, PAPER: "paper/index.html"}
CONTENT_TYPES = {".html": "text/html", ".svg": "image/svg+xml", ".pdf": "application/pdf", ".png": "image/png",
                 ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".css": "text/css"}
URL_PLACES = {("a", "href"), ("img", "src"), ("iframe", "src"), ("link", "href")}
# The elements the wrapper may use, each with the attributes it may carry besides GLOBAL_ATTRS: elements that show
# their content, load nothing the checks do not follow, and parse the same in Python and a browser.
ELEMENTS = {
    "html": set(), "head": set(), "title": set(), "style": set(), "body": set(),
    "meta": {"charset", "name", "property", "content"}, "link": {"rel", "href"},
    "nav": set(), "header": set(), "main": set(), "footer": set(), "section": set(), "div": set(),
    "h1": set(), "h2": set(), "h3": set(), "p": set(), "span": set(), "strong": set(), "em": set(), "br": set(),
    "a": {"href", "rel", "target"}, "img": {"src", "alt", "width", "height"},
    "iframe": {"src", "title", "loading", "sandbox", "referrerpolicy", "width", "height"},
}
GLOBAL_ATTRS = {"class", "id", "lang", "aria-label", "title"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
TEXT_ONLY = {"title", "style", "iframe"}  # a browser reads what sits inside these as text, not markup
CLOSES_P = {"nav", "header", "main", "footer", "section", "div", "h1", "h2", "h3", "p"}  # a browser closes an open <p>
HEADINGS = {"h1", "h2", "h3"}
HIDING = {"template", "noscript", "script", "style", "title", "iframe"}  # content a page does not show as a link
WS = " \t\n\f\r"  # HTML's and CSS's ASCII whitespace
START_TAG = re.compile(r"<[A-Za-z][A-Za-z0-9]*(?:[ \t\n\f\r]+[A-Za-z][A-Za-z0-9-]*(?:[ \t\n\f\r]*=[ \t\n\f\r]*"
                       r"""(?:"[^"<]*"|'[^'<]*'|[^ \t\n\f\r"'=<>`]+))?)*[ \t\n\f\r]*/?>""")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f-\x9f]")
CSS_LOADS = re.compile(r"url\(|@import|image\(|image-set\(|src\(", re.I | re.A)
LOCAL_URL = re.compile(r"[A-Za-z0-9._~/-]+(\?[A-Za-z0-9._~=&-]*)?(#[A-Za-z0-9._~-]*)?")
HTTPS_URL = re.compile(r"https://[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]+")


def tokens(value):
    """A token list such as class, rel or sandbox, split on HTML's ASCII whitespace only (a no-break space joins)."""
    return [token for token in re.split(r"[ \t\n\f\r]+", value) if token]


class _Page(HTMLParser):
    """Every element with its attributes, text and open ancestors, the URLs in the allowed places, and the rules the
    markup breaks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements, self.urls, self.ids, self.problems = [], [], set(), []
        self.doctype = False
        self._open = []

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        if tag not in VOID:
            self.problems.append(f"<{tag} ... /> does not close in HTML: a browser reads what follows as its content")
        self._start(tag, attrs)
        if tag not in VOID:
            self._end(tag)

    def _start(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        if not START_TAG.fullmatch(raw):
            self.problems.append(f"<{tag}> is not written as plain name=\"value\" pairs separated by spaces")
        if re.search(r"&(?!amp;)", raw):
            self.problems.append(f"<{tag}> has an & not written as &amp;, which Python and a browser decode apart")
        attrs = [(name, value or "") for name, value in attrs]
        element = {"tag": tag, "attrs": dict(attrs), "text": "", "img": False, "ancestors": list(self._open)}
        self.elements.append(element)
        open_tags = [e["tag"] for e in self._open]
        if tag not in ELEMENTS:
            self.problems.append(f"<{tag}> is not an element the checks read")
        if TEXT_ONLY & set(open_tags):
            self.problems.append(f"<{tag}> inside <{[t for t in open_tags if t in TEXT_ONLY][-1]}>, "
                                 "where a browser reads markup as text")
        if tag in CLOSES_P and "p" in open_tags:
            self.problems.append(f"<{tag}> inside an open <p>: a browser closes the <p> first")
        if tag == "a" and "a" in open_tags:
            self.problems.append("a link inside a link: a browser closes the outer one first")
        if tag in HEADINGS and HEADINGS & set(open_tags):
            self.problems.append(f"<{tag}> inside a heading: a browser closes the heading first")
        if len({name for name, _ in attrs}) != len(attrs):
            self.problems.append(f"<{tag}> repeats an attribute; a browser keeps the first value, the checks the last")
        allowed = GLOBAL_ATTRS | ELEMENTS.get(tag, set())
        for name, value in attrs:
            if name not in allowed:
                self.problems.append(f"<{tag} {name}> is not an attribute the checks allow on <{tag}>")
            elif name == "id" and value:
                self.ids.add(value)
            elif (tag, name) in URL_PLACES or (tag == "meta" and name == "content" and value.startswith(("/", "http"))):
                self.urls.append((tag, name, value))
        if tag == "meta":
            keys, charset = set(element["attrs"]), element["attrs"].get("charset", "").lower()
            if not (keys == {"charset"} and charset == "utf-8" or keys in ({"name", "content"}, {"property", "content"})):
                self.problems.append("a <meta> carries charset=\"utf-8\", or a name or property with content, only")
        if tag == "link" and tokens(element["attrs"].get("rel", "")) != ["canonical"]:
            self.problems.append("a <link> may only be rel=\"canonical\"")
        if tag == "img":
            for e in self._open:
                e["img"] = True
        if tag not in VOID:
            self._open.append(element)

    def handle_endtag(self, tag):
        if tag in VOID:
            self.problems.append(f"</{tag}>: <{tag}> has no end tag, and a browser reads this one its own way")
            return
        self._end(tag)

    def _end(self, tag):
        if self._open and self._open[-1]["tag"] == tag:
            self._open.pop()
            return
        top = f" <{self._open[-1]['tag']}>" if self._open else ""
        self.problems.append(f"</{tag}> does not close the innermost open element{top}")
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i]["tag"] == tag:
                del self._open[i:]
                break

    def handle_data(self, data):
        if self._open and self._open[-1]["tag"] == "iframe" and data.strip(WS):
            self.problems.append("text inside <iframe>, which a browser does not show")
        if any(e["tag"] == "title" for e in self._open) and "<" in data:
            self.problems.append("markup inside <title>, which a browser reads as text")
        for element in self._open:
            element["text"] += data

    def handle_comment(self, data):
        self.problems.append("an HTML comment, which a browser may end where Python's parser does not")

    def handle_decl(self, decl):
        if decl.lower() != "doctype html":
            self.problems.append(f"<!{decl}> is a declaration other than <!DOCTYPE html>")
        elif self.doctype or self.elements:
            self.problems.append("<!DOCTYPE html> must come first, once")
        self.doctype = True

    def unknown_decl(self, data):
        self.problems.append(f"<![{data[:20]}...]> is CDATA or a marked section, which a browser reads as a comment")

    def handle_pi(self, data):
        self.problems.append("a processing instruction, which a browser reads as a comment")

    def close(self):
        super().close()
        if not self.doctype:
            self.problems.append("the page does not start with <!DOCTYPE html>")
        for element in self._open:
            self.problems.append(f"<{element['tag']}> is never closed")


def parse(html):
    page = _Page()
    if CONTROL.search(html):
        page.problems.append("a control character, which Python and a browser read apart")
    page.feed(html)
    page.close()
    return page


def css_problems(css):
    """Why a <style> block may load what the checks cannot follow, reading it as CSS's tokenizer does: a comment runs
    to its */ (or the end) and loads nothing; a string runs to its closing quote or, unclosed, to the end of its line;
    url( and the other loading functions count only outside both. A backslash could escape a quote or spell a name,
    so it is rejected outside comments."""
    code, kept, i = [], [], 0
    while i < len(css):
        if css.startswith("/*", i):
            end = css.find("*/", i + 2)
            i = len(css) if end < 0 else end + 2
            code.append(" ")
            kept.append(" ")
        elif css[i] in "\"'":
            quote, j = css[i], i + 1
            while j < len(css) and css[j] not in quote + "\n\r\f":
                j += 1
            kept.append(css[i:j + 1 if j < len(css) and css[j] == quote else j])
            code.append(quote * 2)
            i = j + 1 if j < len(css) and css[j] == quote else j
        else:
            code.append(css[i])
            kept.append(css[i])
            i += 1
    problems = []
    if "\\" in "".join(kept):
        problems.append("a <style> block has a backslash outside a comment, which can escape a quote or spell a name")
    if CSS_LOADS.search("".join(code)):
        problems.append("a <style> block has CSS that can load a URL the checks cannot follow")
    return problems


def shown(element):
    """Whether a page shows the element: it is not inside an element whose content a page does not show, and neither
    it nor an ancestor carries the hidden attribute."""
    return not any(a["tag"] in HIDING or "hidden" in a["attrs"] for a in element["ancestors"]) \
        and "hidden" not in element["attrs"]


def usable(element):
    """A link a reader can see and use: shown, with text or an image."""
    return shown(element) and (bool(element["text"].strip(WS)) or element["img"])


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
    for element in page.elements:
        if element["tag"] == "style":
            problems += css_problems(element["text"])
    for tag, attr, url in page.urls:
        problem = _url_problem(url, page.ids)
        if problem:
            problems.append(f"<{tag} {attr}={url!r}> {problem}")
        elif url == BASE or url.startswith(BASE + "/"):
            local.append((tag, attr, url))

    def count(tag, attr, match):
        return sum(1 for e in page.elements if e["tag"] == tag and attr in e["attrs"] and match(e["attrs"][attr])
                   and (usable(e) if tag == "a" else shown(e)))

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
    for frame in page.elements:
        if frame["tag"] == "iframe" and set(tokens(frame["attrs"].get("sandbox", ""))) != SANDBOX:
            problems.append(f"the iframe's sandbox tokens are {sorted(tokens(frame['attrs'].get('sandbox', '')))}, "
                            f"want {sorted(SANDBOX)}")
    manuscript_urls = [u for _, _, u in local if path_of(u) == MANUSCRIPT]
    versions = {u.split("?v=", 1)[1].split("#", 1)[0] if "?v=" in u else "" for u in manuscript_urls}
    if len(versions) != 1 or "" in versions:
        problems.append(f"the manuscript URLs carry versions {sorted(versions)}, want one shared ?v= version")
    return problems, sorted({(content_type(u), u, public_file(u)) for _, _, u in local})


def dashboard_scripts(html, layout):
    """The scripts of this app's own dashboard page, or None if the page is not it. It must carry the root layout's
    title, a visible "Read the working paper" link to the bare /paper, and at least one script served from the
    basePath's /_next/static/ (each returned, for the route check to fetch)."""
    title = re.search(r'\btitle:\s*"([^"]+)"', layout)
    page = parse(html)
    titles = [" ".join(tokens(e["text"])) for e in page.elements if e["tag"] == "title"]
    links = [e for e in page.elements if e["tag"] == "a" and e["attrs"].get("href") == PAPER and usable(e)
             and " ".join(tokens(e["text"])) == "Read the working paper"]
    scripts = [e["attrs"]["src"] for e in page.elements if e["tag"] == "script"
               and e["attrs"].get("src", "").startswith(BASE + "/_next/static/")
               and LOCAL_URL.fullmatch(e["attrs"]["src"]) and shown(e)]
    if title and titles == [title.group(1)] and links and scripts:
        return scripts
    return None


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
        scripts = dashboard_scripts(page, layout)
        if scripts is None:
            return 1
        sys.stdout.write("".join(f"{script}\n" for script in scripts))
        return 0
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
