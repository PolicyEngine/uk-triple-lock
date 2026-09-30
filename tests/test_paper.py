"""The working paper: its /paper wrapper, its committed render, its sources and its numbers.

Pattern (PolicyBench's /paper page): /uk/triple-lock/paper/ is a shelled wrapper
(site header, paper header, action links, a versioned sandboxed iframe of the
manuscript at paper/web/, back-to-top footer). paper/render.sh renders the
Quarto manuscript and syncs it to dashboard/public/paper/web/, never to /paper/
itself.

The manuscript types no result by hand: paper/paperdata.py reads every figure
from data/results.json. These tests check the wrapper, that the committed render
matches the current results file, that the prose carries no hand-typed numbers,
that every citation resolves, the house style, and that no survey record's
identifiers or weights reach the paper. None needs Quarto or matplotlib.
"""

import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
PAPER_SRC = ROOT / "paper"
QMD = PAPER_SRC / "index.qmd"
BIB = PAPER_SRC / "references.bib"
PUBLIC = ROOT / "dashboard" / "public" / "paper"
WRAPPER = PUBLIC / "index.html"
WEB = PUBLIC / "web"
sys.path.insert(0, str(PAPER_SRC))

import paperdata as D  # noqa: E402


# ── The /paper wrapper ───────────────────────────────────────────────────


def wrapper():
    return WRAPPER.read_text()


def test_wrapper_embeds_versioned_manuscript():
    html = wrapper()
    srcs = re.findall(r'<iframe src="(web/index\.html\?v=[^"]+)"', html)
    assert len(srcs) == 1, "exactly one embedded manuscript iframe"
    version = srcs[0].split("?v=")[1]
    links = re.findall(r'href="(web/index\.html[^"]*)"', html)
    assert len(links) >= 2, "standalone link in the action row and the footer"
    for href in links:
        assert href.endswith(f"?v={version}"), href
    assert 'sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"' in html
    assert 'referrerpolicy="same-origin"' in html
    assert 'loading="lazy"' in html
    assert re.search(r"height:\s*calc\(100vh - 16rem\);\s*min-height:\s*720px", html)


def test_wrapper_header_and_actions():
    html = wrapper()
    assert '<div class="kicker">Working paper</div>' in html
    title = re.search(r'^title: "(.*)"$', QMD.read_text(), re.M).group(1)
    assert re.search(r"<h1>(.*?)</h1>", html, re.S).group(1).strip() == title
    assert re.search(r"Revision \d+ · \d{4}-\d{2}-\d{2} · Max Ghenis and Vahid Ahmadi, PolicyEngine", html)
    assert 'href="web/index.pdf"' in html
    assert 'href="../"' in html
    assert 'href="https://github.com/PolicyEngine/uk-triple-lock"' in html
    assert 'class="pe-shell pe-shell-header"' in html and 'class="pe-shell pe-shell-footer"' in html
    assert 'property="og:type" content="article"' in html
    assert '<link rel="canonical" href="https://policyengine.org/uk/triple-lock/paper/">' in html


def test_wrapper_uses_relative_urls_for_its_own_assets():
    """Everything the wrapper serves itself is relative; only shell and repo links are absolute."""
    for attr in re.findall(r'(?:src|href)="([^"]+)"', wrapper()):
        if attr.startswith("https://"):
            assert attr.startswith(("https://policyengine.org/", "https://github.com/PolicyEngine/")), attr
        else:
            assert not attr.startswith("/"), f"root-relative URL {attr} breaks outside the basePath"


def test_wrapper_figures_match_the_results():
    """Every £ figure and count in the wrapper's description is one the paper computes from the results."""
    desc = re.search(r'<p class="paper-desc">(.*?)</p>', wrapper(), re.S).group(1)
    final = D.FINAL
    expected_money = {
        D.bn(D.row(D.path("central"), final)["gross"]),
        D.bn(D.est("gross", final)["mean"]),
        D.bn(D.est("net", final)["mean"]),
        f'£{D.DWP["saving_bn"][str(final)]["nominal"]}bn',
    }
    found = {m.rstrip(",.;") for m in re.findall(r"£[\d,.]+(?:bn)?", desc)}
    assert found == expected_money, (found, expected_money)
    assert D.count(D.EV["draws"]["n"]) in desc and D.count(D.n_unique()) in desc
    assert D.fy(final) in desc


