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
    # The manuscript is our own same-origin render; it needs its scripts for the figure lightbox, anchors and
    # tooltips (issue #9, S1), so the sandbox allows them.
    assert 'sandbox="allow-same-origin allow-scripts allow-popups allow-popups-to-escape-sandbox"' in html
    assert 'referrerpolicy="same-origin"' in html
    assert 'loading="lazy"' in html
    assert re.search(r"height:\s*calc\(100vh - 16rem\);\s*min-height:\s*720px", html)


def test_wrapper_header_and_actions():
    html = wrapper()
    assert '<div class="kicker">Working paper</div>' in html
    title = re.search(r'^title: "(.*)"$', QMD.read_text(), re.M).group(1)
    assert re.search(r"<h1>(.*?)</h1>", html, re.S).group(1).strip() == title
    assert re.search(r"Revision \d+ · \d{4}-\d{2}-\d{2} · Vahid Ahmadi and Max Ghenis, PolicyEngine", html)
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
    """Every £ figure in the wrapper's description is one the paper computes: the Bayesian forecast's median (rounded
    and to one decimal), its £10bn threshold and the runs without 2021-23 and at the outturns' scale, the four
    scenarios and DWP's figure, with no expected value."""
    desc = re.search(r'<p class="paper-desc">(.*?)</p>', wrapper(), re.S).group(1)
    final = D.FINAL
    expected_money = {D.bn(s["values"][final][0], 1) for s in D.scenarios([final])}
    expected_money.add(f'£{D.DWP["saving_bn"][str(final)]["nominal"]}bn')
    expected_money |= {D.bn(D.b1(final), 0), D.bn(D.b1(final), 1), D.bn(D.B1_THRESHOLDS[1], 0), D.bn(D.b1_run("S7"), 1),
                       D.bn(D.b1_run("S12"), 1)}
    found = {m.rstrip(",.;") for m in re.findall(r"£[\d,.]+(?:bn)?", desc)}
    assert found == expected_money, (found, expected_money)
    assert D.count(D.N_DRAWS) in desc and D.fy(final) in desc
    assert "expected saving" not in desc


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
    """The committed render states the four scenarios' final-year figures."""
    text = text_of(manuscript())
    for s in D.scenarios([D.FINAL]):
        g, n = s["values"][D.FINAL][:2]
        assert D.bn(g, 1) in text and D.bn(n, 1) in text, s["name"]
    assert "NaN" not in text and "Traceback" not in text and "Error" not in text


def test_web_manuscript_matches_the_current_manuscript():
    """The HTML beside the PDF is built in the same pass from the same qmd: it carries this revision's figures (the
    Great Britain scenarios, the failed check) and none of the pre-Budget revision's wording."""
    text = text_of(manuscript())
    for key in ("central", "wedge", "minus", "plus"):
        assert D.bn(D.scenario_gb(key), 1) in text, key
    (stat, value, limit), = D.screen_failures()
    assert D.num(value, 3) in text and D.num(limit, 2) in text
    for stale in ("Burnham plan", "expected saving of", "typical path", "high-saving path", "Prime Minister",
                  "provisional until", "Enhanced FRS, Great Britain"):
        assert stale not in text, stale
    assert "<iframe" not in manuscript() and "site_libs/" not in manuscript()


def test_dwp_is_quoted_only_in_its_own_words():
    """The paper's reading of DWP's anchor is ours: no bracketed gloss is quoted as DWP's, and every DWP phrase the
    paper quotes is in DWP's published text."""
    src = QMD.read_text()
    assert "dwp_bracket" not in src and 'D.DWP["definition"]' not in src
    for name in ("dwp_record", "dwp_retain", "dwp_over_time"):
        assert f"{name} = re.search(" in src


