#!/usr/bin/env bash
# Start the dashboard detached, recording its PID so it can be stopped without
# pattern-matching (a `pkill -f streamlit` also matches the shell that runs it).
cd "$(dirname "$0")/.."
PIDFILE=runs/dashboard.pid
# Always restart. Streamlit's runOnSave re-executes the main script but keeps
# the modules it already imported, so a server started before a change to
# proplab/ keeps running the old code against a newer database. Restarting is
# the only way to pick up module changes.
if [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; then
  echo "restarting pid $(cat $PIDFILE) to pick up code changes"
  kill "$(cat $PIDFILE)" 2>/dev/null
  sleep 2
fi
nohup setsid .venv/bin/python -m streamlit run dashboard/app.py \
  --server.port 8501 --server.headless true --server.address 0.0.0.0 \
  --server.runOnSave true --browser.gatherUsageStats false \
  > runs/dashboard.log 2>&1 < /dev/null &
echo $! > "$PIDFILE"
echo "started pid $(cat $PIDFILE) -> http://localhost:8501"
