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
import glob
import shutil
import subprocess
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
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v"}
MEDIA_EXTS = PHOTO_EXTS | VIDEO_EXTS
MAX_PHOTO_MB, MAX_VIDEO_MB = 40, 1024
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
    "panels": {"todo": True, "countdown": True, "cfm": True, "wotd": True, "joke": True},
    "location": {"name": "", "latitude": None, "longitude": None},
    "units": "fahrenheit",
    "clock_24h": False,
    "show_seconds": True,
    "calendars": [],
    "calendar_labels": {},
    "calendar_colors": {},
    "show_key": True,
    "task_lists": [],
    "photos_dir": "photos",
    "photo_folders": [],
    "photo_interval_seconds": 60,
    "screen": {"off": "", "on": ""},
    "dim": {"from": "", "to": "", "level": 45},
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


def calendar_label(cfg, cal_id, name):
    """Short name for the calendar key: the label set on the settings page, else the
    calendar's name (an email address becomes just the part before the @)."""
    label = (cfg.get("calendar_labels") or {}).get(cal_id) or name or ""
    return label.split("@")[0] if "@" in label else label


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
        overrides = cfg.get("calendar_colors") or {}
        cal_color = {c["id"]: overrides.get(c["id"]) or c.get("backgroundColor", "#4285f4") for c in chosen}
        key = [{"name": calendar_label(cfg, c["id"], c.get("summaryOverride") or c.get("summary")),
                "color": cal_color[c["id"]]} for c in chosen]
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
                    color = cal_color[c["id"]]
                    if e.get("colorId") in event_colors:
                        color = event_colors[e["colorId"]]["background"]
                    events.append({
                        "summary": e.get("summary", "(busy)"),
                        "allDay": "date" in s,
                        "start": s.get("date") or s.get("dateTime"),
                        "end": en.get("date") or en.get("dateTime"),
                        "color": color,
                        "calendar": calendar_label(cfg, c["id"], c.get("summaryOverride") or c.get("summary")),
                    })
                page = resp.get("nextPageToken")
                if not page:
                    break
        grid_end = start + dt.timedelta(days=cfg["weeks_to_show"] * 7)
        return {"start": start.isoformat(), "end": grid_end.isoformat(), "events": events, "calendars": key}

    def sources(self, cfg):
        """Calendars and task lists available to choose from on the settings page."""
        cal, svc = self._services()
        cals = [{"id": c["id"], "name": c.get("summaryOverride") or c.get("summary"),
                 "color": (cfg.get("calendar_colors") or {}).get(c["id"]) or c.get("backgroundColor"),
                 "googleColor": c.get("backgroundColor"), "selected": bool(c.get("selected"))}
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
        "hourly": "temperature_2m,weather_code,precipitation_probability,is_day",
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
    hourly, hours = d.get("hourly") or {}, []
    now_hour = cur["time"][:13]  # "2026-11-18T07"
    times = hourly.get("time") or []
    start = next((i for i, t in enumerate(times) if t[:13] >= now_hour), None)
    if start is not None:
        for i in range(start + 1, min(start + 13, len(times))):
            if hourly["temperature_2m"][i] is None:
                continue
            hours.append({
                "time": times[i],
                "temp": round(hourly["temperature_2m"][i]),
                "code": hourly["weather_code"][i],
                "pop": hourly["precipitation_probability"][i] or 0,
                "isDay": bool(hourly["is_day"][i]),
            })
    return {
        "location": name,
        "hours": hours,
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
    key = [{"name": calendar_label(cfg, i, n), "color": c} for i, n, c in
           (("demo-family", "Family", "#3f51b5"), ("demo-work", "Work", "#e67c73"),
            ("demo-kids", "Kids", "#33b679"), ("demo-church", "Church", "#f6bf26"))]
    return {"start": start.isoformat(), "end": grid_end.isoformat(), "events": events, "calendars": key}


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
                    "showKey": self.cfg.get("show_key", True),
                    "dim": self.cfg.get("dim") or {},
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
    "calendar_labels": lambda v: {str(k)[:200]: str(x).strip()[:30] for k, x in list(v.items())[:50] if str(x).strip()},
    "show_key": bool,
    "calendar_colors": lambda v: {str(k)[:200]: str(x) for k, x in list(v.items())[:50]
                                  if re.fullmatch(r"#[0-9a-fA-F]{6}", str(x))},
    "dim": lambda v: {"from": hhmm(v.get("from")), "to": hhmm(v.get("to")),
                      "level": max(10, min(90, int(v.get("level") or 45)))},
    "task_lists": lambda v: [str(x) for x in v][:20],
    "panels": lambda v: {k: bool(v.get(k, True)) for k in ("todo", "countdown", "cfm", "wotd", "joke")},
    "come_follow_me_manual": lambda v: str(v)[:300],
    "photo_folders": lambda v: [str(x)[:100] for x in v][:100],
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
        if "photo_folders" in changes:
            cache.photos_version += 1   # the screen reloads its slideshow list


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


def media_rel(rel):
    """Clean a relative path like 'Trips/Beach 2025/IMG_1.jpg' (folders allowed, nothing
    hidden, no '..'). Returns the OS path relative to the photos folder, or None."""
    parts = [p.strip() for p in rel.replace("\\", "/").split("/") if p.strip()]
    if not parts or len(parts) > 5 or any(p in (".", "..") or p.startswith(".") for p in parts):
        return None
    if os.path.splitext(parts[-1])[1].lower() not in MEDIA_EXTS:
        return None
    return os.path.join(*parts)


def list_media(cfg, all_folders=False):
    """Every photo and video under the photos folder, including subfolders. Unless
    all_folders, only the top-level folders picked on the settings page ("" = loose files)."""
    root = photos_dir(cfg)
    chosen = cfg.get("photo_folders") or []
    out = []
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        top = rel_dir.split("/")[0]
        if chosen and not all_folders and top not in chosen:
            continue
        for n in sorted(files):
            ext = os.path.splitext(n)[1].lower()
            if n.startswith(".") or ext not in MEDIA_EXTS:
                continue
            rel = f"{rel_dir}/{n}" if rel_dir else n
            out.append({"url": "/photos/" + urllib.parse.quote(rel), "path": rel, "folder": rel_dir,
                        "video": ext in VIDEO_EXTS})
    return out


def media_folders(cfg):
    root = photos_dir(cfg)
    try:
        return sorted(d for d in os.listdir(root) if not d.startswith(".") and os.path.isdir(os.path.join(root, d)))
    except FileNotFoundError:
        return []


def screenshot():
    """PNG of what the Pi's screen shows right now (labwc/Wayland, via grim), plus
    whether the screen is powered on. Returns (png_bytes, power) or raises."""
    run = f"/run/user/{os.getuid()}"
    sockets = sorted(glob.glob(os.path.join(run, "wayland-[0-9]")))
    if not sockets:
        raise RuntimeError("No screen session found (only works on the Pi)")
    env = {**os.environ, "XDG_RUNTIME_DIR": run, "WAYLAND_DISPLAY": os.path.basename(sockets[0])}
    power = "unknown"
    try:
        out = subprocess.run(["wlopm", "-j"], env=env, capture_output=True, timeout=5, text=True).stdout
        power = "off" if '"off"' in out else "on" if '"on"' in out else "unknown"
    except Exception:
        pass
    if power == "off":
        raise RuntimeError("The screen is turned off right now (night schedule), so there's nothing to show.")
    img = subprocess.run(["grim", "-l", "1", "-s", "0.5", "-"],
                         env=env, capture_output=True, timeout=15)
    if img.returncode != 0 or not img.stdout:
        raise RuntimeError(img.stderr.decode(errors="replace")[:200] or "grim failed")
    return img.stdout, power


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

        def photo_path(self, path, prefix="/api/photos/"):
            rel = media_rel(urllib.parse.unquote(path[len(prefix):]))
            return os.path.join(photos_dir(cache.cfg), rel) if rel else None

        def send_file(self, full):
            """Stream a photo or video, honouring Range requests so videos start playing at once."""
            size = os.path.getsize(full)
            ctype = self.guess_type(full)
            if full.lower().endswith((".mov", ".m4v")):
                ctype = "video/mp4"   # Chromium plays H.264 .mov files when labelled as mp4
            start, end = 0, size - 1
            m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
                else:
                    start = max(0, size - int(m.group(2)))
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "max-age=3600")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            with open(full, "rb") as f:
                f.seek(start)
                left = end - start + 1
                try:
                    while left > 0:
                        chunk = f.read(min(256 * 1024, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the browser stopped reading (normal for video seeking)

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

        def do_PUT(self):  # upload: PUT /api/photos/<folder/.../name> with the file as the body
            path = urllib.parse.urlparse(self.path).path
            full = self.photo_path(path) if path.startswith("/api/photos/") else None
            if not full:
                return self.send_error(400, "Photos (.jpg .png .webp .gif) or videos (.mp4 .mov .webm .m4v) only")
            if not self.pin_ok():
                return
            n = int(self.headers.get("Content-Length") or 0)
            video = os.path.splitext(full)[1].lower() in VIDEO_EXTS
            limit = (MAX_VIDEO_MB if video else MAX_PHOTO_MB) * 1024 * 1024
            if n > limit:
                return self.send_error(413, f"{'Video' if video else 'Photo'} is over {limit // 1048576} MB")
            os.makedirs(os.path.dirname(full), exist_ok=True)
            if shutil.disk_usage(os.path.dirname(full)).free - n < 1024 ** 3:
                return self.send_error(507, "Not enough free space on the Pi (keeping 1 GB free)")
            tmp = full + ".part"
            try:
                with open(tmp, "wb") as f:   # written in pieces: videos can be large
                    left = n
                    while left > 0:
                        chunk = self.rfile.read(min(1024 * 1024, left))
                        if not chunk:
                            raise ConnectionError("upload cut short")
                        f.write(chunk)
                        left -= len(chunk)
                os.replace(tmp, full)
            except Exception as e:
                if os.path.exists(tmp):
                    os.remove(tmp)
                return self.send_error(400, str(e)[:100])
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
            # Tidy up folders left empty (never the photos folder itself).
            root, d = os.path.abspath(photos_dir(cache.cfg)), os.path.dirname(os.path.abspath(full))
            while d != root and d.startswith(root) and not os.listdir(d):
                os.rmdir(d)
                d = os.path.dirname(d)
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
            if path == "/api/screenshot":
                if not self.pin_ok():
                    return
                try:
                    body, power = screenshot()
                except Exception as e:
                    return self.send_error(503, str(e)[:150])
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Screen-Power", power)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/photos":
                every = "all=1" in (urllib.parse.urlparse(self.path).query or "")
                items = list_media(cache.cfg, all_folders=every)
                return self.send_json({"photos": [i["url"] for i in items], "items": items,
                                       "folders": media_folders(cache.cfg),
                                       "chosen": cache.cfg.get("photo_folders") or []})
            if path.startswith("/photos/"):
                full = self.photo_path(path, "/photos/")
                if not full or not os.path.isfile(full):
                    return self.send_error(404)
                return self.send_file(full)
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