def test_paper_is_scenarios_only():
    """The binding release withdrew the expected value of the microsimulation runs; the paper reads none, and no
    figure reconstructs one from the paired differences (scenario minus the unshifted paths). The paper's distribution
    comes from the Bayesian forecast (B1, data/b1), on Max's ruling of 12 November 2026, not from results.json."""
    assert "expected_value" not in D.R and "paper_rule_arithmetic" not in D.R
    src = "".join(p.read_text() for p in (QMD, PAPER_SRC / "paperdata.py", PAPER_SRC / "figures.py"))
    assert "paired_difference" not in src and "D.est(" not in src
    assert D.R["expected_value_omission"]["effective_ruling"] == "a"


def test_render_names_the_authors():
    html = manuscript()
    assert "Max Ghenis" in html and "Vahid Ahmadi" in html


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
                     r"Proposition \d|Chart \d+\.\d+|"
                     r"(?:Act|Regulations) \d{4}|\b\d{1,2} (?:" + MONTHS + r") \d{4}|\b12-month")


def test_prose_types_no_result_numbers():
    text = STATUTE.sub("", prose())
    tokens = re.findall(r"£?\d[\d,.]*(?:[-–]\d+)?(?:%|st|nd|rd|th|bn|m)?", text)
    bad = [t for t in tokens if not ALLOWED_NUMBER.match(t.rstrip(".,"))]
    assert not bad, f"numbers typed in the prose (compute them from the results): {bad}"


def headings():
    return [h.strip() for h in re.findall(r"^#{2,4} (.+?)(?:\s*\{[^}]*\})?$", QMD.read_text(), re.M)]


PROPER = {"Triple", "Lock", "OBR", "OBR's", "DWP", "DWP's", "PolicyEngine", "UK", "FRS", "Enhanced", "Microcosm", "State",
          "Pension", "CPI", "Winter", "Fuel", "Payment", "Bayesian"}


def test_headings_are_sentence_case():
    for h in headings():
        for word in h.split()[1:]:
            w = word.strip(":,()")
            assert not w[:1].isupper() or w in PROPER, f"heading not in sentence case: {h!r} ({w})"


@pytest.mark.parametrize("word", ["certified", "validated", "proves", "proved", "guarantees that"])
def test_banned_words(word):
    pattern = re.compile(r"\b" + re.escape(word) + r"\b")  # whole words: a cited title's "improved" is not "proved"
    assert not pattern.search(prose().lower())
    assert not pattern.search(text_of(manuscript()).lower())


def test_no_probability_of_an_outcome():
    """No chance or likelihood of an outcome is stated loosely. Since Max's ruling of 12 November 2026 the paper
    states the Bayesian forecast's posterior predictive probabilities, as shares of paths under the stated model and
    priors (test_b1_headline_is_conditional_and_beside_its_sensitivities); the scenarios, V1 and the failed second
    model's appendix attach none."""
    text = text_of(manuscript()).lower()
    for phrase in ("probability that", "chance that", "chance of", "likelihood of", "% chance", "per cent chance",
                   "is likely to save", "will probably"):
        assert phrase not in text, phrase



# ── Claims the paper must not make ───────────────────────────────────────


TAKE_UP_LIMITATION = "Housing Benefit and council tax reduction respond only for households already receiving them"


def test_no_claim_that_council_tax_reduction_reaches_new_claimants():
    """In the survey runs council tax reduction, like Housing Benefit, responds only for households already receiving
    it: policyengine-uk's claims_all_entitled_benefits sums reported benefits over the whole simulation, so it is false
    for every benefit unit (tests/test_model.py). An earlier draft said otherwise; neither the source nor the render
    may, and the results file's limitation must reach the paper as written."""
    for label, text in (("index.qmd", QMD.read_text()), ("render", text_of(manuscript()))):
        flat = re.sub(r"\s+", " ", text).lower()
        for phrase in ("none of several other means-tested benefits", "newly entitled pensioners can take it up",
                       "council tax reduction is claimed by", "council tax reduction, by contrast"):
            assert phrase not in flat, (label, phrase)
    assert any(TAKE_UP_LIMITATION in l for l in D.R["method_limitations"])
    assert TAKE_UP_LIMITATION in text_of(manuscript())


