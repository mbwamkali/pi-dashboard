# Pi Dashboard

A full-screen, portrait family dashboard for a Raspberry Pi. Replaces a DakBoard
subscription; everything it uses is free.

The top always shows a photo slideshow with the clock and weather. Below it, two
screens take turns (every 45 seconds by default):

- **Month**: a 5-week Google Calendar with each day's forecast.
- **List**: a day-by-day agenda (times, all-day events, forecast) next to your
  Google Tasks to-do list, this week's Come Follow Me lesson, Merriam-Webster's
  Word of the Day and a dad joke.

Change it from your phone at `http://<pi-ip>:8080/settings` (see below).

```
pi-dashboard/
  server.py           small web server + data fetching (Python, stdlib)
  authorize.py        one-time Google sign-in, saves token.json
  authorize-windows.cmd  the same sign-in on a Windows PC (double-click)
  static/             the dashboard (index.html, style.css, app.js) + settings.html
  docs/               homepage + privacy policy (GitHub Pages, for Google's sign-in screen)
  photos/             put your background pictures here
  config.example.json copied to config.json by install.sh
  install.sh          sets up the Pi (packages, service, kiosk, rotation)
  kiosk.sh            opens Chromium full-screen (reopened if it closes)
  screen.sh           turns the screen off/on at the times set in settings
  run-server.sh       starts the server (sample data until Google is signed in)
```

## 1. Prepare the Pi

Use **Raspberry Pi OS (64-bit)**, the Desktop version (Trixie or newer). Write it
with Raspberry Pi Imager, and in its settings set a username, your Wi-Fi, and
**Enable SSH** with your public key, so the Pi never needs a keyboard. Then copy
this folder to it, e.g. `rsync -a pi-dashboard/ <user>@<host>.local:pi-dashboard/`

Optional but useful: `sudo raspi-config nonint do_vnc 0` (see the screen from any
VNC viewer) and `sudo apt install unattended-upgrades` (security updates).

## 2. Google setup (once, about 10 minutes)

The dashboard reads your calendar and tasks with your permission, read-only.

1. Go to <https://console.cloud.google.com/>, create a project (e.g. "Home Dashboard").
2. **APIs & Services → Library**: enable **Google Calendar API** and **Google Tasks API**.
3. **Google Auth Platform → Branding** (older consoles: *OAuth consent screen*): choose
   user type **External** (Internal only exists for Google Workspace organizations).
   Fill in the app name, your support and developer-contact email, and:
   - **Application home page**: `https://mbwamkali.github.io/pi-dashboard/`
   - **Privacy policy**: `https://mbwamkali.github.io/pi-dashboard/privacy.html`
   - **Authorized domains**: `mbwamkali.github.io`

   (If you fork this, publish your own copy of the `docs/` folder with GitHub Pages and
   use your own addresses.) Don't upload a logo: that triggers Google's review process.
4. **Audience → Publish app** ("In production"). Important: while an app is in *Testing*,
   Google expires the sign-in after 7 days. Published but unverified is fine for personal
   use; you'll see an "unverified app" warning once when you sign in (click
   *Advanced → Go to …*). Don't attach a billing account; nothing here costs money.
5. **Clients → Create client** (older: *Credentials → OAuth client ID*), type **Desktop app**.
   Download the JSON and save it in this folder as `client_secret.json`.
6. Sign in. On the Pi (with the monitor attached) or on any computer with a browser:
   ```bash
   .venv/bin/python authorize.py      # on a computer: pip install -r requirements.txt first
   ```
   On **Windows**: put `client_secret.json` in the folder and double-click
   `authorize-windows.cmd`. It installs Python for that Windows user if needed (via
   winget), sets up the Google libraries, and runs the same sign-in.

   Approve access. It saves `token.json` and prints your calendars and task lists.
   If you did this on another computer, copy `token.json` and `client_secret.json`
   to the Pi's `pi-dashboard` folder.

## 3. Install on the Pi

```bash
cd ~/pi-dashboard
chmod +x install.sh
./install.sh 270        # screen rotation: 270, 90, 180 or normal (safe to re-run)
```

Then edit `config.json`:

- `location.name`: e.g. `"Denver, CO"` (or set `latitude` / `longitude`).
- `calendars`: leave `[]` to show the calendars ticked in Google Calendar, or list
  names/ids printed by `authorize.py`.
- `task_lists`: leave `[]` for your default list, or list names, e.g. `["My Tasks", "Groceries"]`.
- Everything else can be changed later from the settings page on your phone.

Copy photos into `photos/` (landscape pictures look best; they're cropped to fit).
Then `sudo reboot`. The Pi boots straight into the dashboard. Until Google is
signed in (`token.json` present) it shows sample calendar and to-do items.

## Change it from your phone

On any phone or computer on your home Wi-Fi, open `http://<pi-ip>:8080/settings`
(bookmark it). From there you can:

- turn the month and list screens on or off and set how often they switch,
- choose how many weeks / days each shows and which panels appear,
- tick which Google calendars and task lists to show,
- switch 12/24-hour clock, seconds, °F/°C and your town,
- turn the screen off at night (e.g. 22:30 to 06:00),
- add or delete background photos straight from your phone's camera roll.

Press **Save**; the dashboard picks it up within 30 seconds, no restart. Your
calendar and to-do list themselves you change as usual in the Google Calendar
and Google Tasks apps; the screen refreshes them every 5 minutes.

The settings page is open to anyone on your Wi-Fi. To require a PIN, set
`"settings_pin": "1234"` in `config.json` and restart (`sudo systemctl restart pi-dashboard`).

## Another household

Family members can run their own dashboard with this same Google app: set up their
own Pi (sections 1 and 3), copy your `client_secret.json` into their `pi-dashboard`
folder, and run the sign-in with **their** Google account (step 2.6, on the Pi or a
Windows/Mac/Linux computer). Their calendar data goes only to their Pi. Unverified apps
allow up to 100 Google accounts in total, far more than a family needs.

## Everyday use

- Hand edits to `config.json`: `sudo systemctl restart pi-dashboard`
- New photos: upload on the settings page, or copy them into `photos/`.
- Logs: `journalctl -u pi-dashboard -f`
- Wrong rotation: `./install.sh 90` (or 180, 270, normal) and reboot.
- The browser reopens by itself if it ever closes. The mouse pointer is hidden
  when the dashboard opens and reappears if the mouse is moved.
- Screenshot of the screen over SSH:
  `WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u) grim shot.png`
- Try it on any computer without Google: `python3 server.py --demo` and open
  <http://localhost:8080> (make the browser window tall and narrow).
- A small ⚠ in the bottom-right corner names any source that failed to update;
  the last good data stays on screen meanwhile.
- Moon phases / holidays: subscribe to those calendars in Google Calendar and
  they'll appear automatically.
- Come Follow Me: in January, change `come_follow_me_manual` to the new year's
  manual URL (open the manual on churchofjesuschrist.org and copy its address).
