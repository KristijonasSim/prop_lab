#!/usr/bin/env bash
# Put the idea factory on the VM so steps 2-7 run whether or not the desktop is on.
#
# THE SPLIT, AND WHY IT IS NOT NEGOTIABLE TODAY.
#
#   step 1  (the model proposes ideas)  runs WHERE `claude` IS - the desktop.
#   steps 2-7 (everything else)         run on the VM, 24/7, zero tokens.
#
# The VM has no `claude` CLI and no node to install one with, and `claude -p`
# needs an authenticated interactive login that cannot be scripted from here.
# So the handoff is the QUEUE FILE: the desktop fills `queue.jsonl` with model
# ideas, this script pushes it, and the VM drains it with `--no-agent`.
#
# That is better architecture anyway. Token spend stays on a box Kris is
# sitting at, the 24/7 loop has no network dependency on Anthropic, and a
# queue that is full is a queue the VM can chew on for days.
#
# WHAT THE BOX CAN TAKE. Measured 2026-09-23: 341 MB peak for a 24-cell pass,
# against 423 MB available with the live bot and the research loop already on
# it, plus 2 GB of swap. It fits, and it fits with less headroom than anything
# else here - so the unit is niced, IO-idle, and one pass at a time.
#
#   ./factory/deploy_vm.sh              # sync code, data, queue; install, DO NOT start
#   ./factory/deploy_vm.sh --arm        # the same, and start it
#   ./factory/deploy_vm.sh --queue      # push the queue only (after a top-up)
#   ./factory/deploy_vm.sh --status     # alive? what has it done?
#   ./factory/deploy_vm.sh --pull       # bring results back to the desktop
#   ./factory/deploy_vm.sh --stop
set -euo pipefail

KEY="${PROP_LAB_VM_KEY:-$HOME/trading-bots/bybit_bot/deploy/ssh/oracle_bots}"
HOST="${PROP_LAB_VM_HOST:-ubuntu@89.168.78.138}"
REMOTE="/home/ubuntu/prop_lab"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=20)
#: How often a pass starts. One pass of 20 ideas is ~17 min of VM CPU, so this
#: leaves the box idle most of the hour for the live bot's cron at :02.
EVERY="${PROP_LAB_FACTORY_EVERY:-10800}"

case "${1:-deploy}" in
--status)
  "${SSH[@]}" "$HOST" '
    echo "=== service ==="; systemctl --user is-active proplab-factory 2>/dev/null || echo inactive
    echo "=== queue ==="; cd '"$REMOTE"' && ./.venv/bin/python -m factory.nightly --status 2>/dev/null | head -40
    echo "=== last log ==="; tail -20 '"$REMOTE"'/backtests/factory/nightly.log 2>/dev/null
    echo "=== box ==="; free -m | head -2; uptime'
  exit 0 ;;
--stop)
  "${SSH[@]}" "$HOST" 'systemctl --user stop proplab-factory; systemctl --user disable proplab-factory'
  echo "stopped"; exit 0 ;;
--pull)
  mkdir -p backtests/factory/vm
  rsync -az -e "${SSH[*]}" "$HOST:$REMOTE/backtests/factory/" backtests/factory/vm/
  echo "results in backtests/factory/vm/"
  exit 0 ;;
--queue)
  "${SSH[@]}" "$HOST" "mkdir -p $REMOTE/backtests/factory"
  rsync -az -e "${SSH[*]}" ./backtests/factory/queue.jsonl "$HOST:$REMOTE/backtests/factory/"
  rsync -az -e "${SSH[*]}" ./backtests/factory/tried.jsonl "$HOST:$REMOTE/backtests/factory/" 2>/dev/null || true
  echo "queue pushed"; exit 0 ;;
esac

echo "→ code"
rsync -az --delete -e "${SSH[*]}" --exclude '__pycache__' --exclude '*.pyc' \
  ./core/ "$HOST:$REMOTE/core/"
rsync -az --delete -e "${SSH[*]}" --exclude '__pycache__' --exclude '*.pyc' \
  ./factory/ "$HOST:$REMOTE/factory/"

