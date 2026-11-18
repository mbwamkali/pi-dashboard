#!/usr/bin/env bash
# Started at login by labwc (see install.sh). Turns the screen off and on at
# the times set on the settings page ("screen": {"off": "22:30", "on": "06:00"}).
# Leave either time empty to keep the screen on all the time.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
last=""
while true; do
  want=$(python3 - "$DIR/config.json" <<'EOF'
import json, sys, datetime as dt
try:
    s = json.load(open(sys.argv[1])).get("screen") or {}
except Exception:
    s = {}
off, on = s.get("off") or "", s.get("on") or ""
if not off or not on or off == on:
    print("on"); sys.exit()
now = dt.datetime.now().strftime("%H:%M")
# Off period may run past midnight (22:30 -> 06:00) or not (13:00 -> 14:00).
asleep = (off <= now < on) if off < on else (now >= off or now < on)
print("off" if asleep else "on")
EOF
)
  if [ "$want" != "$last" ]; then
    wlopm --"$want" '*' && last="$want"
  fi
  sleep 30
done