def test_example_pensioners_report_the_share_that_reaches_income():
    """The example pensioners' table gives, for each, the share of the lower State Pension that reaches income,
    computed from the runs and signed: a pensioner who ends better off is reported as a gain, never as "none"
    (review round 1). The wording is checked in the source, which the PDF is built from."""
    src = QMD.read_text()
    # Review round 2 renamed the row (it can show a negative share, a gain).
    assert "Change in income as a share of the change in State Pension" in src
    assert "D.signed_share(s)" in src
    assert "loses nothing" not in src
    for ex in D.examples(D.path("monthly_p50")).values():
        s = D.borne_share(ex, D.FINAL)
        if s is not None and s < -0.005:
            assert D.signed_share(s) != "none" and "income rises" in D.signed_share(s)


def test_signed_share_never_hides_a_gain():
    assert D.signed_share(-0.05).endswith("(income rises)")
    assert D.signed_share(0.0) == "none" and D.signed_share(None) == "no change in pension"
    assert D.signed_share(0.5) == "50%"


def test_scenarios_match_the_results_file():
    """The four scenarios the paper prints are the results file's own: single runs, and the draw averages with
    their 95% Monte Carlo error."""
    env = D.R["scenario_envelope"]
    sc = {s["key"]: s["values"][D.FINAL] for s in D.scenarios([D.FINAL])}
    y = str(D.FINAL)
    assert sc["central"][:2] == (D.R["central"]["run"]["saving_bn"][y]["gross"], D.R["central"]["run"]["saving_bn"][y]["net"])
    assert sc["wedge"][:2] == (env["obr_wedge"]["run"]["saving_bn"][y]["gross"], env["obr_wedge"]["run"]["saving_bn"][y]["net"])
    for v in env["paired_earnings_mean_paths"]["scenarios"].values():
        k = "plus" if v["calendar_earnings_delta"] > 0 else "minus"
        ps = v["scenario_path_set"]
        assert sc[k] == (ps["gross"][y]["mean"], ps["net"][y]["mean"], ps["gross"][y]["plus_minus_95"],
                         ps["net"][y]["plus_minus_95"])


def test_section_150a_years_and_switch_year():
    for pid in ("central", "wedge", "monthly_p50", "monthly_p90"):
        assert all(D.SWITCH < y <= D.FINAL for y in D.plan_below_earnings(pid))
        assert D.row(D.path(pid), D.SWITCH)["gross"] == 0


def test_stylised_example_is_the_rules_arithmetic():
    sys.path.insert(0, str(ROOT / "src"))
    from triple_lock import rules
    (c1, e1), (c2, e2) = D.STYLISED
    tl = rules.rates_matrix("triple_lock", [c1, c2], [e1, e2])[0]
    bp = rules.rates_matrix("burnham_2030", [c1, c2], [e1, e2])[0]
    ex = D.stylised_example()
    assert abs((1 + tl[0]) * (1 + tl[1]) - 1 - ex["tl"]) < 1e-9
    assert abs((1 + bp[0]) * (1 + bp[1]) - 1 - ex["plan"]) < 1e-9


def test_history_flags_the_rises_paid_that_differ_from_the_replay():
    differ = [r["year"] for r in D.paid_vs_replay()]
    assert D.HISTORY_RPI_YEAR in differ
    first = D.tl_record()[0]
    assert first["year"] == D.HISTORY_RPI_YEAR and first["paid"] > first["rate"]


