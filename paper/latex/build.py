"""Build the working paper as LaTeX in the uk-ai-study template and compile it.

Runs the Python in ``paper/index.qmd`` (the same code Quarto runs, reading only
``data/results.json`` and ``data/raw``), so every number is still computed, not
typed. Inline ``{python}`` expressions are evaluated in place, tables from
``md_table`` become booktabs tables, and each figure chunk is saved as a PNG.
Pandoc turns the result into LaTeX, one file per section under ``sections/``,
which ``main.tex`` (the uk-ai-study layout) inputs. Tectonic compiles it.

    uv run --with matplotlib --with ipython python paper/latex/build.py
"""

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent
OUT = PAPER / "out"
WEB_FIGS = OUT / "index_files" / "figure-html"
QMD = PAPER / "index.qmd"
SECTIONS = HERE / "sections"
FIGURES = HERE / "figures"

CHUNK = re.compile(r"^```\{python\}\n(.*?)^```\n", re.S | re.M)
INLINE = re.compile(r"`\{python\}\s+([^`]+)`")

# At most 150 words. Every number is evaluated from the paper's own code; tests/test_paper.py checks that the
# abstract carries the same headline figures as the manuscript's summary.
ABSTRACT = (
    "We use stochastic microsimulation to cost the Burnham plan, which from April "
    "`{python} SWITCH` would raise the State Pension by at least the higher of CPI and `{python} FLOOR`, topped up "
    "to keep what we read as its `{python} fy(SWITCH - 1)` value relative to earnings. PolicyEngine UK runs on `{python} N_RUNS` of `{python} N_PATHS` price and earnings paths centred "
    "on the OBR forecast give an expected `{python} fy(FINAL)` saving of `{python} bn(g_final['mean'], 1)` in pension "
    "spending and `{python} bn(n_final['mean'], 1)` after tax and benefits; other calibrations and model "
    "versions give `{python} bn(model_lo, 1)` to `{python} bn(model_hi, 1)`, mostly less. The OBR's central "
    "forecast alone gives `{python} bn(c_final['gross'], 1)`; its long-term assumption that the triple lock outpaces "
    "earnings gives `{python} bn(wedge['gross'], 1)`. For Great Britain we find `{python} bn(gb_final['mean'], 1)` "
    "(`{python} bn(gb_scaled, 1)` scaled for survey coverage), against DWP's £`{python} dwp_nominal`bn. About "
    "`{python} pct(lose_final['mean'], 0)` of households have less income, by "
    "`{python} gbp(t_final['mean_loss'])` a year on a typical path; pensioner poverty after housing costs "
    "is up to `{python} num(max(pov_typ_abs, pov_typ_rel), 1)` points higher. Results are provisional until the "
    "October 2026 Budget."
)


def split_front_matter(text):
    assert text.startswith("---\n")
    end = text.index("\n---\n", 4)
    return text[end + 5 :]


def front_matter_field(text, key):
    """A top-level string field of the qmd's YAML front matter (title, subtitle), so the PDF and HTML share them."""
    head = text[4 : text.index("\n---\n", 4)]
    m = re.search(rf'^{key}:\s*"(.*)"\s*$', head, re.M)
    return m.group(1) if m else ""


def write_title(qmd_text):
    """title.tex: the manuscript's own title and subtitle, in its sentence case."""
    title = latex_escape(front_matter_field(qmd_text, "title"))
    subtitle = latex_escape(front_matter_field(qmd_text, "subtitle"))
    (HERE / "title.tex").write_text(f"\\newcommand{{\\papertitle}}{{{title}}}\n"
                                    f"\\newcommand{{\\papersubtitle}}{{{subtitle}}}\n")


CITE = re.compile(r"@([A-Za-z][\w]*\d{4}\w*|[a-z]+_[a-z_]+\d*)")


def latex_escape(text):
    text = str(text)
    # A citation key in a table cell ("@dwp_uprating2026") prints as an author-year citation.
    cites = []
    text = CITE.sub(lambda m: cites.append(m.group(1)) or f"CITE{len(cites) - 1}CITE", text)
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
                 ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"),
                 ("^", r"\textasciicircum{}")]:
        text = text.replace(a, b)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    text = re.sub(r"(?<![\\w])\*(.+?)\*", r"\\emph{\1}", text)
    text = re.sub(r"CITE(\d+)CITE", lambda m: "\\citet{" + cites[int(m.group(1))] + "}", text)
    return text.replace("–", "--").replace("—", "---")