echo "→ bars (~90 MB: six markets, 15m/1h/4h, plus the five-year caches)"
"${SSH[@]}" "$HOST" "mkdir -p $REMOTE/data $REMOTE/backtests/factory"
for f in XAUUSD XAGUSD EURUSD GBPUSD USDJPY; do
  for tf in 15m 1h 4h; do
    rsync -az -e "${SSH[*]}" "./data/${f}_dukascopy_${tf}.parquet"   "$HOST:$REMOTE/data/" 2>/dev/null || true
    rsync -az -e "${SSH[*]}" "./data/${f}_dukascopy5y_${tf}.parquet" "$HOST:$REMOTE/data/" 2>/dev/null || true
  done
done
rsync -az -e "${SSH[*]}" ./data/BTCUSDT_spot_15m.parquet "$HOST:$REMOTE/data/"

echo "→ queue (this is the handoff - model ideas made on the desktop)"
rsync -az -e "${SSH[*]}" ./backtests/factory/queue.jsonl "$HOST:$REMOTE/backtests/factory/" 2>/dev/null || true
rsync -az -e "${SSH[*]}" ./backtests/factory/tried.jsonl "$HOST:$REMOTE/backtests/factory/" 2>/dev/null || true

echo "→ preflight on the box"
"${SSH[@]}" "$HOST" "cd $REMOTE && ./.venv/bin/python -c '
import sys; sys.path.insert(0, \".\")
from factory import cells
cl = cells.all_cells()
print(f\"  {len(cl)} of 24 cells have data\")
from factory.recheck import coverage
print(f\"  {int(coverage().usable.sum())} of 24 can be re-checked\")
'"

echo "→ service"
"${SSH[@]}" "$HOST" "mkdir -p ~/.config/systemd/user && cat > ~/.config/systemd/user/proplab-factory.service <<'UNIT'
[Unit]
Description=prop_lab idea factory, steps 2-7
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$REMOTE
# Two cores, and the live bot needs one. No 24-cell fan-out here.
Environment=PROP_LAB_WORKERS=1
# --no-agent: the VM has no claude CLI. Ideas arrive by queue from the desktop.
ExecStart=/bin/sh -c 'while true; do $REMOTE/.venv/bin/python -m factory.nightly --no-agent -n 20 --seeds 3 >> $REMOTE/backtests/factory/nightly.log 2>&1; sleep $EVERY; done'
Restart=always
RestartSec=120
Nice=15
# The live bot is the priority on this box. 341 MB against 423 MB free is the
# tightest fit on here, so the factory yields on both CPU and IO.
IOSchedulingClass=idle
MemoryMax=600M
# MemoryMax in a USER unit needs the memory controller delegated, which Ubuntu
# 20.04 on cgroup v1 may not do - so it can silently not be enforced. This line
# is the one that always works: if the box runs out, the kernel kills THIS and
# not the live bot. Without it the OOM killer picks by size and the factory is
# the biggest thing on the box.
OOMScoreAdjust=800

[Install]
WantedBy=default.target
UNIT
loginctl enable-linger ubuntu 2>/dev/null || true
systemctl --user daemon-reload
echo '  unit installed'"

if [ "${1:-deploy}" = "--arm" ] || [ "${2:-}" = "--arm" ]; then
  echo "→ arming"
  "${SSH[@]}" "$HOST" 'systemctl --user enable proplab-factory
    systemctl --user restart proplab-factory
    sleep 6
    systemctl --user is-active proplab-factory'
else
  echo
  echo "NOT STARTED. The unit is installed and idle."
  echo "This box also runs the live bot and the research loop, and the factory"
  echo "is the tightest memory fit on it (341 MB against 423 MB free), so"
  echo "starting it is a deliberate act:"
  echo "    ./factory/deploy_vm.sh --arm"
fi

echo
echo "deployed. steps 2-7 now run whether or not this desktop is on."
echo
echo "THE ONE THING IT CANNOT DO THERE: propose ideas. Top the queue up here,"
echo "then push it:"
echo "    .venv/bin/python -m factory.sources.agent -n 100"
echo "    ./factory/deploy_vm.sh --queue"
echo
echo "    ./factory/deploy_vm.sh --status     # is it alive"
echo "    ./factory/deploy_vm.sh --pull       # bring results back"