def test_pdf_title_and_abstract_come_from_the_manuscript():
    """The PDF takes its title, keywords and JEL codes from the manuscript (none hard-coded in main.tex), and its
    abstract is the manuscript's Abstract section, carrying the headline figures: the four scenarios and DWP's, no
    expected value."""
    tex = (PAPER_SRC / "latex" / "main.tex").read_text()
    assert "\\papertitle" in tex and "Reforming the UK Triple Lock" not in tex
    assert "\\paperkeywords" in tex and "\\paperjel" in tex and "stochastic microsimulation" not in tex
    build = (PAPER_SRC / "latex" / "build.py").read_text()
    assert "ABSTRACT = abstract_of(QMD.read_text())" in build
    abstract = re.search(r"^## Abstract \{\.unnumbered\}\n\n(.*?)\n\n", QMD.read_text(), re.S | re.M).group(1)
    # Max's ruling of 12 November 2026: the abstract leads with the question, the theory and the replay, then the
    # Bayesian forecast's headline, stated conditionally and beside the runs without 2021-23 and at the outturns'
    # scale, the basis disclosure, the design history, the OBR central path and DWP's figure.
    for expr in ("bn(c_g, 1)", "dwp_nominal", "G_HIST / Y_HIST", 'bn(B1G["p50"], 0)', "B1_HALF", "bn(TEN, 0)",
                 "bn(B1_S7, 1)", "bn(B1_S12, 1)", "B1_BASIS[0]", "B1_FWD_SPAN", "B1_ERR_SPAN",
                 "two models failed tests registered before their scores", "no hold-out is clean"):
        assert expr in abstract, expr
    assert "Burnham" not in abstract and "expected saving" not in abstract


SECTIONS = ["Abstract", "Introduction", "Background and related literature", "Policy rules", "Data and method", "Results",
            "Comparison with official costings", "Discussion", "Conclusion"]


def test_sections_follow_the_dashboard():
    """The paper is in the order of an academic working paper: abstract, introduction and literature, the rules, data
    and method, results, the comparison with official costings, discussion, conclusion."""
    tops = [h.strip() for h in re.findall(r"^## (.+?)(?:\s*\{[^}]*\})?$", QMD.read_text(), re.M)]
    body = [h for h in tops if h != "References" and not h.startswith("Appendix")]
    assert body == SECTIONS, body


def test_no_lists_in_the_paper():
    """The paper is prose: no bulleted or numbered list in the manuscript, the built LaTeX or the web render (the web
    page's table of contents aside)."""
    lines = prose().split("\n")
    assert not [l for l in lines if re.match(r"^\s*(?:[-*+]|\d+[.)])\s", l)], "list in index.qmd"
    for tex in (PAPER_SRC / "latex").glob("**/*.tex"):
        text = tex.read_text()
        assert "\\begin{itemize}" not in text and "\\begin{enumerate}" not in text, tex.name
    body = re.sub(r'<nav id="TOC".*?</nav>', "", manuscript(), flags=re.S)
    assert "<ul" not in body and "<ol" not in body, "list in the web render"


def test_headline_figures_reach_the_summary_and_conclusion():
    text = text_of(manuscript())
    final = D.FINAL
    for s in D.scenarios([final]):
        g = D.bn(s["values"][final][0], 1)
        assert text.count(g) >= 2, (s["name"], g)  # results and conclusion; the abstract leads with the forecast
    assert f'£{D.DWP["saving_bn"][str(final)]["nominal"]}bn' in text


def test_no_internal_codes_or_names_in_the_paper():
    """No internal decision codes, model jargon or names of politicians or think tanks reach the prose. The dataset
    (Microcosm) is named; the Enhanced FRS appears only as the coverage check."""
    text = prose()
    for word in ("populace", "C1", "C2", "C3", "d955", "d2202", "VAR", "CRPS", "stratum", "frozen", "pre-registered",
                 "dry run", "binding test", "committed a test", "monthly_var1", "policyengine-uk-data #",
                 "policyengine-uk #", "Burnham", "Prime Minister", "Resolution Foundation", "Institute for Fiscal",
                 "IFS", "Labour"):
        assert word not in text, word
    rendered = text_of(manuscript())
    for word in ("Burnham", "Resolution Foundation", "Institute for Fiscal Studies"):
        assert word not in rendered, word


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


