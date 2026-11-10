#!/usr/bin/env bash
# Installs upstream OpenAlgo (AGPL-3.0) beside this project and starts it on localhost.
# Usage: ./setup.sh <broker>   e.g. ./setup.sh zerodha   (names: VALID_BROKERS in OpenAlgo's .sample.env)
# Tested in a sandbox with Python 3.12.3 and uv.
set -euo pipefail
BROKER="${1:?broker name required, e.g. zerodha}"
DIR="${OPENALGO_DIR:-$(cd "$(dirname "$0")" && pwd)/openalgo-upstream}"
python3 -c 'import sys; sys.exit(sys.version_info < (3,12))' || { echo "Python 3.12+ required"; exit 1; }
pip install --quiet uv 2>/dev/null || pip install --quiet --break-system-packages uv
[ -d "$DIR" ] || git clone --depth 1 https://github.com/marketcalls/openalgo.git "$DIR"
cd "$DIR"
[ -f .env ] || cp .sample.env .env
python3 - "$BROKER" <<'PY'
import re, secrets, sys
b = sys.argv[1]; s = open('.env').read()
if 'OPENALGO_PLACEHOLDER' in s:   # generate secrets once only
    s = re.sub(r"APP_KEY\s*=\s*'[^']*'", f"APP_KEY = '{secrets.token_hex(32)}'", s)
    s = re.sub(r"API_KEY_PEPPER\s*=\s*'[^']*'", f"API_KEY_PEPPER = '{secrets.token_hex(32)}'", s)
s = s.replace("http://127.0.0.1:5000/<broker>/callback", f"http://127.0.0.1:5000/{b}/callback")
open('.env', 'w').write(s)
PY
echo "Now edit $DIR/.env: set BROKER_API_KEY and BROKER_API_SECRET for '$BROKER'."
uv sync
mkdir -p /tmp/gunicorn_workers
# Newest gunicorn (26.x) dropped the eventlet worker that upstream start.sh uses. OpenAlgo's SocketIO runs in
# threading mode anyway, so the gthread worker is used here. Bound to localhost only.
exec .venv/bin/gunicorn --worker-class gthread --threads 64 --workers 1 --bind 127.0.0.1:5000 \
     --timeout 300 --worker-tmp-dir /tmp/gunicorn_workers --log-level warning app:app
