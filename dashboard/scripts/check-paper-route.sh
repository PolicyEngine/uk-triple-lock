#!/usr/bin/env bash
# Check that the working paper is served at /uk/triple-lock/paper with no redirect loop, and that every URL its
# wrapper serves itself answers with the expected type and the checked-in file's exact bytes.
# Usage: scripts/check-paper-route.sh <origin> [public dir, default dashboard/public]
#   CI runs it against `next start`; after a deploy, run it against https://www.policyengine.org from a checkout of
#   the deployed commit. scripts/paper_links.py reads the wrapper's URLs; tests/test_paper.py applies the same rules.
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

# same BODY FILE: BODY is byte for byte the checked-in public/FILE, which must exist (the hub's sparse checkouts leave
# out public/paper/web/: run from a full checkout of the deployed commit).
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

# Every URL in the wrapper follows the rules in paper_links.py; list each local one once with its type and file.
python3 -I "$here/paper_links.py" wrapper "$tmp/paper.html" > "$tmp/links" \
  || fail "the wrapper's links break the rules above"

# Each listed URL answers 200 with no redirect, the expected type, and the checked-in file's bytes. The dashboard is
# built, not checked in: its page must be this app's (the layout's title and its link back to the paper), and each
# script it loads from the basePath's /_next/static/ must answer 200 as JavaScript.
while IFS=$'\t' read -r want link file; do
  fetch "$origin$link" "$tmp/file"
  [ "$code" = 200 ] || fail "$link gave $code${target:+ to $target}"
  has_type "$want" || fail "$link came as '$ctype', not $want"
  echo "ok $link ($ctype)"
  if [ "$file" = - ]; then
    python3 -I "$here/paper_links.py" dashboard "$tmp/file" "$here/../app/layout.jsx" > "$tmp/scripts" \
      || fail "$link is not this app's dashboard page"
    while IFS= read -r script; do
      fetch "$origin$script" "$tmp/script"
      [ "$code" = 200 ] || fail "$script gave $code${target:+ to $target}"
      has_type application/javascript || has_type text/javascript || fail "$script came as '$ctype', not JavaScript"
      echo "ok $script ($ctype)"
    done < "$tmp/scripts"
  else
    same "$tmp/file" "$file" || fail "$link is not public/$file"
  fi
done < "$tmp/links"
echo "OK: $base/paper serves the wrapper, $base/paper/ redirects to it once, and every URL it serves itself resolves"
