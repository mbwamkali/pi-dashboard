#!/usr/bin/env bash
# Started at login by labwc (see install.sh), wrapped in lwrespawn so Chromium
# is reopened if it ever closes or crashes. Waits for the dashboard server,
# then opens it full-screen.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
URL="http://localhost:$(python3 -c "import json;print(json.load(open('$DIR/config.json')).get('port',8080))" 2>/dev/null || echo 8080)/"

# Wait up to 60s for the server.
for _ in $(seq 60); do
  curl -fs -o /dev/null "$URL" && break
  sleep 1
done

BROWSER="$(command -v chromium || command -v chromium-browser)"
# Clear the "Chromium didn't shut down correctly" bubble after power cuts.
PREFS="$HOME/.config/chromium/Default/Preferences"
[ -f "$PREFS" ] && sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"[^"]*"/"exit_type":"Normal"/' "$PREFS"

exec "$BROWSER" --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble \
  --no-first-run --check-for-update-interval=31536000 --password-store=basic \
  --ozone-platform=wayland --disable-features=Translate "$URL"
