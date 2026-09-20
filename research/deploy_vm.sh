#!/usr/bin/env bash
# Put the research loop on the VM so it runs when the desktop is off.
#
# WHY. Kris, 2026-09-18: "when i will turn off my computer, will this still
# work?" It did not. A loop that only runs while a desktop is awake is not a
# 24/7 loop, and the whole point of building it was that it runs without him.
#
# WHY THE VM CAN TAKE IT, despite being a 2-core / 952 MB free-tier box:
# the SCREEN is cheap. It needs core/, research/, the six cached feeds and six
# market bar files - about 18 MB, against 36 GB free. What it must NEVER do
# there is the walk-forward; that stays on the 28-core desktop.
#
# IT SHARES THE BOX WITH THE LIVE BOT and the bot wins. The loop is niced and
# the cycle is long, so an hourly cron that places real orders is never waiting
# on a screen run.
#
#   ./research/deploy_vm.sh            # sync + restart
#   ./research/deploy_vm.sh --status   # is it alive, what has it done
#   ./research/deploy_vm.sh --stop
set -euo pipefail

KEY="${PROP_LAB_VM_KEY:-$HOME/trading-bots/bybit_bot/deploy/ssh/oracle_bots}"
HOST="${PROP_LAB_VM_HOST:-ubuntu@89.168.78.138}"
REMOTE="/home/ubuntu/prop_lab"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15)

case "${1:-deploy}" in
--status)
  "${SSH[@]}" "$HOST" '
    echo "=== service ==="; systemctl --user is-active proplab-loop 2>/dev/null || echo inactive
    echo "=== state ==="; cat '"$REMOTE"'/backtests/loop_state.json 2>/dev/null
    echo "=== last cycles ==="; tail -12 '"$REMOTE"'/backtests/loop.log 2>/dev/null
    echo "=== load ==="; uptime'
  exit 0 ;;
--stop)
  "${SSH[@]}" "$HOST" 'systemctl --user stop proplab-loop; systemctl --user disable proplab-loop'
  echo "stopped"; exit 0 ;;
esac

echo "→ code"
# --delete only inside the two code dirs, so nothing else on the VM is touched.
rsync -az --delete -e "${SSH[*]}" \
  --exclude '__pycache__' --exclude '*.pyc' \
  ./core/ "$HOST:$REMOTE/core/"
rsync -az --delete -e "${SSH[*]}" \
  --exclude '__pycache__' --exclude '*.pyc' \
  ./research/ "$HOST:$REMOTE/research/"

echo "→ feeds and bars (~18 MB)"
"${SSH[@]}" "$HOST" "mkdir -p $REMOTE/data/macro $REMOTE/data/vix $REMOTE/backtests $REMOTE/docs/prereg"
rsync -az -e "${SSH[*]}" ./data/macro/ "$HOST:$REMOTE/data/macro/"
rsync -az -e "${SSH[*]}" ./data/vix/   "$HOST:$REMOTE/data/vix/"
for f in XAUUSD XAGUSD EURUSD GBPUSD USDJPY; do
  rsync -az -e "${SSH[*]}" "./data/${f}_dukascopy_1h.parquet" "$HOST:$REMOTE/data/" 2>/dev/null || true
done
rsync -az -e "${SSH[*]}" ./data/BTCUSDT_spot_15m.parquet "$HOST:$REMOTE/data/" 2>/dev/null || true

# The gold tick archive — 22 MB, and the only INTRADAY feed in the registry.
# Every other feed is daily, which is ~750 rows in three years and was the
# single biggest killer in the loop's first 187 tests. Without this the VM can
# only run the thin half of the search space.
echo "→ gold flow archive (~22 MB, the intraday feeds)"
"${SSH[@]}" "$HOST" "mkdir -p $REMOTE/data/flow/XAUUSD"
rsync -az -e "${SSH[*]}" ./data/flow/XAUUSD/ "$HOST:$REMOTE/data/flow/XAUUSD/"

echo "→ ledger + proposal queue"
rsync -az -e "${SSH[*]}" ./backtests/ledger.csv "$HOST:$REMOTE/backtests/"
rsync -az -e "${SSH[*]}" ./backtests/proposals.jsonl "$HOST:$REMOTE/backtests/" 2>/dev/null || true

echo "→ service"
"${SSH[@]}" "$HOST" "mkdir -p ~/.config/systemd/user && cat > ~/.config/systemd/user/proplab-loop.service <<'UNIT'
[Unit]
Description=prop_lab research loop
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$REMOTE
ExecStart=$REMOTE/.venv/bin/python -m research.loop --forever --every 1800 -n 8 --mode queue
Restart=always
RestartSec=60
Nice=10
# The live bot is the priority on this box; the loop yields to it.
IOSchedulingClass=idle

[Install]
WantedBy=default.target
UNIT
loginctl enable-linger ubuntu 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable proplab-loop
# `enable --now` does NOT restart a service that is already running, so a
# redeploy silently kept the old code and the old --mode. Restart explicitly.
systemctl --user restart proplab-loop
sleep 6
systemctl --user is-active proplab-loop"

echo
echo "deployed. it now runs whether or not this desktop is on."
echo "  ./research/deploy_vm.sh --status"
echo
echo "Email alerts need ~/.config/prop_lab/notify.env ON THE VM — see"
echo "research/notify.py. Without it the loop still runs and just logs."
