#!/usr/bin/env bash
# Start the dashboard detached, recording its PID so it can be stopped without
# pattern-matching (a `pkill -f streamlit` also matches the shell that runs it).
cd "$(dirname "$0")/.."
PIDFILE=runs/dashboard.pid
if [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; then
  echo "already running (pid $(cat $PIDFILE)) at http://localhost:8501"; exit 0
fi
nohup setsid .venv/bin/python -m streamlit run dashboard/app.py \
  --server.port 8501 --server.headless true --server.address 0.0.0.0 \
  --server.runOnSave true --browser.gatherUsageStats false \
  > runs/dashboard.log 2>&1 < /dev/null &
echo $! > "$PIDFILE"
echo "started pid $(cat $PIDFILE) -> http://localhost:8501"
