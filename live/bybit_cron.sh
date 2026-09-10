#!/usr/bin/env bash
# H-027 on Bybit demo, one pass per hour, from cron.
#
# WHY CRON AND NOT A LOOP. `--loop` holds a process open, and a process dies with
# the machine. Cron restarts from nothing every hour, so a reboot, a crash or a
# closed laptop lid costs at most one bar rather than the whole run. The strategy
# decides on CLOSED 1h bars, so one pass an hour is all it needs - this fires at
# :02 to let Bybit finish the bar.
#
# WHAT IT DOES NOT SOLVE. If the machine is off, nothing runs, and the per-leg
# stops are enforced by the bot rather than by the exchange. The exchange holds a
# backstop at the WIDEST live leg, so an unattended adverse move costs the widest
# leg's distance on the whole position - about 2.5% of equity rather than the 2.0%
# the book intends. That is the real argument for a VPS, and it is a difference of
# half a percent, not of solvency.
#
# Install:  (crontab -l 2>/dev/null; echo '2 * * * * /home/kris/prop_lab/live/bybit_cron.sh') | crontab -
# Watch:    tail -f /home/kris/prop_lab/live/paper/bybit_cron.log
# Stop:     crontab -e   and delete the line
set -uo pipefail

ROOT=/home/kris/prop_lab
LOG="$ROOT/live/paper/bybit_cron.log"
mkdir -p "$(dirname "$LOG")"

# one at a time: a slow API call must never overlap the next hour's pass and
# double an order.
exec 9>"$ROOT/live/paper/.bybit_cron.lock"
flock -n 9 || { echo "$(date -u +%FT%TZ) previous pass still running - skipped" >> "$LOG"; exit 0; }

{
  echo "----- $(date -u +%FT%TZ) -----"
  "$ROOT/.venv/bin/python" "$ROOT/live/bybit_demo.py" --arm 2>&1
} >> "$LOG"

# keep the log from growing without bound
tail -n 5000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
