#!/usr/bin/env bash
# Check that the working paper is served at /uk/triple-lock/paper with no redirect loop, and that every URL its
# wrapper serves itself answers with the expected type and the checked-in file's exact bytes.
# Usage: scripts/check-paper-route.sh <origin> [public dir, default dashboard/public]
#   CI runs it against `next start`; after a deploy, run it against https://www.policyengine.org from a checkout of
#   the deployed commit. scripts/paper_links.py reads the wrapper's URLs; tests/test_paper.py applies the same rules.
set -euo pipefail

origin="${1:?usage: check-paper-route.sh <origin> [public dir]}"
origin="${origin%/}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
  ctype="$(printf '%s' "$ctype" | tr '[:upper:]' '[:lower:]')"
}

# has_type WANT: the response's media type (before any parameters such as "; charset=utf-8", spaces dropped) is WANT.
has_type() { [ "$(printf '%s' "${ctype%%;*}" | tr -d ' \t')" = "$1" ]; }

# The bare address serves the wrapper itself, byte for byte, with no redirect.
fetch "$base/paper" "$tmp/paper.html"
[ "$code" = 200 ] || fail "$base/paper gave $code${target:+ to $target}"
has_type text/html || fail "$base/paper came as '$ctype', not text/html"
cmp -s "$tmp/paper.html" "$public/paper/index.html" || fail "$base/paper is not public/paper/index.html"

# The slashed address takes exactly one redirect, to the bare address.
fetch "$base/paper/" /dev/null
[ "$code" = 308 ] && [ "$target" = "$base/paper" ] \
  || fail "$base/paper/ gave $code to '$target', not 308 to $base/paper"
fetch "$base/paper/" /dev/null -L --max-redirs 5
[ "$code" = 200 ] && [ "$hops" = 1 ] || fail "$base/paper/ ended at $code after $hops redirects"

# Every URL in the wrapper follows the rules in paper_links.py; list each local one once with its type and file.
python3 -I "$here/paper_links.py" wrapper "$tmp/paper.html" > "$tmp/links" \
  || fail "the wrapper's links break the rules above"

# Each listed URL answers 200 with no redirect, the expected type, and the checked-in file's bytes. The dashboard
# renders in the browser (its page shows a loading fallback until then), so its HTML is checked as this app's page.
while IFS=$'\t' read -r want link file; do
  fetch "$origin$link" "$tmp/file"
  [ "$code" = 200 ] || fail "$link gave $code${target:+ to $target}"
  has_type "$want" || fail "$link came as '$ctype', not $want"
  if [ "$file" = - ]; then
    python3 -I "$here/paper_links.py" dashboard "$tmp/file" "$here/../app/layout.jsx" \
      || fail "$link is not this app's dashboard page"
  else
    cmp -s "$tmp/file" "$public/$file" || fail "$link is not public/$file"
  fi
  echo "ok $link ($ctype)"
done < "$tmp/links"
echo "OK: $base/paper serves the wrapper, $base/paper/ redirects to it once, and every URL it serves itself resolves"
