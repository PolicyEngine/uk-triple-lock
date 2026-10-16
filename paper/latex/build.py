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
QMD = PAPER / "index.qmd"
SECTIONS = HERE / "sections"
FIGURES = HERE / "figures"

CHUNK = re.compile(r"^```\{python\}\n(.*?)^```\n", re.S | re.M)
INLINE = re.compile(r"`\{python\}\s+([^`]+)`")

# At most 150 words. Every number is evaluated from the paper's own code.
ABSTRACT = (
    "The UK State Pension triple lock raises the pension each year by the highest of CPI inflation, earnings growth "
    "and `{python} FLOOR`, and keeps every gain. We estimate what the Burnham plan, which from `{python} SWITCH` keeps "
    "the protection against prices and the floor but tracks earnings over time, would save against the triple lock "
    "(current law), and who would be affected. We run both rules through PolicyEngine UK on `{python} N_PATHS` simulated "
    "paths of prices and earnings centred on the OBR's forecast. The expected saving in `{python} fy(FINAL)` is "
    "`{python} bn(g_final['mean'], 1)` in State Pension spending and `{python} bn(n_final['mean'], 1)` after tax and "
    "benefits respond, against `{python} bn(c_final['gross'], 1)` on the OBR's central forecast alone; the middle "
    "80% of paths runs from `{python} bn(spread80[0], 1)` to `{python} bn(spread80[1], 1)`. About "
    "`{python} pct(lose_final['mean'], 0)` of households, nearly all with a pensioner, have less income. The results "
    "are provisional until the binding test on the Budget forecast."
)


def split_front_matter(text):
    assert text.startswith("---\n")
    end = text.index("\n---\n", 4)
    return text[end + 5 :]


def latex_escape(text):
    text = str(text)
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
                 ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"),
                 ("^", r"\textasciicircum{}")]:
        text = text.replace(a, b)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    text = re.sub(r"(?<![\\w])\*(.+?)\*", r"\\emph{\1}", text)
    return text.replace("–", "--").replace("—", "---")


def table_to_latex(lines, cap, label):
    """A pipe table as a booktabs float.

    Columns take their data's width; headers longer than the data wrap onto two
    or three lines; only long free-text columns wrap (tabularx X). Anything still
    wider than the text is scaled down to it.
    """
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines]
    head, rule, body = rows[0], rows[1], rows[2:]
    align = ["r" if r.endswith(":") and not r.startswith(":") else "l" for r in rule]
    body_w = [max([len(str(r[i])) for r in body if i < len(r)] or [1]) for i in range(len(head))]
    wrap = [a == "l" and w > 40 for a, w in zip(align, body_w)]
    wide = sum(body_w) + 2 * len(body_w) > 90
    size = "\\footnotesize" if wide else "\\small"
    spec = "".join(">{\\raggedright\\arraybackslash}X" if x else a for a, x in zip(align, wrap))

    def header(text, a, w, x):
        cell = latex_escape(text)
        if x or len(text) <= w + 2:
            return cell
        # Wide enough that the header takes at most two lines.
        width = max(w, -(-len(text) // 2) + 2) * 0.5
        side = "\\raggedleft" if a == "r" else "\\raggedright"
        return f"\\parbox[b]{{{width:.1f}em}}{{{side} {cell}}}"

    heads = [header(h, a, w, x) for h, a, w, x in zip(head, align, body_w, wrap)]
    tex = ["```{=latex}", "\\begin{table}[htbp]", "\\centering" + size]
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
    tex += ["\\toprule", " & ".join(heads) + " \\\\", "\\midrule"]
    sep = "\\addlinespace[0.5em]" if any(wrap) else ""
    tex += [(sep if i else "") + " & ".join(latex_escape(c) for c in r) + " \\\\"
            for i, r in enumerate(body)]
    tex += ["\\bottomrule", end, "\\end{table}", "```"]
    return "\n".join(tex)


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
            ax.set_title(title, loc="left", fontweight="normal", fontsize=8.5)
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

    shown = []

    def display(obj):
        shown.append(obj.data if hasattr(obj, "data") else str(obj))

    ipd.display = display
    ns = {"__name__": "__paper__"}
    out, pos = [], 0

    def fill(text):
        return INLINE.sub(lambda m: str(eval(m.group(1), ns)), text)

    for m in CHUNK.finditer(body):
        out.append(fill(body[pos : m.start()]))
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
            path = FIGURES / f"{label}.png"
            panels = paper_style(plt.gcf())
            plt.gcf().savefig(path, dpi=200, bbox_inches="tight")
            plt.close("all")
            # Single-panel figures at 85% of the text width; multi-panel ones full width.
            width = " width=85%" if panels == 1 else ""
            out.append(f"\n![{cap or ''}](figures/{label}.png){{#{label}{width}}}\n\n")
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
                cap_tex = to_latex_inline(cap)
                out.append(f"\n{pre}\n\n{table_to_latex(lines[start:end], cap_tex, label)}\n\n{rest}\n\n")
                cap = None
            else:
                out.append(f"\n{md}\n\n")
    out.append(fill(body[pos:]))
    return "".join(out), fill(ABSTRACT), fill(CONCLUSION)


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


def to_latex_inline(md):
    """Markdown (a caption) to inline LaTeX, citations and emphasis included."""
    tex = subprocess.run(["pandoc", "--from=markdown", "--to=latex", "--natbib", "--wrap=none"],
                         input=md, capture_output=True, text=True, check=True).stdout.strip()
    return tex


def to_latex(md):
    """Quarto markdown to LaTeX via pandoc, with cross-references and natbib citations."""
    md = re.sub(r"^::: \{\.summary-box\}\n", "", md, flags=re.M)
    md = re.sub(r"^::: \{#refs\}\n:::\n", "", md, flags=re.M)
    md = re.sub(r"^:::[ \t]*\n", "", md, flags=re.M)
    kinds = {"sec": "Section", "fig": "Figure", "tbl": "Table", "eq": "Equation"}
    md = re.sub(
        r"@((sec|fig|tbl|eq)-[A-Za-z0-9_-]+)",
        lambda m: f"{kinds[m.group(2)]}\u00a0\\ref{{{m.group(1)}}}",
        md,
    )
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
        return f"@{m.group(1)}{{{m.group(2)},\n  author = {{{{{title.group(1)}}}}},{body}\n}}"

    return re.sub(r"@(\w+)\{([^,]+),(.*?)\n\}", fix, bib, flags=re.S)


def main():
    md, abstract_md, conclusion_md = run_chunks(split_front_matter(QMD.read_text()))
    md = restructure(md, conclusion_md)
    write_sections(to_latex(md), abstract_md)
    (HERE / "references.bib").write_text(with_legislation_authors((PAPER / "references.bib").read_text()))
    subprocess.run(["tectonic", "--keep-logs", "main.tex"], cwd=HERE, check=True)
    print(HERE / "main.pdf")


if __name__ == "__main__":
    main()
