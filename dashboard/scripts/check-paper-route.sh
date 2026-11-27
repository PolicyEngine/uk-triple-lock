#!/usr/bin/env bash
# Check that the working paper is served at /uk/triple-lock/paper with no redirect loop,
# and that every file its wrapper links under /uk/triple-lock resolves.
# Usage: scripts/check-paper-route.sh <origin>
#   CI runs it against `next start`; after a deploy, run it against https://www.policyengine.org.
set -euo pipefail

origin="${1:?usage: check-paper-route.sh <origin>}"
origin="${origin%/}"
base="$origin/uk/triple-lock"
page="$(mktemp)"
trap 'rm -f "$page"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

# The bare address serves the wrapper itself, with no redirect.
read -r code hops < <(curl -s -o "$page" -w '%{http_code} %{num_redirects}\n' "$base/paper")
[ "$code" = 200 ] && [ "$hops" = 0 ] || fail "$base/paper gave $code after $hops redirects"
grep -q '<iframe src="/uk/triple-lock/paper/web/index.html?v=' "$page" || fail "$base/paper has no manuscript iframe"

# The slashed address takes exactly one redirect, to the bare address.
read -r code target < <(curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' "$base/paper/")
[ "$code" = 308 ] && [ "$target" = "$base/paper" ] || fail "$base/paper/ gave $code to '$target'"
read -r code hops < <(curl -s -L --max-redirs 5 -o /dev/null -w '%{http_code} %{num_redirects}\n' "$base/paper/")
[ "$code" = 200 ] && [ "$hops" = 1 ] || fail "$base/paper/ ended at $code after $hops redirects"

# Every file the wrapper links under the basePath resolves with no redirect.
links="$(grep -o -E '(src|href)="/uk/triple-lock[^"]*"' "$page" | sed -E 's/^(src|href)="//; s/"$//' | sort -u)"
[ -n "$links" ] || fail "no links under /uk/triple-lock in the wrapper"
while read -r link; do
  read -r code hops < <(curl -s -o /dev/null -w '%{http_code} %{num_redirects}\n' "$origin$link")
  [ "$code" = 200 ] || fail "$link gave $code"
  echo "ok $link"
done <<< "$links"
echo "OK: $base/paper serves the wrapper, and $base/paper/ redirects to it once"