def test_ordinals_round_half_away_from_zero_like_the_dashboard():
    assert [D.ordinal(x) for x in (2.35, 2.5, 48.1, 89.04, 11.5, 12.5, 100.0)] == [
        "2nd", "3rd", "48th", "89th", "12th", "13th", "100th"]


def test_fiscal_year_labels():
    assert D.fy(2039) == "2039-40" and D.fy(2099) == "2099-00" and D.fy(2029) == "2029-30"


# ── Round 3 of review: the digitised Budget chart and the corrected bounds ──────────────────────────────


def test_budget_chart_readings_match_the_published_svg():
    """data/benchmarks/budget_2026_chart_5_1.csv is the digitisation of the committed SVG, and the two lines part
    when the rules can first differ."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import digitise_budget_chart as dig
    rows = dig.digitise((ROOT / "data" / "raw" / "budget-2026-chart-5.1.svg").read_text())
    for y, a, b in rows:
        tl, adj = D.CHART_5_1[y]
        assert abs(tl - a) < 5e-4 and abs(adj - b) < 5e-4, y
    assert D.chart_first_differ() == D.SWITCH + 1


def test_pension_credit_convention_is_a_lower_bound():
    """Reviewers in round 3: a guarantee that followed each rule's rise lowers existing awards, so the offsets can
    change sign and the net saving is at least, not at most, the gross less the income tax and other offsets."""
    src = QMD.read_text()
    assert "would rise by at most" not in src and "bounds the effect" not in src
    assert "at least about" in src and "gives a lower bound on the effect" in src


def test_upper_bound_is_attached_to_the_share_not_the_cash():
    src = QMD.read_text()
    budget = re.search(r"^### Robustness: four scenarios \{#sec-budget\}.*?(?=^### )", src, re.S | re.M).group(0)
    assert "This scenario bounds the share of spending saved from above" in budget
    assert "In cash the bound need not hold" in budget
    assert "a share that is an upper bound within that convention only" in src


# ── The second model, which failed its registered test ──────────────────


def _c4_appendix(src):
    return re.search(r"^## Appendix: the second model.*?(?=^## )", src, re.S | re.M).group(0)


def test_failed_second_model_is_reported_as_its_registration_requires():
    """The registration's fail clause: scenarios only; the model's distribution of G and the share once, in an
    appendix, labelled as the output of a model that failed its test; no probability statement; no cash figure; every
    score and the verdict published."""
    src = QMD.read_text()
    appendix = _c4_appendix(src)
    outside = src.replace(appendix, "")
    # Its distribution and the decomposition appear in the appendix only.
    for expr in ("c4_distribution", "C4_DECOMP", "DC[", "C4_ARITH"):
        assert expr not in outside, expr
    assert "D.c4_distribution" in appendix and "tbl-c4-dist" in appendix and "tbl-c4-scores" in appendix
    # No cash figure from the failed model.
    assert "bn(" not in appendix and "£" not in appendix and "gbp(" not in appendix
    assert "output of a model that failed its registered test" in appendix and "not a probability statement" in appendix
    assert "untested" in appendix
    # The past-years check could not be scored and is never counted as passed.
    assert "not scored" in D.C4_SCORES["verdict"]["past_years_check"]
    assert '"not scored"' in appendix and "met every scored condition but one" in outside
    # The body names the failing check and the floor-bias knife-edge; the abstract names the second model.
    assert "num(c4_value, 3)" in outside and "C4_FB" in outside and 'C4S["floor_bias_a"]' in outside
    abstract = re.search(r"^## Abstract \{\.unnumbered\}\n\n(.*?)\n\n", src, re.S | re.M).group(1)
    assert "two models failed tests registered before their scores" in abstract
    assert not D.C4_SCORES["verdict"]["passes"]


def test_failed_second_model_tables_reach_the_render():
    text = text_of(manuscript())
    d = D.c4_distribution(D.FINAL)
    for k in ("mean", "p25", "median", "p75"):
        assert D.num(100 * d[k], 2) in text, k
    (_, _, value, _), = D.c4_failures()
    assert D.num(value, 3) in text and "(fails)" in text


def test_web_appendices_are_lettered_in_order_and_links_land_on_them():
    """Each appendix takes the next letter on the web page, as in the PDF, and a cross-reference to it names that
    letter and links to its anchor."""
    src = QMD.read_text()
    ids = re.findall(r"^## Appendix: [^\n]*\{#(sec-[\w-]+) \.appendix\}", src, re.M)
    assert len(ids) >= 4
    html = manuscript()
    for i, ident in enumerate(ids):
        letter = chr(65 + i)
        head = re.search(r'<h2[^>]*id="' + ident + r'"[^>]*>(.*?)</h2>', html, re.S)
        assert head and f"Appendix {letter}:" in text_of(head.group(1)), ident
        for link in re.findall(r'<a href="#' + ident + r'"[^>]*>(.*?)</a>', html, re.S):
            assert re.match(f"Appendix {letter}(:|$)", text_of(link).strip()), (ident, link)  # the contents too


def test_second_model_sensitivities_and_post_verdict_checks_come_from_data():
    """The registered sensitivities' failed checks are read from scores.json; the single-score drops and the history
    concentration are labelled as computed after the verdict."""
    assert D.c4_sensitivity_failures("no_centre_uncertainty") == []
    raw = D.c4_sensitivity_failures("raw_errors")
    assert len(raw) == len(D.C4_SCORES["sensitivities_no_influence_on_verdict"]["raw_errors"]["would_fail_on"])
    src = QMD.read_text()
    assert "computed after the verdict, outside the registration" in src
    assert "none of them was registered" in _c4_appendix(src)
    text = text_of(manuscript())
    assert "data/c4/rule_arithmetic.json" in text and "data/c4/scores.json" in text
    assert D.num(D.C4_DROP1["min"], 3) in text and D.num(D.C4_DROP1["max"], 3) in text
    for stale in ("the upper end", "withdrawn average lies close", "pay the same on at least a quarter"):
        assert stale not in src, stale


# ── Results under stated volatility (V1), a conditional sensitivity ─────


def _v1_section(src):
    return re.search(r"^### Robustness: results under stated volatility \{#sec-v1\}.*?(?=^### )", src, re.S | re.M).group(0)


def test_v1_sits_after_the_scenarios_and_keeps_them():
    src = QMD.read_text()
    assert src.index("{#sec-b1}") < src.index("{#sec-b1-sure}") < src.index("{#sec-budget}") < src.index("{#sec-v1}") \
        < src.index("{#sec-paths}")
    assert "#| label: tbl-scenarios" in src and "#| label: fig-scenarios" in src and "{#sec-c4 .appendix}" in src


def test_v1_is_conditional_both_settings_together_and_not_from_the_failed_models():
    src = QMD.read_text()
    sec = _v1_section(src)
    prose_only = re.sub(r"```.*?```", "", sec, flags=re.S)
    # Every paragraph that states a V1 figure states the condition, and names both settings.
    for para in [p for p in prose_only.split("\n\n") if "V1G[" in p]:
        assert "vary" in para and 'V1G["a"]' in para and "V1_HOT" in para, para[:80]
    lowered = prose_only.lower()
    for word in ("expected", "probability that", "likely", "calibrated", "forecast of the saving", "c4_", "c2"):
        assert word not in lowered, word
    assert "sensitivity" in prose_only and "neither registered model" in prose_only
    # The table and both figures carry the condition in their captions; the failed models' data never enter V1.
    for label in ("tbl-v1", "fig-v1-fan", "fig-v1-dist"):
        cap = re.search(rf"#\| label: {label}\n#\| \w+-cap: \"(.*?)\"\n", sec, re.S).group(1)
        assert "no test bears on either" in cap, label
    for expr in ("C4_", "c4_distribution", "D.C2"):
        assert expr not in sec, expr
    # Since Max's ruling V1 is a robustness check: out of the abstract, and named as such in its section.
    assert "a check of robustness on that forecast" in sec


def test_v1_reaches_the_render():
    text = text_of(manuscript())
    for k in D.V1_SETTINGS:
        for q in ("p5", "p50", "p95"):
            assert D.bn(D.v1(k, D.FINAL, "gross_bn", q), 1) in text, (k, q)
    assert "Robustness: results under stated volatility" in text
    figs = sorted(p.name for p in (WEB / "index_files" / "figure-html").glob("*v1*"))
    assert any("fan" in f for f in figs) and any("dist" in f for f in figs), figs


# ── The Bayesian forecast (B1), the headline under Max's ruling of 12 November 2026 ──


def _section(src, ident):
    return re.search(r"^#{2,3} [^\n]*\{#" + ident + r"[ }].*?(?=^#{2,3} )", src, re.S | re.M).group(0)


def test_b1_headline_is_conditional_and_beside_its_sensitivities():
    """Wherever the headline median appears in prose (abstract, introduction, results, conclusion), the same
    paragraph states the condition on forecast errors and gives the runs without 2021-23 and at the outturns' scale."""
    src = QMD.read_text()
    paras = [p for p in re.sub(r"```.*?```", "", src, flags=re.S).split("\n\n") if 'bn(B1G["p50"], 0)' in p]
    assert len(paras) >= 4, len(paras)
    for p in paras:
        assert "B1_FWD_SPAN" in p and "B1_ERR_SPAN" in p, p[:80]
        assert "B1_S7" in p and "B1_S12" in p, p[:80]
    results = _section(src, "sec-b1")
    assert "B1_HALF" in results and "posterior predictive" in results
    # The net 95th percentile extrapolates the net ratio, and the prose says so.
    assert "so the net `{python} V1_HI` percentile extrapolates the ratio" in results
    # Real terms beside cash.
    assert "At the central path's levels" in results and "D.b1_real_prob(FINAL, TEN)" in results


