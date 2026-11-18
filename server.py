#!/usr/bin/env python3
"""Pi Dashboard server.

Serves the dashboard page and one JSON endpoint (/api/data) that gathers:
  - Google Calendar events (5 weeks starting this Sunday)
  - Google Tasks (incomplete tasks)
  - Weather (Open-Meteo, no key needed)
  - This week's Come Follow Me lesson
  - Merriam-Webster Word of the Day
  - A dad joke (icanhazdadjoke.com)

Run:  python server.py            (uses config.json + token.json)
      python server.py --demo     (sample calendar/tasks, no Google sign-in needed)
"""

import argparse
import datetime as dt
import html
import json
import os
import random
import re
import threading
import time
import traceback
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(HERE, "static")
CONFIG_PATH = os.path.join(HERE, "config.json")
TOKEN_PATH = os.path.join(HERE, "token.json")
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
USER_AGENT = "pi-dashboard/1.0 (personal home display)"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks.readonly",
]

DEFAULT_CONFIG = {
    "port": 8080,
    "host": "0.0.0.0",
    "settings_pin": "",
    "views": ["month", "list"],
    "view_seconds": 45,
    "agenda_days": 14,
    "panels": {"todo": True, "cfm": True, "wotd": True, "joke": True},
    "location": {"name": "", "latitude": None, "longitude": None},
    "units": "fahrenheit",
    "clock_24h": False,
    "show_seconds": True,
    "calendars": [],
    "task_lists": [],
    "photos_dir": "photos",
    "photo_interval_seconds": 60,
    "screen": {"off": "", "on": ""},
    "weeks_to_show": 5,
    "come_follow_me_manual": "https://www.churchofjesuschrist.org/study/manual/come-follow-me-for-home-and-church-old-testament-2026",
    "refresh_minutes": {
        "calendar": 5,
        "tasks": 5,
        "weather": 15,
        "come_follow_me": 360,
        "word_of_the_day": 180,
        "dad_joke": 60,
    },
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            user = json.load(f)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def http_get(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def grid_range(weeks, agenda_days=0):
    """Sunday of this week (local) through weeks*7 days later (or further, for the agenda)."""
    today = dt.date.today()
    start = today - dt.timedelta(days=(today.weekday() + 1) % 7)
    end = max(start + dt.timedelta(days=weeks * 7), today + dt.timedelta(days=agenda_days + 1))
    return start, end


# --------------------------------------------------------------------------- Google

class Google:
    def __init__(self):
        self._lock = threading.Lock()
        self._creds = None

    def _services(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        with self._lock:
            if self._creds is None:
                if not os.path.exists(TOKEN_PATH):
                    raise RuntimeError("Not signed in to Google yet: run authorize.py")
                self._creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            if not self._creds.valid:
                self._creds.refresh(Request())
                with open(TOKEN_PATH, "w", encoding="utf-8") as f:
                    f.write(self._creds.to_json())
            cal = build("calendar", "v3", credentials=self._creds, cache_discovery=False)
            tasks = build("tasks", "v1", credentials=self._creds, cache_discovery=False)
            return cal, tasks

    def calendar(self, cfg):
        cal, _ = self._services()
        start, end = grid_range(cfg["weeks_to_show"], cfg["agenda_days"])
        tz = dt.datetime.now().astimezone().tzinfo
        time_min = dt.datetime.combine(start, dt.time(), tz).isoformat()
        time_max = dt.datetime.combine(end, dt.time(), tz).isoformat()

        cal_list = cal.calendarList().list().execute().get("items", [])
        wanted = cfg.get("calendars") or []
        if wanted:
            chosen = [c for c in cal_list if c["id"] in wanted or c.get("summary") in wanted]
        else:
            chosen = [c for c in cal_list if c.get("selected")]
        event_colors = cal.colors().get().execute().get("event", {})

        events = []
        for c in chosen:
            page = None
            while True:
                resp = cal.events().list(
                    calendarId=c["id"], timeMin=time_min, timeMax=time_max,
                    singleEvents=True, orderBy="startTime", maxResults=250, pageToken=page,
                ).execute()
                for e in resp.get("items", []):
                    if e.get("status") == "cancelled":
                        continue
                    s, en = e.get("start", {}), e.get("end", {})
                    color = c.get("backgroundColor", "#4285f4")
                    if e.get("colorId") in event_colors:
                        color = event_colors[e["colorId"]]["background"]
                    events.append({
                        "summary": e.get("summary", "(busy)"),
                        "allDay": "date" in s,
                        "start": s.get("date") or s.get("dateTime"),
                        "end": en.get("date") or en.get("dateTime"),
                        "color": color,
                        "calendar": c.get("summaryOverride") or c.get("summary"),
                    })
                page = resp.get("nextPageToken")
                if not page:
                    break
        grid_end = start + dt.timedelta(days=cfg["weeks_to_show"] * 7)
        return {"start": start.isoformat(), "end": grid_end.isoformat(), "events": events}

    def sources(self, cfg):
        """Calendars and task lists available to choose from on the settings page."""
        cal, svc = self._services()
        cals = [{"id": c["id"], "name": c.get("summaryOverride") or c.get("summary"),
                 "color": c.get("backgroundColor"), "selected": bool(c.get("selected"))}
                for c in cal.calendarList().list().execute().get("items", [])]
        lists = [{"id": l["id"], "name": l["title"]}
                 for l in svc.tasklists().list(maxResults=100).execute().get("items", [])]
        return {"calendars": cals, "taskLists": lists}

    def tasks(self, cfg):
        _, svc = self._services()
        lists = svc.tasklists().list(maxResults=100).execute().get("items", [])
        wanted = cfg.get("task_lists") or []
        if wanted:
            lists = [l for l in lists if l["id"] in wanted or l["title"] in wanted]
        else:
            lists = lists[:1]  # your default ("My Tasks") list
        out = []
        for l in lists:
            items = svc.tasks().list(
                tasklist=l["id"], showCompleted=False, showHidden=False, maxResults=100
            ).execute().get("items", [])
            items = [t for t in items if t.get("title", "").strip() and not t.get("parent")]
            items.sort(key=lambda t: (t.get("due") or "9999", t.get("position", "")))
            out.append({
                "title": l["title"],
                "items": [{"title": t["title"], "due": (t.get("due") or "")[:10] or None} for t in items],
            })
        return {"lists": out}


# --------------------------------------------------------------------------- Public sources

_geo_cache = {}


def resolve_location(cfg):
    loc = cfg.get("location") or {}
    if loc.get("latitude") is not None and loc.get("longitude") is not None:
        return float(loc["latitude"]), float(loc["longitude"]), loc.get("name") or ""
    name = (loc.get("name") or "").strip()
    if not name:
        raise RuntimeError("Set location in config.json")
    if name in _geo_cache:
        return _geo_cache[name]
    city, _, region = [p.strip() for p in name.partition(",")]
    q = urllib.parse.urlencode({"name": city, "count": 20, "language": "en", "format": "json"})
    results = json.loads(http_get("https://geocoding-api.open-meteo.com/v1/search?" + q)).get("results") or []
    if region:
        r = region.lower()
        match = [x for x in results if r in (x.get("admin1", "").lower(), x.get("country_code", "").lower(),
                                            x.get("country", "").lower())
                 or (len(r) == 2 and US_STATES.get(r.upper(), "").lower() == x.get("admin1", "").lower())]
        results = match or results
    if not results:
        raise RuntimeError(f"Couldn't find location '{name}'")
    best = results[0]
    _geo_cache[name] = (best["latitude"], best["longitude"], name)
    return _geo_cache[name]


def weather(cfg):
    lat, lon, name = resolve_location(cfg)
    f = cfg.get("units", "fahrenheit") == "fahrenheit"
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,apparent_temperature,weather_code,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum",
        "temperature_unit": "fahrenheit" if f else "celsius",
        "precipitation_unit": "inch" if f else "mm",
        "timezone": "auto", "forecast_days": 16,
    })
    d = json.loads(http_get("https://api.open-meteo.com/v1/forecast?" + q))
    cur, daily = d["current"], d["daily"]
    days = []
    for i, date in enumerate(daily["time"]):
        if daily["temperature_2m_max"][i] is None or daily["temperature_2m_min"][i] is None:
            continue  # the far end of the forecast is sometimes empty
        days.append({
            "date": date,
            "code": daily["weather_code"][i],
            "hi": round(daily["temperature_2m_max"][i]),
            "lo": round(daily["temperature_2m_min"][i]),
            "pop": daily["precipitation_probability_max"][i],
            "precip": daily["precipitation_sum"][i],
        })
    return {
        "location": name,
        "temp": round(cur["temperature_2m"]),
        "feels": round(cur["apparent_temperature"]),
        "code": cur["weather_code"],
        "isDay": bool(cur["is_day"]),
        "precipUnit": "″" if f else " mm",
        "days": days,
    }


def come_follow_me(cfg):
    base = cfg["come_follow_me_manual"].split("?")[0].rstrip("/")
    index = http_get(base + "?lang=eng", headers={"User-Agent": "Mozilla/5.0"})
    today = dt.date.today().isoformat()
    for m in re.finditer(r'<li[^>]*data-date-end="([\d-]+)"[^>]*data-date-start="([\d-]+)"[^>]*>\s*<a href="([^"]+)"', index):
        end, start, href = m.groups()
        if start <= today <= end:
            url = urllib.parse.urljoin("https://www.churchofjesuschrist.org", html.unescape(href))
            page = http_get(url, headers={"User-Agent": "Mozilla/5.0"})
            title_m = re.search(r'<p[^>]*class="title-number"[^>]*>(.*?)</p>', page, re.S)
            h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
            title = strip_tags(title_m.group(1)) if title_m else ""
            dates, _, theme = title.partition(":")
            return {
                "dates": dates.strip(),
                "theme": theme.strip().strip("“”\""),
                "reading": strip_tags(h1_m.group(1)) if h1_m else "",
            }
    return None


def word_of_the_day(cfg):
    rss = http_get("https://www.merriam-webster.com/wotd/feed/rss2")
    item = rss[rss.find("<item>"):]
    word = strip_tags(re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item, re.S).group(1))
    desc = html.unescape(re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>", item, re.S).group(1))
    pron = re.search(r"\\([^\\]+)\\", desc)
    pos = re.search(r"\\[^\\]+\\.*?<em>(.*?)</em>", desc, re.S)
    defn = re.search(r"</em>\s*<br\s*/?>\s*<p>(.*?)</p>", desc, re.S)
    return {
        "word": word,
        "pronunciation": pron.group(1).strip() if pron else "",
        "partOfSpeech": strip_tags(pos.group(1)) if pos else "",
        "definition": strip_tags(defn.group(1)) if defn else "",
    }


def dad_joke(cfg):
    d = json.loads(http_get("https://icanhazdadjoke.com/", headers={"Accept": "application/json"}))
    return {"joke": d["joke"]}


US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}


