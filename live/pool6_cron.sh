#!/usr/bin/env bash
# The gold pool on Bybit demo, one pass every 5 minutes, from cron.
#   Install: (crontab -l 2>/dev/null; echo "*/5 * * * * $HOME/prop_lab/live/pool6_cron.sh") | crontab -
#   Watch:   tail -f $HOME/prop_lab/live/paper/pool6_cron.log
#   Status:  .venv/bin/python live/pool6_demo.py --status
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$ROOT/live/paper/pool6_cron.log"
mkdir -p "$(dirname "$LOG")"
exec 9>"$ROOT/live/paper/.pool6_cron.lock"
flock -n 9 || { echo "$(date -u +%FT%TZ) previous pass still running - skipped" >> "$LOG"; exit 0; }
{ "$ROOT/.venv/bin/python" -W ignore "$ROOT/live/pool6_demo.py" --arm 2>&1; } >> "$LOG"
tail -n 20000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
