#!/usr/bin/env bash
# Render the working paper (HTML, and the PDF in the uk-ai-study template) and sync it to the
# dashboard's /paper route. The PDF build needs tectonic on PATH.
#
#   uv pip install --python .venv/bin/python matplotlib jupyter   # on top of requirements-lock.txt
#   paper/render.sh
#
# The render reads only committed files (data/results.json, data/raw/*); it runs
# no PolicyEngine simulation. The wrapper page, dashboard/public/paper/index.html,
# is written by hand: after a new revision, bump its ?v= value (every link uses
# the same one; tests/test_paper.py checks).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/.." && pwd)"
python="${PAPER_PYTHON:-$repo/.venv/bin/python}"
export QUARTO_PYTHON="$python"
export JUPYTER_PREFER_ENV_PATH=1
export PATH="$(dirname "$python"):$PATH"

# Both formats in one pass: rendering them one at a time clears the other's output.
quarto render "$here"

# The published PDF is the LaTeX build in the uk-ai-study template (paper/latex/main.tex),
# not Quarto's own PDF: it replaces out/index.pdf before the sync below.
"$python" "$here/latex/build.py"
cp "$here/latex/main.pdf" "$here/out/index.pdf"

web="$repo/dashboard/public/paper/web"
rm -rf "$web"
mkdir -p "$web"
cp "$here/out/index.html" "$here/out/index.pdf" "$here/out/pe-tokens.css" "$here/out/pe-paper.css" "$web/"
rsync -a "$here/out/index_files/" "$web/index_files/"
rsync -a "$here/out/site_libs/" "$web/site_libs/"
echo "Synced to $web"