# --------------------------------------------------------------------------- Demo data

def demo_calendar(cfg):
    start, end = grid_range(cfg["weeks_to_show"], cfg["agenda_days"])
    rnd = random.Random(start.toordinal())
    colors = ["#3f51b5", "#e67c73", "#33b679", "#f6bf26", "#8e24aa"]
    titles = ["Soccer practice", "Dentist", "Piano lesson", "Book club", "Date night", "Work trip",
              "Grocery pickup", "Team meeting", "Youth activity", "Choir", "Parent-teacher conference",
              "Birthday party", "Seminary", "Yard work"]
    tz = dt.datetime.now().astimezone().tzinfo
    events = []
    d = start
    while d < end:
        for _ in range(rnd.choice([0, 1, 1, 2, 3])):
            h = rnd.choice([7, 9, 10, 13, 15, 16, 18, 19, 20])
            m = rnd.choice([0, 0, 15, 30, 45])
            s = dt.datetime.combine(d, dt.time(h, m), tz)
            events.append({"summary": rnd.choice(titles), "allDay": False, "start": s.isoformat(),
                           "end": (s + dt.timedelta(hours=1)).isoformat(), "color": rnd.choice(colors),
                           "calendar": "Demo"})
        if d.weekday() == 4 and rnd.random() < 0.6:
            events.append({"summary": "Pay day", "allDay": True, "start": d.isoformat(),
                           "end": (d + dt.timedelta(days=1)).isoformat(), "color": "#4285f4", "calendar": "Demo"})
        if d.weekday() == 6:
            s = dt.datetime.combine(d, dt.time(10, 30), tz)
            events.append({"summary": "Church", "allDay": False, "start": s.isoformat(),
                           "end": (s + dt.timedelta(hours=2)).isoformat(), "color": "#3f51b5", "calendar": "Demo"})
        d += dt.timedelta(days=1)
    events.sort(key=lambda e: e["start"])
    grid_end = start + dt.timedelta(days=cfg["weeks_to_show"] * 7)
    return {"start": start.isoformat(), "end": grid_end.isoformat(), "events": events}