def test_paper_route_is_served_with_its_trailing_slash():
    config = (ROOT / "dashboard" / "next.config.js").read_text()
    assert "skipTrailingSlashRedirect: true" in config
    assert '{ source: "/paper/", destination: "/paper/index.html" }' in config
    proxy = (ROOT / "dashboard" / "proxy.js").read_text()
    assert 'pathname === "/paper"' in proxy and "/paper/" in proxy
    assert '"public/paper/**"' in (ROOT / "dashboard" / "eslint.config.mjs").read_text()


def test_dashboard_links_to_the_paper():
    assert "/paper/`}" in (ROOT / "dashboard" / "src" / "components" / "Dashboard.jsx").read_text()


# ── The committed render ─────────────────────────────────────────────────


def manuscript():
    return (WEB / "index.html").read_text()


def test_manuscript_and_pdf_are_under_web():
    for name in ("index.html", "index.pdf", "pe-paper.css", "pe-tokens.css"):
        assert (WEB / name).exists(), name
    html = manuscript()
    refs = re.findall(r'(?:src|href)="((?:index_files|site_libs)/[^"?#]+|pe-[a-z]+\.css)"', html)
    assert any(r.startswith("index_files/figure-html/") for r in refs), "the figures are referenced"
    for ref in refs:
        assert (WEB / ref).exists(), f"manuscript references missing {ref}"
    assert "pe-shell-header" not in html, "the raw render must not overwrite the wrapper"
    assert (WEB / "index.pdf").read_bytes()[:5] == b"%PDF-"


