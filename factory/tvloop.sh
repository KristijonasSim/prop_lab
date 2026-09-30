#!/usr/bin/env bash
# The TradingView run as a systemd USER service - restarts on a crash and comes
# back after a reboot (linger is on). Added 2026-09-30 after the first 24h run
# died with the PC on 2026-09-28.
#
#   ./factory/tvloop.sh start 24    new run of N hours
#   ./factory/tvloop.sh stop        stop it (the deadline is kept; `resume` carries on)
#   ./factory/tvloop.sh resume      restart toward the saved deadline
#   ./factory/tvloop.sh status      totals and whether it is alive
#   ./factory/tvloop.sh log         follow the output
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
UNIT=proplab-tvloop
FILE="$HOME/.config/systemd/user/$UNIT.service"

install_unit() {
  mkdir -p "$(dirname "$FILE")"
  cat > "$FILE" <<UNIT
[Unit]
Description=prop_lab TradingView loop - fetch, translate, test
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=PYTHONUNBUFFERED=1
# The model is the claude CLI in ~/.local/bin; systemd's PATH does not have it.
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$PY -m factory.tvloop --resume
StandardOutput=append:$ROOT/backtests/factory/tvloop.log
StandardError=append:$ROOT/backtests/factory/tvloop.log
# on-failure, not always: a run that reaches its deadline exits 0 and stays down.
Restart=on-failure
RestartSec=120
TimeoutStopSec=30
Nice=10

[Install]
WantedBy=default.target
UNIT
  systemctl --user daemon-reload
}

case "${1:-status}" in
  start)
    install_unit
    systemctl --user stop $UNIT 2>/dev/null || true
    "$PY" -c "import sys; sys.path.insert(0,'$ROOT'); from factory import tvloop; tvloop.start(float('${2:-24}'))"
    systemctl --user enable --now $UNIT
    echo "started ${2:-24}h run"; ;;
  resume) install_unit; systemctl --user enable --now $UNIT; ;;
  stop)   systemctl --user disable --now $UNIT; ;;
  log)    tail -f "$ROOT/backtests/factory/tvloop.log"; ;;
  status) systemctl --user is-active $UNIT || true
          cd "$ROOT" && "$PY" -m factory.tvloop --status; ;;
  *) echo "usage: $0 start [hours] | resume | stop | status | log"; exit 2; ;;
esac
