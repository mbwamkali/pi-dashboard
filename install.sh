#!/usr/bin/env bash
# Sets up the dashboard on Raspberry Pi OS Desktop (Trixie or Bookworm, labwc).
# Run from this folder as your normal user:   ./install.sh [rotation]
#   rotation: 270 (default), 90, 180 or normal
# Safe to run again (e.g. after copying a new version over).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
ROTATION="${1:-270}"
USER_NAME="$(id -un)"

echo "==> Installing packages"
sudo apt-get update
sudo apt-get install -y python3-venv fonts-roboto curl wlopm
sudo apt-get install -y chromium || sudo apt-get install -y chromium-browser

echo "==> Python environment"
[ -d "$DIR/.venv" ] || python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --quiet --upgrade pip
"$DIR/.venv/bin/pip" install --quiet -r "$DIR/requirements.txt"

[ -f "$DIR/config.json" ] || cp "$DIR/config.example.json" "$DIR/config.json"
mkdir -p "$DIR/photos"
chmod +x "$DIR/kiosk.sh" "$DIR/screen.sh" "$DIR/run-server.sh"

echo "==> Background service (starts at boot)"
sudo tee /etc/systemd/system/pi-dashboard.service >/dev/null <<EOF
[Unit]
Description=Pi Dashboard server
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$DIR
ExecStart=$DIR/run-server.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable pi-dashboard.service
sudo systemctl restart pi-dashboard.service

echo "==> Desktop: auto-login, no screen blanking"
sudo raspi-config nonint do_boot_behaviour B4 || true   # desktop, auto-login
sudo raspi-config nonint do_blanking 1 || true          # 1 = disable blanking

echo "==> Screen rotation ($ROTATION)"
# kanshi is what Raspberry Pi OS's own Screen Configuration tool uses.
mkdir -p "$HOME/.config/kanshi"
if [ "$ROTATION" = "normal" ]; then T=normal; else T="$ROTATION"; fi
cat > "$HOME/.config/kanshi/config" <<EOF
profile {
	output * transform $T
}
EOF

echo "==> Hide the mouse pointer over the dashboard"
# labwc reads this alongside the system rc.xml (Pi OS starts labwc with -m).
mkdir -p "$HOME/.config/labwc"
RC="$HOME/.config/labwc/rc.xml"
if [ ! -f "$RC" ] || ! grep -q pi-dashboard "$RC"; then
  [ -f "$RC" ] && cp "$RC" "$RC.bak"
  cat > "$RC" <<'EOF'
<?xml version="1.0"?>
<!-- pi-dashboard: move the pointer to the corner and hide it when the dashboard opens.
     It reappears if the mouse is moved. -->
<labwc_config>
  <windowRules>
    <windowRule identifier="chromium*">
      <action name="WarpCursor" to="output" x="-1" y="-1" />
      <action name="HideCursor" />
    </windowRule>
  </windowRules>
</labwc_config>
EOF
fi

echo "==> Start the dashboard at login"
AUTOSTART="$HOME/.config/labwc/autostart"
touch "$AUTOSTART"
sed -i '/pi-dashboard\|kiosk\.sh\|screen\.sh/d' "$AUTOSTART"
cat >> "$AUTOSTART" <<EOF
# pi-dashboard: browser (reopened if it closes) and night-time screen schedule
/usr/bin/lwrespawn $DIR/kiosk.sh &
/usr/bin/lwrespawn $DIR/screen.sh &
EOF

echo
echo "Done."
if [ ! -f "$DIR/token.json" ]; then
  echo "  Showing sample calendar and to-do items until you sign in to Google:"
  echo "  put client_secret.json + token.json in $DIR (see README), then"
  echo "  sudo systemctl restart pi-dashboard"
fi
echo "  Settings from your phone: http://$(hostname).local:8080/settings"
echo "  Reboot (sudo reboot) to start the screen, or log out and back in."