# A header's trailing unit in parentheses: "Gross (£bn)", "Triple lock (£ a year)", "Change (points)".
UNIT = re.compile(r"^(.+?)\s+\(([^()]*(?:£|%|bn|points|a year|million)[^()]*)\)$")


def split_caption(cap):
    """uk-ai-study tables: a short caption (the first sentence) and the rest as a note under the table."""
    m = re.search(r"(?<=[a-z0-9)])\. (?=[A-Z'])", cap)
    if not m:
        return cap, ""
    return cap[: m.start() + 1], cap[m.end():]


def table_to_latex(lines, cap, label, note=""):
    """A pipe table as a booktabs float in the uk-ai-study layout: caption above, units in a second header row
    (a header's trailing parenthesis, "Gross (£bn)"), a rule above a bold total row, and a footnote-size note below.

    Columns take their data's width; headers longer than the data wrap onto two
    or three lines; only long free-text columns wrap (tabularx X). Anything still
    wider than the text is scaled down to it.
    """
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines]
    head, rule, body = rows[0], rows[1], rows[2:]
    align = ["r" if r.endswith(":") and not r.startswith(":") else "l" for r in rule]
    body_w = [max([len(str(r[i])) for r in body if i < len(r)] or [1]) for i in range(len(head))]
    wrap = [a == "l" and w > 40 for a, w in zip(align, body_w)]
    if any(wrap):
        # Once one text column wraps, every other long text column shares the width with it, so no single column
        # is left narrow while another has room to spare.
        wrap = [a == "l" and (x or w > 15) for a, w, x in zip(align, body_w, wrap)]
    wide = sum(body_w) + 2 * len(body_w) > 90
    size = "\\footnotesize" if wide else "\\small"
    spec = "".join(">{\\raggedright\\arraybackslash}X" if x else a for a, x in zip(align, wrap))

    def header(text, a, w, x):
        cell = latex_escape(text)
        if x or len(text) <= w + 2:
            return cell
        # Wide enough that the header takes at most two lines.
        width = max(w, -(-len(text) // 2) + 3) * 0.55
        side = "\\raggedleft" if a == "r" else "\\raggedright"
        return f"\\parbox[b]{{{width:.1f}em}}{{{side} {cell}}}"

    # "2034-35: Gross" headers share a spanner ("2034-35") over their columns, with a rule under it.
    groups = [h.split(": ", 1)[0] if ": " in h else "" for h in head]
    head = [h.split(": ", 1)[1] if ": " in h else h for h in head]
    units = [UNIT.match(h) for h in head]
    if any(units):
        head = [m.group(1) if m else h for m, h in zip(units, head)]
        units = [m.group(2) if m else "" for m in units]
    heads = [header(h, a, w, x) for h, a, w, x in zip(head, align, body_w, wrap)]
    tex = ["```{=latex}", "\\begin{table}[!htbp]", "\\centering" + size]
    if cap:
        tex.append(f"\\caption{{{cap}}}")
    if label:
        tex.append(f"\\label{{{label}}}")
    if any(wrap):
        tex += [f"\\begin{{tabularx}}{{\\linewidth}}{{{spec}}}"]
        end = "\\end{tabularx}"
    else:
        # Shrink only when wider than the text; never enlarge a narrow table.
        tex += [f"\\fitwidth{{\\begin{{tabular}}{{{spec}}}"]
        end = "\\end{tabular}}"
    tex.append("\\toprule")
    if any(groups):
        cells, rules, i = [], [], 0
        while i < len(groups):
            j = i
            while j + 1 < len(groups) and groups[j + 1] == groups[i]:
                j += 1
            if groups[i]:
                cells.append(f"\\multicolumn{{{j - i + 1}}}{{c}}{{{latex_escape(groups[i])}}}")
                rules.append(f"\\cmidrule(lr){{{i + 1}-{j + 1}}}")
            else:
                cells += [""] * (j - i + 1)
            i = j + 1
        tex += [" & ".join(cells) + " \\\\", "".join(rules)]
    tex += [" & ".join(heads) + " \\\\"]
    if any(units):
        tex.append(" & ".join(latex_escape(f"({u})") if u else "" for u in units) + " \\\\")
    tex.append("\\midrule")
    sep = "\\addlinespace[0.5em]" if any(wrap) else ""
    # A first column that names a few groups of rows is printed once per group, with space between groups.
    firsts = [r[0] for r in body]
    if len(body) > 6 and len(set(firsts)) <= len(body) / 3:
        body = [[""] + r[1:] if i and r[0] == firsts[i - 1] else r for i, r in enumerate(body)]
        group = ["\\addlinespace[0.4em]" if i and r[0] else "" for i, r in enumerate(body)]
    else:
        group = [""] * len(body)
    for i, r in enumerate(body):
        if group[i]:
            tex.append(group[i])
        total = i == len(body) - 1 and i > 0 and r[0].startswith("**")
        tex.append(("\\midrule " if total else sep if i else "") + " & ".join(latex_escape(c) for c in r) + " \\\\")
    tex += ["\\bottomrule", end]
    if note:
        tex += ["", "\\vspace{0.4em}", f"\\parbox{{0.92\\linewidth}}{{\\footnotesize\\emph{{Note:}} {note}}}"]
    tex += ["\\end{table}", "```"]
    return "\n".join(tex)


def table_to_html_md(lines, cap, label, note=""):
    """A pipe table for the web page: an anchored caption above, the rows (spanner prefixes kept in the header,
    "2034-35: Gross"), and the note below."""
    out = [f"::: {{.table-caption}}\n[]{{#{label}}}**@{label}**: {cap}\n:::\n" if label else "", "\n".join(lines)]
    if note:
        out.append(f"\n::: {{.table-note}}\n*Note:* {note}\n:::")
    return "\n".join(out)


def paper_style(fig):
    """Paper figures: the caption is the title. A single panel loses its title; panels of a
    multi-panel figure keep a short, regular-weight label (the captions name them)."""
    axes = [ax for ax in fig.axes if ax.get_visible() and ax.has_data()]
    for ax in axes:
        title = ax.get_title(loc="left") or ax.get_title()
        if len(axes) == 1:
            ax.set_title("", loc="left")
            ax.set_title("")
        elif title:
            ax.set_title("", loc="left")
            ax.set_title("", loc="right")
            ax.set_title(title, fontweight="normal", fontsize=plotstyle.PANEL_TITLE)
    if fig._suptitle is not None and len(axes) == 1:
        fig._suptitle.set_text("")
    return len(axes)


# The conclusion is a section of the manuscript itself, in both formats.
CONCLUSION = ""


def run_chunks(body):
    """Execute chunks in order, returning markdown with outputs and values filled in."""
    os.chdir(PAPER)
    sys.path.insert(0, str(PAPER))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import IPython.display as ipd
    global plotstyle
    import plotstyle

    shown = []

    def display(obj):
        shown.append(obj.data if hasattr(obj, "data") else str(obj))

    ipd.display = display
    ns = {"__name__": "__paper__"}
    out, pos = [], 0
    html = []  # the same manuscript for the web page: PNG figures and pipe tables
    WEB_FIGS.mkdir(parents=True, exist_ok=True)

    def fill(text):
        return INLINE.sub(lambda m: str(eval(m.group(1), ns)), text)

    for m in CHUNK.finditer(body):
        text = fill(body[pos : m.start()])
        out.append(text)
        html.append(text)
        pos = m.end()
        code = m.group(1)
        opts = dict(re.findall(r"^#\|\s*([\w-]+):\s*(.*)$", code, re.M))
        label = opts.get("label", "").strip().strip('"')
        shown.clear()
        plt.close("all")
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(code, f"<chunk {label}>", "exec"), ns)
        ns["display"] = display
        cap = opts.get("fig-cap") or opts.get("tbl-cap")
        if cap:
            cap = fill(cap.strip().strip('"').strip("'"))
        if plt.get_fignums():
            FIGURES.mkdir(exist_ok=True)
            fig = plt.gcf()
            paper_style(fig)
            # Vector PDF, drawn at the size it prints (plotstyle), so it is placed at its own width: type
            # prints at its set size. Only a figure wider than the text is scaled down to it.
            fig.savefig(FIGURES / f"{label}.pdf")
            fig.savefig(WEB_FIGS / f"{label}-output-1.png", dpi=200)
            html.append(f"\n![{cap or ''}](index_files/figure-html/{label}-output-1.png){{#{label}}}\n\n")
            box = fig.get_tightbbox(fig.canvas.get_renderer())
            width = min(box.width + 2 * plt.rcParams["savefig.pad_inches"], plotstyle.TEXTWIDTH)
            plt.close("all")
            out.append(f"\n![{cap or ''}](figures/{label}.pdf){{#{label} width={width:.2f}in}}\n\n")
        for md in shown:
            lines = md.split("\n")
            if cap and label.startswith("tbl-") and any(l.startswith("|") for l in lines):
                # Caption straight after the table rows, before any text the chunk adds.
                start = next(i for i, l in enumerate(lines) if l.startswith("|"))
                end = start
                while end < len(lines) and lines[end].startswith("|"):
                    end += 1
                pre = "\n".join(lines[:start]).strip()
                rest = "\n".join(lines[end:]).strip()
                short, note = split_caption(cap)
                note = " ".join(t for t in (note, rest) if t)
                note_tex = to_latex_inline(note) if note else ""
                out.append(f"\n{pre}\n\n{table_to_latex(lines[start:end], to_latex_inline(short), label, note_tex)}\n\n")
                html.append(f"\n{pre}\n\n{table_to_html_md(lines[start:end], short, label, note)}\n\n")
                cap = None
            else:
                out.append(f"\n{md}\n\n")
                html.append(f"\n{md}\n\n")
    out.append(fill(body[pos:]))
    html.append(fill(body[pos:]))
    return "".join(out), fill(ABSTRACT), fill(CONCLUSION), "".join(html)


HEAD = re.compile(r"^(#{2,3}) (.+?)\s*(\{[^}]*\})?\s*$", re.M)


def restructure(md, conclusion=""):
    """The manuscript's sections in its own order, without the HTML-only summary and the reference list (natbib
    prints it), and with LaTeX's appendix switch before the first section marked .appendix."""
    tops = [m for m in HEAD.finditer(md) if m.group(1) == "##"]
    out = [md[: tops[0].start()] if tops else md]
    appendix = False
    for i, m in enumerate(tops):
        end = tops[i + 1].start() if i + 1 < len(tops) else len(md)
        title, attrs = m.group(2).strip(), m.group(3) or ""
        if title in ("Summary", "References"):
            continue
        body = md[m.end():end]
        if ".appendix" in attrs:
            if not appendix:
                out.append("\n```{=latex}\n\\appendix\n```\n")
                appendix = True
            title = re.sub(r"^Appendix:\s*", "", title)
            title = title[0].upper() + title[1:]
            attrs = attrs.replace(" .appendix", "").replace(".appendix", "")
        out.append(f"\n## {title} {attrs}\n{body}")
    return "".join(out)


KINDS = {"sec": "Section", "fig": "Figure", "tbl": "Table", "eq": "Equation"}
XREF = re.compile(r"@((sec|fig|tbl|eq)-[A-Za-z0-9_-]*[A-Za-z0-9])")


def xrefs(md):
    """Quarto cross-references to LaTeX: '@tbl-rule' -> 'Table~\\ref{tbl-rule}'."""
    return XREF.sub(lambda m: f"{KINDS[m.group(2)]}\u00a0\\ref{{{m.group(1)}}}", md)


def to_latex_inline(md):
    """Markdown (a caption) to inline LaTeX, citations, cross-references and emphasis included."""
    md = xrefs(md)
    tex = subprocess.run(["pandoc", "--from=markdown", "--to=latex", "--natbib", "--wrap=none"],
                         input=md, capture_output=True, text=True, check=True).stdout.strip()
    return tex


def to_latex(md):
    """Quarto markdown to LaTeX via pandoc, with cross-references and natbib citations."""
    md = re.sub(r"^::: \{\.summary-box\}\n", "", md, flags=re.M)
    md = re.sub(r"^::: \{#refs\}\n:::\n", "", md, flags=re.M)
    md = re.sub(r"^:::[ \t]*\n", "", md, flags=re.M)
    md = xrefs(md)
    tex = subprocess.run(
        ["pandoc", "--from=markdown+pipe_tables+implicit_figures", "--to=latex", "--natbib",
         "--top-level-division=section", "--shift-heading-level-by=-1", "--wrap=preserve"],
        input=md, capture_output=True, text=True, check=True,
    ).stdout
    # Tables float with their caption above, as in the uk-ai-study paper.
    tex = tex.replace("\\begin{longtable}", "{\\small\\begin{longtable}").replace(
        "\\end{longtable}", "\\end{longtable}}"
    )
    return tex


FLOAT = re.compile(r"\\begin\{(table|figure)\}.*?\\end\{\1\}\n?", re.S)


def floats_after_first_mention(tex):
    """Move any figure or table that comes before its first mention to just after that paragraph."""
    for _ in range(50):
        for m in FLOAT.finditer(tex):
            label = re.search(r"\\label\{([^}]+)\}", m.group(0))
            ref = label and re.search(r"\\ref\{" + re.escape(label.group(1)) + r"\}", tex)
            if ref and ref.start() > m.end():
                end = tex.find("\n\n", ref.end())
                end = len(tex) if end < 0 else end
                tex = tex[:m.start()] + tex[m.end():end] + "\n\n" + m.group(0) + tex[end:]
                break
        else:
            return tex
    return tex


def write_sections(tex, abstract_md):
    """Summary becomes the abstract; every other top-level section its own file."""
    if SECTIONS.exists():
        shutil.rmtree(SECTIONS)
    SECTIONS.mkdir()
    tex = re.sub(r"\\begin\{(itemize|enumerate)\}\n(\\tightlist\n)?", "", tex)
    tex = re.sub(r"\n?\\end\{(itemize|enumerate)\}", "", tex)
    tex = re.sub(r"^\\item\n\s*", "\n", tex, flags=re.M)
    tex = floats_after_first_mention(tex)
    main_tex, _, appendix_tex = tex.partition("\\appendix")
    # Appendix tables stack in order where they are introduced, with no float gaps between them.
    appendix_tex = appendix_tex.replace("\\begin{table}[!htbp]", "\\begin{table}[H]")
    appendix_start = None
    parts = re.split(r"(?=^\\section)", main_tex, flags=re.M)
    parts += [None] + re.split(r"(?=^\\section)", appendix_tex, flags=re.M)
    names = []
    for part in parts:
        if part is None:
            appendix_start = len(names)
            continue
        head = re.match(r"\\section\*?\{([^}]*)\}", part)
        if not head:
            continue
        title = head.group(1)
        body = part[head.end():]
        if title.startswith("Summary"):
            part = part.replace("\\addcontentsline{toc}{section}{Summary}", "")
        if title.startswith("References"):
            continue
        part = part.rstrip() + "\n\n\\FloatBarrier\n"
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40]
        (SECTIONS / f"{len(names) + 1:02d}_{slug}.tex").write_text(part)
        names.append(f"{len(names) + 1:02d}_{slug}")
    abstract = to_latex(abstract_md).strip()
    words = len(re.sub(r"\\[a-z]+\{[^}]*\}", "", abstract_md).split())
    assert words <= 150, f"abstract has {words} words"
    (HERE / "abstract.tex").write_text(abstract + "\n")
    inputs = [f"\\input{{sections/{n}}}\n" for n in names]
    (HERE / "sections.tex").write_text("".join(inputs[:appendix_start]))
    (HERE / "appendix.tex").write_text("\\appendix\n" + "".join(inputs[appendix_start:]))