def test_b1_discloses_its_limits():
    src = QMD.read_text()
    sure = _section(src, "sec-b1-sure")
    for expr in ("B1_BASIS[0]", "B1_BASIS[1]", "B1_CPI_NEG", "B1_CLIP", "seventh", "inform the forecast twice",
                 "neither the mean nor the largest path saving", "B1_D4"):
        assert expr in sure, expr
    method = _section(src, "sec-b1-method")
    for expr in ("D.B1_WALL_DIV[0]", "D.B1_WALL_DIV[1]", "rejection sampling", "second author's call",
                 "B1_SEEDS_CH", "B1_SEEDS_TY", "so no hold-out below is clean", "added after seeing these"):
        assert expr in method, expr
    assert D.B1_WALL_DIV == (74, 90)


def test_b1_mean_and_largest_path_never_reach_the_paper():
    src = "".join(p.read_text() for p in (QMD, PAPER_SRC / "paperdata.py", PAPER_SRC / "figures.py"))
    assert "B1[\"gross_2039_max_bn\"]" not in src and "b1_max" not in src
    with pytest.raises(ValueError):
        D.b1(D.FINAL, "gross_bn", "mean")
    text = text_of(manuscript())
    assert D.bn(D.B1["gross_2039_max_bn"], 0) not in text


def test_b1_reaches_the_render():
    text = text_of(manuscript())
    for q in ("p5", "p25", "p50", "p75", "p95"):
        assert D.num(D.b1(D.FINAL, "gross_bn", q), 1) in text, q
    assert D.bn(D.b1_run("S7"), 1) in text and D.bn(D.b1_run("S12"), 1) in text
    figs = sorted(p.name for p in (WEB / "index_files" / "figure-html").glob("*b1*"))
    assert any("fan" in f for f in figs) and any("dist" in f for f in figs), figs
    assert "appendix e: the bayesian forecast" in text.lower() and "appendix c: the second model" in text.lower()
