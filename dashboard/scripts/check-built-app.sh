#!/usr/bin/env bash
# Serve the production build with `next start` and run check-paper-route.sh against it. The Dashboard workflow runs
# this after `bun run build`; tests/test_paper.py keeps that step a single unconditional call to this script.
# Usage: bash scripts/check-built-app.sh
set -euo pipefail

here="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$here/.."
port=3123
# Anything already listening on 127.0.0.1:$port would answer the probes in place of this build. curl exits 7 only when
# nothing accepts the connection; any other result (a reply, an empty reply, a timeout) means the port is taken. This
# does not catch a listener that takes the port after this check; on CI's fresh runner nothing does.
probe=0
curl -q -s -o /dev/null --max-time 2 "http://127.0.0.1:$port/" || probe=$?
if [ "$probe" != 7 ]; then
  echo "port $port is already in use"; exit 1
fi
log="$(mktemp)"
err="$(mktemp)"
./node_modules/.bin/next start -H 127.0.0.1 -p "$port" > "$log" 2>&1 &
server=$!
stop() {
  kill "$server" 2>/dev/null || true
  for _ in $(seq 1 10); do kill -0 "$server" 2>/dev/null || break; sleep 1; done
  kill -9 "$server" 2>/dev/null || true
  wait "$server" 2>/dev/null || true
  rm -f "$log" "$err"
}
trap stop EXIT

# Ready means curl finished cleanly and the dashboard answered 200; a transfer error is not ready, whatever it printed.
ready=
code=
for _ in $(seq 1 60); do
  if ! kill -0 "$server" 2>/dev/null; then
    rc=0; wait "$server" || rc=$?
    echo "next start exited with status $rc before serving"; cat "$err" "$log"; exit 1
  fi
  if code="$(curl -q -sS -o /dev/null --max-time 2 -w '%{http_code}' "http://127.0.0.1:$port/uk/triple-lock" \
       2> "$err")" && [ "$code" = 200 ]; then
    ready=1
    break
  fi
  sleep 1
done
if [ -z "$ready" ]; then
  echo "/uk/triple-lock was not ready after 60 tries (last status '$code')"; cat "$err" "$log"; exit 1
fi
bash "$here/check-paper-route.sh" "http://127.0.0.1:$port" || { cat "$log"; exit 1; }