# apalike labels an entry with no author by its key ("spc, 2002"); UK legislation
# is cited by its title instead, as the Quarto (CSL) build shows it.
def with_legislation_authors(bib):
    def fix(m):
        body = m.group(3)
        if re.search(r"^\s*(author|editor)\s*=", body, re.M):
            return m.group(0)
        title = re.search(r"^\s*title\s*=\s*\{\{?(.*?)\}?\},?\s*$", body, re.M)
        if not title:
            return m.group(0)
        # The title becomes the author (so the entry sorts and cites by it) and is not printed twice.
        body = body.replace(title.group(0), "")
        return f"@{m.group(1)}{{{m.group(2)},\n  author = {{{{{title.group(1)}}}}},{body}\n}}"

    return re.sub(r"@(\w+)\{([^,]+),(.*?)\n\}", fix, bib, flags=re.S)


WEB_HEAD = re.compile(r"^(#{2,3}) (.+?)\s*(\{[^}]*\})?\s*$", re.M)


def number_for_web(md):
    """Number sections, figures and tables as the PDF does, and turn Quarto cross-references into links."""
    names, sec, sub, appendix = {}, 0, 0, False
    lines = []
    for line in md.split("\n"):
        m = WEB_HEAD.match(line)
        if m:
            level, title, attrs = m.group(1), m.group(2), m.group(3) or ""
            ident = re.search(r"#([\w-]+)", attrs)
            if ".appendix" in attrs:
                appendix, sec, sub = True, 0, 0
            if ".unnumbered" not in attrs:
                if level == "##":
                    sec, sub = sec + 1, 0
                    num = chr(64 + sec) if appendix else str(sec)
                else:
                    sub += 1
                    num = f"{chr(64 + sec) if appendix else sec}.{sub}"
                if appendix and level == "##":
                    title = re.sub(r"^Appendix:\s*", "", title)
                    title = f"Appendix {num}: {title[0].upper() + title[1:]}"
                else:
                    title = f"{num} {title}"
                if ident:
                    names[ident.group(1)] = ("Appendix " if appendix and level == "##" else "Section ") + num
            line = f"{level} {title} {attrs}".rstrip()
        lines.append(line)
    md = "\n".join(lines)
    for kind, word in (("fig", "Figure"), ("tbl", "Table")):
        found = re.findall(r"\{#(" + kind + r"-[\w-]+)\}", md)
        for i, label in enumerate(dict.fromkeys(found), 1):
            names[label] = f"{word} {i}"
    md = re.sub(r"!\[(.*?)\]\((index_files/[^)]+)\)\{#(fig-[\w-]+)\}",
                lambda m: f"![**{names[m.group(3)]}**: {m.group(1)}]({m.group(2)}){{#{m.group(3)}}}", md, flags=re.S)
    md = re.sub(r"\*\*@(tbl-[\w-]+)\*\*:", lambda m: f"**{names[m.group(1)]}**:", md)
    return XREF.sub(lambda m: f"[{names.get(m.group(1), m.group(1))}](#{m.group(1)})", md)


