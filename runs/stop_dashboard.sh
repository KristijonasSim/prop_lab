#!/usr/bin/env bash
cd "$(dirname "$0")/.."
PIDFILE=runs/dashboard.pid
[ -f "$PIDFILE" ] || { echo "no pidfile"; exit 0; }
kill "$(cat $PIDFILE)" 2>/dev/null && echo "stopped $(cat $PIDFILE)" || echo "not running"
rm -f "$PIDFILE"