def demo_sources(cfg):
    return {"calendars": [{"id": "demo-family", "name": "Family", "color": "#3f51b5", "selected": True},
                          {"id": "demo-work", "name": "Work", "color": "#e67c73", "selected": True},
                          {"id": "demo-holidays", "name": "Holidays", "color": "#33b679", "selected": False}],
            "taskLists": [{"id": "demo-tasks", "name": "My Tasks"}, {"id": "demo-groceries", "name": "Groceries"}]}


def demo_tasks(cfg):
    today = dt.date.today()
    return {"lists": [{"title": "My Tasks", "items": [
        {"title": "Get new car insurance", "due": (today + dt.timedelta(days=2)).isoformat()},
        {"title": "Schedule furnace service", "due": None},
        {"title": "Return library books", "due": today.isoformat()},
        {"title": "Order birthday present", "due": (today + dt.timedelta(days=6)).isoformat()},
        {"title": "Call about the gutters", "due": None},
    ]}]}


# --------------------------------------------------------------------------- Cache + HTTP

class Cache:
    def __init__(self, cfg, demo):
        self.cfg = cfg
        self.google = Google()
        self.demo = demo
        self.photos_version = 0
        self.lock = threading.Lock()
        self.data, self.errors, self.fetched = {}, {}, {}
        self.sources = {
            "calendar": (demo_calendar if demo else self.google.calendar, "calendar"),
            "tasks": (demo_tasks if demo else self.google.tasks, "tasks"),
            "weather": (weather, "weather"),
            "cfm": (come_follow_me, "come_follow_me"),
            "wotd": (word_of_the_day, "word_of_the_day"),
            "joke": (dad_joke, "dad_joke"),
        }

    def refresh(self, force=False):
        now = time.time()
        today = dt.date.today().isoformat()
        for key, (fn, ttl_key) in self.sources.items():
            ttl = self.cfg["refresh_minutes"].get(ttl_key, 15) * 60
            last, last_day = self.fetched.get(key, (0, None))
            if not force and now - last < ttl and last_day == today:
                continue
            try:
                self.data[key] = fn(self.cfg)
                self.errors.pop(key, None)
            except Exception as e:  # keep showing the last good data
                self.errors[key] = str(e)[:200]
                traceback.print_exc()
            self.fetched[key] = (now, today)

    def snapshot(self):
        with self.lock:
            self.refresh()
            return {
                **self.data,
                "errors": dict(self.errors),
                "photosVersion": self.photos_version,
                "settings": {
                    "clock24h": self.cfg["clock_24h"],
                    "showSeconds": self.cfg["show_seconds"],
                    "photoIntervalSeconds": self.cfg["photo_interval_seconds"],
                    "views": self.cfg["views"],
                    "viewSeconds": self.cfg["view_seconds"],
                    "agendaDays": self.cfg["agenda_days"],
                    "panels": self.cfg["panels"],
                },
            }

    def background_loop(self):
        while True:
            try:
                with self.lock:
                    self.refresh()
            except Exception:
                traceback.print_exc()
            time.sleep(30)


