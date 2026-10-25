#!/usr/bin/env bash
# Start the Component Twin exercise station and open its UI.
set -euo pipefail
cd "$(dirname "$0")"
# shellcheck disable=SC1091
. .venv/bin/activate
URL="$(python -c 'from station.config import get_settings as g; s=g(); print(f"http://{s.station_host}:{s.station_port}/")')"
( sleep 4; xdg-open "$URL" >/dev/null 2>&1 || true ) &
exec python -m station
