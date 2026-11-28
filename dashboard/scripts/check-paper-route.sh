#!/usr/bin/env bash
# Check that the working paper is served at /uk/triple-lock/paper with no redirect loop, and that the three files
# its wrapper links under the basePath (manuscript, PDF, logo) are served there. The list of files at the end is
# fixed: change it when the wrapper's links change.
# Usage: scripts/check-paper-route.sh <origin> [public dir, default dashboard/public]
#   CI runs it against `next start` (scripts/check-built-app.sh). After a deploy, run it against
#   https://www.policyengine.org from a full checkout of the deployed commit: it compares what is served with the
#   checked-in files. tests/test_paper.py reads the wrapper's src and href attributes and requires each root-relative
#   one to stay under the basePath.
set -euo pipefail

origin="${1:?usage: check-paper-route.sh <origin> [public dir]}"
origin="${origin%/}"
here="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
public="${2:-$here/../public}"
base_path=/uk/triple-lock
base="$origin$base_path"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

# fetch URL BODY [curl options...]: request URL once, write the body to BODY and set code, hops, ctype (lower case)
# and target. A transfer error (refused connection, timeout, truncated body) fails the check, whatever status line
# arrived before it. -q skips any .curlrc and --globoff stops curl reading [] or {} in a URL as a pattern.
fetch() {
  local url="$1" body="$2" out rc
  shift 2
  # One field per line (no header value or URL holds a newline). The closing "end" stops $(...) from stripping the
  # newline after an empty last field, which would make the last read fail.
  out="$(curl -q --globoff -sS --max-time 30 -o "$body" \
    -w '%{http_code}\n%{num_redirects}\n%{content_type}\n%{redirect_url}\nend' "$@" "$url")" \
    || { rc=$?; fail "$url: curl exited $rc"; }
  { read -r code; read -r hops; read -r ctype; read -r target; } <<< "$out"
  ctype="$(printf '%s' "$ctype" | LC_ALL=C tr '[:upper:]' '[:lower:]')"
}

# same BODY FILE: BODY is byte for byte the checked-in public/FILE, which must exist (a sparse checkout can leave out
# public/paper/web/: run from a full checkout of the deployed commit).
same() {
  [ -f "$public/$2" ] || fail "public/$2 is missing: run from a full checkout of the commit being checked"
  cmp -s "$1" "$public/$2"
}

# has_type WANT: the response's media type is WANT: the part before any parameters such as "; charset=utf-8", with
# spaces and tabs trimmed from its ends only, so "text/html ; charset=UTF-8" passes and "application / pdf" does not.
has_type() {
  [ "$(printf '%s' "${ctype%%;*}" | LC_ALL=C sed -e 's/^[[:blank:]]*//' -e 's/[[:blank:]]*$//')" = "$1" ]
}

# The bare address serves the wrapper itself, byte for byte, with no redirect.
fetch "$base/paper" "$tmp/paper.html"
[ "$code" = 200 ] || fail "$base/paper gave $code${target:+ to $target}"
has_type text/html || fail "$base/paper came as '$ctype', not text/html"
same "$tmp/paper.html" paper/index.html || fail "$base/paper is not public/paper/index.html"

# The slashed address takes exactly one redirect, to the bare address.
fetch "$base/paper/" /dev/null
[ "$code" = 308 ] && [ "$target" = "$base/paper" ] \
  || fail "$base/paper/ gave $code to '$target', not 308 to $base/paper"
fetch "$base/paper/" /dev/null -L --max-redirs 5
[ "$code" = 200 ] && [ "$hops" = 1 ] || fail "$base/paper/ ended at $code after $hops redirects"

# The three files the wrapper links under the basePath answer there with 200, no redirect, the expected type and the
# checked-in bytes. (The manuscript's ?v= query does not change what a static file serves.)
while read -r file want; do
  fetch "$base/$file" "$tmp/file"
  [ "$code" = 200 ] || fail "$base_path/$file gave $code${target:+ to $target}"
  has_type "$want" || fail "$base_path/$file came as '$ctype', not $want"
  same "$tmp/file" "$file" || fail "$base_path/$file is not public/$file"
  echo "ok $base_path/$file ($ctype)"
done <<'FILES'
paper/web/index.html text/html
paper/web/index.pdf application/pdf
assets/logos/policyengine-white.svg image/svg+xml
FILES
echo "OK: $base/paper serves the wrapper, $base/paper/ redirects to it once," \
  "and the manuscript, PDF and logo are served"