# --------------------------------------------------------------------------- Settings page

def hhmm(v):
    """'22:30' -> '22:30', '' or None -> '' (raises on anything else)."""
    v = str(v or "").strip()
    if not v:
        return ""
    return dt.datetime.strptime(v, "%H:%M").strftime("%H:%M")


EDITABLE = {  # key: validator
    "views": lambda v: [x for x in v if x in ("month", "list")] or ["month"],
    "view_seconds": lambda v: max(5, min(3600, int(v))),
    "agenda_days": lambda v: max(1, min(31, int(v))),
    "weeks_to_show": lambda v: max(1, min(8, int(v))),
    "photo_interval_seconds": lambda v: max(10, min(86400, int(v))),
    "clock_24h": bool,
    "show_seconds": bool,
    "units": lambda v: "celsius" if v == "celsius" else "fahrenheit",
    "location": lambda v: {"name": str(v.get("name", ""))[:100],
                           "latitude": float(v["latitude"]) if v.get("latitude") not in (None, "") else None,
                           "longitude": float(v["longitude"]) if v.get("longitude") not in (None, "") else None},
    "calendars": lambda v: [str(x) for x in v][:50],
    "task_lists": lambda v: [str(x) for x in v][:20],
    "panels": lambda v: {k: bool(v.get(k, True)) for k in ("todo", "cfm", "wotd", "joke")},
    "come_follow_me_manual": lambda v: str(v)[:300],
    "screen": lambda v: {k: hhmm(v.get(k)) for k in ("off", "on")},
}


def save_settings(cache, changes):
    with open(CONFIG_PATH, encoding="utf-8") as f:
        on_disk = json.load(f) if os.path.getsize(CONFIG_PATH) else {}
    for k, v in changes.items():
        if k in EDITABLE:
            on_disk[k] = EDITABLE[k](v)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(on_disk, f, indent=2)
    os.replace(tmp, CONFIG_PATH)
    with cache.lock:
        cache.cfg.clear()
        cache.cfg.update(load_config())
        cache.fetched.clear()  # refetch everything with the new settings


