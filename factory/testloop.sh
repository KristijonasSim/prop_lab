#!/usr/bin/env bash
# Test the queue on every core, forever: drain, wait a minute, drain again.
# Runs beside factory.harvest so testing never waits for translation.
cd "$(dirname "$0")/.."
while true; do
  for src in tradingview agent; do
    PROP_LAB_WORKERS=2 .venv/bin/python -m factory.drain -j 12 --source "$src" || true
  done
  sleep 60
done
