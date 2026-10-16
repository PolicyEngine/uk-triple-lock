#!/usr/bin/env bash
# Render the working paper and sync it to the dashboard's /paper route. One pass of paper/latex/build.py writes
# both formats from the same run of the manuscript's code: the PDF in the uk-ai-study template (needs tectonic and
# pandoc on PATH) and the HTML manuscript (pandoc), so the two cannot drift apart. Quarto is not needed.
#
#   uv pip install --python .venv/bin/python matplotlib ipython   # on top of requirements-lock.txt
#   paper/render.sh
#
# The render reads only committed files (data/results.json, data/raw/*); it runs no PolicyEngine simulation. If
# data/results.json has been rebuilt, first rerun scripts/paper_rule_arithmetic.py (rule arithmetic on every path,
# no simulation), which paper/paperdata.py checks. The wrapper page, dashboard/public/paper/index.html, is written
# by hand: after a new revision, bump its ?v= value (every link uses the same one; tests/test_paper.py checks).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/.." && pwd)"
python="${PAPER_PYTHON:-$repo/.venv/bin/python}"

"$python" "$here/latex/build.py"

web="$repo/dashboard/public/paper/web"
rm -rf "$web"
mkdir -p "$web"
cp "$here/out/index.html" "$here/out/index.pdf" "$here/out/pe-tokens.css" "$here/out/pe-paper.css" "$web/"
rsync -a "$here/out/index_files/" "$web/index_files/"
echo "Synced to $web"
