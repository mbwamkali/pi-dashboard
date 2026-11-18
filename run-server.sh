#!/usr/bin/env bash
# Started by the pi-dashboard service. Uses sample calendar/to-do data until
# Google is signed in (token.json present).
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$DIR/token.json" ]; then
  exec "$DIR/.venv/bin/python" "$DIR/server.py"
else
  exec "$DIR/.venv/bin/python" "$DIR/server.py" --demo
fi