def write_html(qmd_text, md):
    """The web manuscript: pandoc's standalone HTML with the paper's own CSS, citations by citeproc."""
    OUT.mkdir(exist_ok=True)
    md = number_for_web(md)
    meta = ["--metadata", f"title={front_matter_field(qmd_text, 'title')}",
            "--metadata", "author=Max Ghenis, PolicyEngine", "--metadata", "author=Vahid Ahmadi, PolicyEngine",
            "--metadata", f"date={re.search(r'^date: (.+)$', qmd_text, re.M).group(1).strip()}",
            "--metadata", "link-citations=true", "--metadata", "lang=en-GB"]
    if front_matter_field(qmd_text, "subtitle"):
        meta += ["--metadata", f"subtitle={front_matter_field(qmd_text, 'subtitle')}"]
    subprocess.run(["pandoc", "--from=markdown+pipe_tables+implicit_figures", "--to=html5", "--standalone", "--toc",
                    "--toc-depth=2", "--citeproc", f"--bibliography={PAPER / 'references.bib'}", "--mathml",
                    "--css=pe-tokens.css", "--css=pe-paper.css", *meta, "-o", str(OUT / "index.html")],
                   input=md, text=True, check=True)
    for css in ("pe-tokens.css", "pe-paper.css"):
        shutil.copy(PAPER / css, OUT / css)


def main():
    text = QMD.read_text()
    write_title(text)
    if WEB_FIGS.exists():
        shutil.rmtree(WEB_FIGS)
    md, abstract_md, conclusion_md, html_md = run_chunks(split_front_matter(text))
    write_html(text, html_md)
    md = restructure(md, conclusion_md)
    write_sections(to_latex(md), abstract_md)
    (HERE / "references.bib").write_text(with_legislation_authors((PAPER / "references.bib").read_text()))
    subprocess.run(["tectonic", "--keep-logs", "main.tex"], cwd=HERE, check=True)
    shutil.copy(HERE / "main.pdf", OUT / "index.pdf")
    print(HERE / "main.pdf", OUT / "index.html")


if __name__ == "__main__":
    main()