def text_of(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_render_is_from_the_current_results():
    """The committed render states the results' build revision and today's headline figures."""
    text = text_of(manuscript())
    assert f'revision {D.PROV["git_revision"][:7]}' in text
    final = D.FINAL
    for figure in (D.bn(D.est("gross", final)["mean"]), D.bn(D.est("net", final)["mean"]),
                   D.bn(D.row(D.path("central"), final)["gross"])):
        assert figure in text, figure
    assert "NaN" not in text and "Traceback" not in text and "Error" not in text


def test_render_names_only_the_authors():
    html = manuscript()
    assert "Max Ghenis" in html and "Vahid Ahmadi" in html
    assert "nikhil" not in html.lower() and "nikhil" not in QMD.read_text().lower()


# ── Sources ──────────────────────────────────────────────────────────────


def bib_keys():
    return set(re.findall(r"^@\w+\{([^,]+),", BIB.read_text(), re.M))


def cited_keys():
    text = re.sub(r"```.*?```", "", QMD.read_text(), flags=re.S)
    return set(re.findall(r"@([A-Za-z][\w]*\d{4}\w*|policyengine_\w+|ons_\w+|obr_\w+|dwp_\w+|rf_\w+|bbc_\w+)", text))


def test_every_citation_resolves_and_every_entry_is_cited():
    keys, cited = bib_keys(), cited_keys()
    assert cited <= keys, cited - keys
    assert keys <= cited, f"uncited entries: {keys - cited}"


def test_bibliography_entries_carry_a_url_or_doi():
    for entry in re.split(r"\n(?=@)", BIB.read_text()):
        if entry.startswith("@"):
            assert re.search(r"^\s*(url|doi)\s*=", entry, re.M), entry.splitlines()[0]


# ── The prose ────────────────────────────────────────────────────────────


def prose():
    """The manuscript's own words: no front matter, code, inline code, citations, cross-references or maths."""
    text = QMD.read_text()
    text = re.sub(r"\A---.*?\n---\n", "", text, flags=re.S)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`\{python\}[^`]*`", "", text)
    text = re.sub(r"\$\$.*?\$\$", "", text, flags=re.S)
    text = re.sub(r"\$[^$]+\$", "", text)
    text = re.sub(r"\[@[^\]]*\]", "", text)
    text = re.sub(r"@(sec|fig|tbl)-[\w-]+", "", text)
    text = re.sub(r"\{#[^}]*\}", "", text)
    return text


# Numbers the prose may type: calendar and fiscal years and ranges of them, statute references, and the fixed
# definitions it describes (the 60% relative poverty line, a 95% interval, a middle 80%, named percentiles).
ALLOWED_NUMBER = re.compile(
    r"^(?:19|20)\d\d(?:[-–](?:\d\d|(?:19|20)\d\d))?$"  # 2030, 2026-27, 2026–28, 2031–2039
    r"|^(?:60|80|95)%$|^(?:10|50|90)th$|^(?:2nd)$"
    r"|^£1$|^£0\.01bn$"  # the £1 loss threshold and unit gap; a bound the manuscript asserts
)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
STATUTE = re.compile(r"SI \d{4}/\d+|section \d+[A-Z]?|regulation \d+\(\d+\)|Schedule \d+, paragraph \d+|"
                     r"(?:Act|Regulations) \d{4}|\b\d{1,2} (?:" + MONTHS + r") \d{4}|\b12-month")


def test_prose_types_no_result_numbers():
    text = STATUTE.sub("", prose())
    tokens = re.findall(r"£?\d[\d,.]*(?:[-–]\d+)?(?:%|st|nd|rd|th|bn|m)?", text)
    bad = [t for t in tokens if not ALLOWED_NUMBER.match(t.rstrip(".,"))]
    assert not bad, f"numbers typed in the prose (compute them from the results): {bad}"


def headings():
    return [h.strip() for h in re.findall(r"^#{2,4} (.+?)(?:\s*\{[^}]*\})?$", QMD.read_text(), re.M)]


PROPER = {"Burnham", "OBR", "OBR's", "DWP", "DWP's", "PolicyEngine", "UK", "FRS", "Enhanced", "Microcosm", "State",
          "Pension", "CPI", "Winter", "Fuel", "Payment"}


def test_headings_are_sentence_case():
    for h in headings():
        for word in h.split()[1:]:
            w = word.strip(":,()")
            assert not w[:1].isupper() or w in PROPER, f"heading not in sentence case: {h!r} ({w})"


@pytest.mark.parametrize("word", ["certified", "validated", "proves", "proved", "guarantees that"])
def test_banned_words(word):
    assert word not in prose().lower()
    assert word not in text_of(manuscript()).lower()


def test_no_probability_of_an_outcome():
    """The spread across paths is described as scenarios; no chance or likelihood of an outcome is stated."""
    text = text_of(manuscript()).lower()
    for phrase in ("probability that", "chance that", "chance of", "likelihood of", "% chance", "per cent chance",
                   "is likely to save", "will probably"):
        assert phrase not in text, phrase


# ── Licensed survey data ─────────────────────────────────────────────────


def test_no_survey_record_identifier_or_weight_reaches_the_paper():
    sources = "".join(p.read_text() for p in (QMD, PAPER_SRC / "paperdata.py", PAPER_SRC / "figures.py"))
    for key in ("household_id", "household_weight", "max_household_weight", "income_change_gbp", "amounts_gbp",
                "income_change_excluding_bn"):
        assert key not in sources, key
    text = text_of(manuscript())
    for dataset in D.R["coverage"]["datasets"].values():
        w = dataset.get("max_household_weight")
        if w is not None:  # the results file should not carry it; if it does, the paper must not print it
            for form in (f"{w:,.0f}", f"{w:.0f}", f"{w:,.1f}"):
                assert form not in text


# ── Number formatting ────────────────────────────────────────────────────


@pytest.mark.parametrize("x, d, out", [(7.555, 2, "7.56"), (7.765, 2, "7.77"), (0.48334089, 2, "0.48"),
                                       (273720.09375, 0, "273,720"), (-0.0004, 1, "0.0"), (-0.0414, 2, "−0.04"),
                                       (0.05, 1, "0.1"), (0.25, 1, "0.3"), (2.5, 0, "3")])
def test_num_rounds_half_away_from_zero_on_the_shortest_repr(x, d, out):
    assert D.num(x, d) == out


@given(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False), st.integers(min_value=0, max_value=3))
def test_num_is_the_decimal_rounding_of_the_shortest_repr(x, d):
    s = D.num(x, d).replace(",", "").replace("−", "-")
    q = Decimal(repr(x)).quantize(Decimal(1).scaleb(-d), rounding="ROUND_HALF_UP")
    assert Decimal(s) == q
    assert not s.startswith("-0") or Decimal(s) != 0, "no negative zero"


@given(st.floats(min_value=-1e3, max_value=1e3, allow_nan=False))
def test_money_carries_the_sign_of_its_rounded_value(x):
    out = D.bn(x)
    rounded = Decimal(D.num(x, 2).replace(",", "").replace("−", "-"))
    assert out.startswith("−£") == (rounded < 0)
    assert out.endswith("bn") and out.lstrip("−").startswith("£")


@given(st.lists(st.text(alphabet="abc", min_size=1, max_size=3), min_size=1, max_size=5))
def test_listing_joins_every_item_once(items):
    out = D.listing(items)
    assert out.count(" and ") == (1 if len(items) > 1 else 0) or any(" and " in i for i in items)
    for item in items:
        assert item in out


def test_fiscal_year_labels():
    assert D.fy(2039) == "2039-40" and D.fy(2099) == "2099-00" and D.fy(2029) == "2029-30"