def settings_view(cache):
    cfg = cache.cfg
    try:
        sources = demo_sources(cfg) if cache.demo else cache.google.sources(cfg)
        err = None
    except Exception as e:
        sources, err = {"calendars": [], "taskLists": []}, str(e)[:200]
    return {"config": {k: cfg.get(k) for k in EDITABLE}, "sources": sources, "sourcesError": err,
            "pinRequired": bool(cfg.get("settings_pin"))}


def photos_dir(cfg):
    p = cfg["photos_dir"]
    return p if os.path.isabs(p) else os.path.join(HERE, p)


def make_handler(cache):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=STATIC_DIR, **kw)

        def log_message(self, fmt, *args):
            pass

        def end_headers(self):
            # Page files: always check for a newer version, so updates show up
            # without clearing the kiosk browser's cache (unchanged = quick 304).
            if not self.path.startswith(("/api/", "/photos/")):
                self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def send_json(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def pin_ok(self):
            pin = cache.cfg.get("settings_pin") or ""
            if pin and self.headers.get("X-Pin", "") != str(pin):
                self.send_response(401)
                self.end_headers()
                return False
            return True

        def read_body(self, limit):
            n = int(self.headers.get("Content-Length") or 0)
            if n > limit:
                raise ValueError("too large")
            return self.rfile.read(n)

        def photo_path(self, path):
            name = os.path.basename(urllib.parse.unquote(path[len("/api/photos/"):]))
            if not name or name.startswith(".") or os.path.splitext(name)[1].lower() not in PHOTO_EXTS:
                return None
            return os.path.join(photos_dir(cache.cfg), name)

        def do_POST(self):
            if urllib.parse.urlparse(self.path).path != "/api/settings":
                return self.send_error(404)
            if not self.pin_ok():
                return
            try:
                save_settings(cache, json.loads(self.read_body(100_000) or b"{}"))
            except Exception as e:
                return self.send_error(400, str(e)[:100])
            self.send_json({"ok": True})

        def do_PUT(self):  # upload a photo: PUT /api/photos/<name> with the file as the body
            path = urllib.parse.urlparse(self.path).path
            full = self.photo_path(path) if path.startswith("/api/photos/") else None
            if not full:
                return self.send_error(400, "Only .jpg .jpeg .png .webp .gif files")
            if not self.pin_ok():
                return
            try:
                body = self.read_body(40 * 1024 * 1024)
            except ValueError:
                return self.send_error(413, "Photo is over 40 MB")
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as f:
                f.write(body)
            cache.photos_version += 1
            self.send_json({"ok": True})

        def do_DELETE(self):
            path = urllib.parse.urlparse(self.path).path
            full = self.photo_path(path) if path.startswith("/api/photos/") else None
            if not full or not os.path.isfile(full):
                return self.send_error(404)
            if not self.pin_ok():
                return
            os.remove(full)
            cache.photos_version += 1
            self.send_json({"ok": True})

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/data":
                return self.send_json(cache.snapshot())
            if path == "/settings":
                self.path = "/settings.html"
                return super().do_GET()
            if path == "/api/settings":
                if not self.pin_ok():
                    return
                return self.send_json(settings_view(cache))
            if path == "/api/photos":
                d = photos_dir(cache.cfg)
                names = sorted(n for n in os.listdir(d) if os.path.splitext(n)[1].lower() in PHOTO_EXTS) \
                    if os.path.isdir(d) else []
                return self.send_json({"photos": ["/photos/" + urllib.parse.quote(n) for n in names]})
            if path.startswith("/photos/"):
                name = os.path.basename(urllib.parse.unquote(path[len("/photos/"):]))
                full = os.path.join(photos_dir(cache.cfg), name)
                if not name or os.path.splitext(name)[1].lower() not in PHOTO_EXTS or not os.path.isfile(full):
                    return self.send_error(404)
                with open(full, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", self.guess_type(full))
                self.send_header("Cache-Control", "max-age=3600")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return super().do_GET()

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="sample calendar/tasks, no Google sign-in")
    ap.add_argument("--port", type=int)
    ap.add_argument("--host", help="address to listen on (default from config: 0.0.0.0 = whole home network)")
    ap.add_argument("--config", help="path to config.json (default: next to server.py)")
    args = ap.parse_args()

    global CONFIG_PATH
    if args.config:
        CONFIG_PATH = os.path.abspath(args.config)
    cfg = load_config()
    cache = Cache(cfg, args.demo)
    threading.Thread(target=cache.background_loop, daemon=True).start()
    port = args.port or cfg["port"]
    host = args.host or cfg["host"]
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write("{}")
    srv = ThreadingHTTPServer((host, port), make_handler(cache))
    print(f"Dashboard on http://{host}:{port}  settings: /settings{'  (demo mode)' if args.demo else ''}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
