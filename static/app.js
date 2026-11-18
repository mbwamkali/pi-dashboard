"use strict";

const $ = (id) => document.getElementById(id);
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
  "September", "October", "November", "December"];
let settings = { clock24h: false, showSeconds: true, photoIntervalSeconds: 60,
  views: ["month", "list"], viewSeconds: 45, agendaDays: 14, panels: {}, dim: {} };
let lastData = null;
let lastDay = new Date().getDate();

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parseDay = (s) => { const [y, m, d] = s.slice(0, 10).split("-").map(Number); return new Date(y, m - 1, d); };
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const dayDiff = (a, b) => Math.round((parseDay(b) - parseDay(a)) / 86400000);
const mon = (d) => MONTHS[d.getMonth()].slice(0, 3);
const dow = (d) => DAYS[d.getDay()].slice(0, 3);

/* ---------------- Weather icons (simple line art, WMO codes) ---------------- */
const ICONS = {
  sun: '<circle cx="32" cy="32" r="11"/><path d="M32 7v7M32 50v7M7 32h7M50 32h7M14.3 14.3l5 5M44.7 44.7l5 5M14.3 49.7l5-5M44.7 19.3l5-5"/>',
  moon: '<path d="M42 44a17 17 0 0 1-16-27 17 17 0 1 0 24 21 17 17 0 0 1-8 6z"/>',
  partly: '<path d="M22 17v-5M10 29H5M13.5 20.5l-3.5-3.5M34 20.5l3.5-3.5"/><path d="M16.5 33a8 8 0 1 1 13-8"/><path d="M20 50h26a9 9 0 0 0 0-18 13 13 0 0 0-25 3 7.5 7.5 0 0 0-1 15z"/>',
  cloud: '<path d="M18 48h28a10 10 0 0 0 0-20 14 14 0 0 0-27 3.5A8.5 8.5 0 0 0 18 48z"/>',
  fog: '<path d="M18 38h28a10 10 0 0 0 0-20 14 14 0 0 0-27 3.5A8.5 8.5 0 0 0 18 38z"/><path d="M12 46h40M18 54h30"/>',
  rain: '<path d="M18 40h28a10 10 0 0 0 0-20 14 14 0 0 0-27 3.5A8.5 8.5 0 0 0 18 40z"/><path d="M22 46l-3 8M32 46l-3 8M42 46l-3 8"/>',
  snow: '<path d="M18 40h28a10 10 0 0 0 0-20 14 14 0 0 0-27 3.5A8.5 8.5 0 0 0 18 40z"/><path d="M22 47v6M19 50h6M34 47v6M31 50h6M28 54v6M25 57h6M40 54v0"/>',
  storm: '<path d="M18 38h28a10 10 0 0 0 0-20 14 14 0 0 0-27 3.5A8.5 8.5 0 0 0 18 38z"/><path d="M33 40l-6 10h8l-5 10"/>',
};
function iconFor(code, isDay = true) {
  let k = "cloud";
  if (code === 0 || code === 1) k = isDay ? "sun" : "moon";
  else if (code === 2) k = "partly";
  else if (code === 3) k = "cloud";
  else if (code === 45 || code === 48) k = "fog";
  else if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) k = "rain";
  else if ((code >= 71 && code <= 77) || code === 85 || code === 86) k = "snow";
  else if (code >= 95) k = "storm";
  return `<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">${ICONS[k]}</svg>`;
}
function describe(code) {
  if (code === 0) return "Clear";
  if (code === 1) return "Mostly Clear";
  if (code === 2) return "Partly Cloudy";
  if (code === 3) return "Cloudy";
  if (code === 45 || code === 48) return "Fog";
  if (code >= 51 && code <= 57) return "Drizzle";
  if (code >= 61 && code <= 67) return "Rain";
  if (code >= 71 && code <= 77) return "Snow";
  if (code >= 80 && code <= 82) return "Showers";
  if (code === 85 || code === 86) return "Snow Showers";
  if (code >= 95) return "Thunderstorms";
  return "";
}

/* ---------------- Clock + evening dimming ---------------- */
const hhmmNow = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
function inWindow(now, from, to) {   // "21:00".."06:00" may wrap past midnight
  if (!from || !to || from === to) return false;
  return from < to ? (now >= from && now < to) : (now >= from || now < to);
}
function tick() {
  const now = new Date();
  let h = now.getHours();
  let ampm = "";
  if (!settings.clock24h) { ampm = h >= 12 ? "PM" : "AM"; h = h % 12 || 12; }
  $("hm").textContent = `${settings.clock24h ? pad(h) : h}:${pad(now.getMinutes())}`;
  $("sec").textContent = settings.showSeconds ? pad(now.getSeconds()) : "";
  $("ampm").textContent = settings.showSeconds ? "" : ampm;
  $("date").textContent = `${DAYS[now.getDay()]}, ${MONTHS[now.getMonth()]} ${now.getDate()}`;
  const dim = settings.dim || {};
  $("dim").style.opacity = inWindow(hhmmNow(now), dim.from, dim.to) ? (dim.level || 45) / 100 : 0;
  if (now.getDate() !== lastDay) { lastDay = now.getDate(); if (lastData) render(lastData); load(); }
}

/* ---------------- Weather (now + next 12 hours) ---------------- */
function hourLabel(iso) {
  const h = Number(iso.slice(11, 13));
  if (settings.clock24h) return `${pad(h)}:00`;
  return `${h % 12 || 12}${h >= 12 ? "p" : "a"}`;
}
function renderWeather(w) {
  if (!w) { $("weather").innerHTML = ""; return; }
  const today = ymd(new Date());
  const t = w.days.find((d) => d.date === today) || w.days[0];
  // Every other hour for the next 12 hours; rain chance shown when it's worth knowing.
  const hours = (w.hours || []).filter((_, i) => i % 2 === 0).slice(0, 5);
  $("weather").innerHTML = `
    <div class="now"><span class="icon">${iconFor(w.code, w.isDay)}</span><span class="temp">${w.temp}°</span></div>
    <div class="desc">${esc(describe(w.code))}</div>
    <div class="feels">Feels like ${w.feels}° · ${t.hi}° / ${t.lo}° · ${t.pop ?? 0}% rain</div>
    <div class="hours">${hours.map((x) => `
      <div class="hour"><span class="name">${hourLabel(x.time)}</span>
        <span class="icon">${iconFor(x.code, x.isDay)}</span><span>${x.temp}°</span>
        <span class="pop">${x.pop >= 20 ? `${x.pop}%` : ""}</span></div>`).join("")}
    </div>`;
}

/* ---------------- Calendar data ---------------- */
function fmtTime(d) {
  let h = d.getHours(); const m = d.getMinutes();
  if (settings.clock24h) return `${pad(h)}:${pad(m)}`;
  const ap = h >= 12 ? "p" : "a"; h = h % 12 || 12;
  return `${h}${m ? `<sup>${pad(m)}</sup>` : ""}${ap}`;
}

// The same event on two calendars (e.g. invited on both) is shown once, with both colors.
function dedupe(events) {
  const seen = new Map();
  for (const e of events) {
    const k = [e.summary.trim().toLowerCase(), e.start, e.end, e.allDay].join("|");
    const prev = seen.get(k);
    if (prev) { if (!prev.colors.includes(e.color)) prev.colors.push(e.color); }
    else seen.set(k, { ...e, colors: [e.color] });
  }
  return [...seen.values()];
}

function eventsByDay(events) {
  const byDay = {};
  const push = (key, ev) => (byDay[key] ||= []).push(ev);
  for (const e of events) {
    if (e.allDay) {
      e.days = Math.max(1, dayDiff(e.start, e.end));
      for (let d = parseDay(e.start); d < parseDay(e.end); d = addDays(d, 1)) push(ymd(d), e);
    } else {
      push(ymd(new Date(e.start)), e);
    }
  }
  // Multi-day bars first (same order every day so they line up), then all-day, then by time.
  const rank = (e) => (e.allDay ? (e.days > 1 ? 0 : 1) : 2);
  for (const k in byDay) {
    byDay[k].sort((a, b) => rank(a) - rank(b)
      || (a.allDay ? (a.start < b.start ? -1 : a.start > b.start ? 1 : b.days - a.days || a.summary.localeCompare(b.summary))
        : new Date(a.start) - new Date(b.start)));
  }
  return byDay;
}

const bg = (colors) => colors.length > 1
  ? `linear-gradient(135deg, ${colors.map((c, i) => `${esc(c)} ${(i * 100) / colors.length}% ${((i + 1) * 100) / colors.length}%`).join(", ")})`
  : esc(colors[0]);
const dots = (colors) => `<span class="dots">${colors.slice(0, 3).map((c) => `<span class="dot" style="background:${esc(c)}"></span>`).join("")}</span>`;

// dayKey + month=true: draw multi-day events as one bar running across the days.
function eventLi(e, { withEnd = false, dayKey = null, month = false } = {}) {
  if (e.allDay) {
    let cls = "ev allday", text = esc(e.summary);
    if (e.days > 1 && dayKey) {
      const d = parseDay(dayKey), first = dayKey === e.start, last = ymd(addDays(d, 1)) === e.end;
      if (month) {
        if (!first) cls += " cont-l";
        if (!last) cls += " cont-r";
        if (!first && d.getDay() !== 0) text = "&nbsp;";      // label once per week row
      } else {
        const endDay = addDays(parseDay(e.end), -1);
        text += first ? ` <span class="span">· through ${dow(endDay)} ${endDay.getDate()}</span>`
          : ` <span class="span">· day ${dayDiff(e.start, dayKey) + 1} of ${e.days}</span>`;
      }
    }
    return `<li class="${cls}" style="background:${bg(e.colors)}">${text}</li>`;
  }
  const s = new Date(e.start), en = new Date(e.end);
  const t = withEnd && en > s ? `${fmtTime(s)}–${fmtTime(en)}` : fmtTime(s);
  return `<li class="ev">${dots(e.colors)}<span class="txt"><span class="t">${t}</span> ${esc(e.summary)}</span></li>`;
}

/* ---------------- Month view ---------------- */
function renderCalendar(cal, weather) {
  const el = $("calendar");
  if (!cal) { el.innerHTML = ""; return; }
  const start = parseDay(cal.start), end = parseDay(cal.end);
  const todayKey = ymd(new Date());
  const fc = Object.fromEntries((weather?.days || []).map((d) => [d.date, d]));
  const byDay = eventsByDay(cal.events);

  // Nearer weeks get more room than weeks further out.
  const weeks = Math.round(dayDiff(cal.start, cal.end) / 7);
  const weights = Array.from({ length: weeks }, (_, i) => [1.35, 1.15][i] ?? (i >= weeks - 1 && weeks > 3 ? 0.85 : 1));
  el.style.gridTemplateRows = `auto ${weights.map((w) => `${w}fr`).join(" ")}`;

  let html = DAYS.map((d, i) => `<div class="dow${i % 6 === 0 ? " weekend" : ""}">${d.slice(0, 3)}</div>`).join("");
  for (let d = new Date(start), i = 0; d < end; d = addDays(d, 1), i++) {
    const key = ymd(d);
    const cls = ["cell"];
    if (d.getDay() % 6 === 0) cls.push("weekend");
    if (key === todayKey) cls.push("today");
    if (key < todayKey) cls.push("past");
    const showMonth = i === 0 || d.getDate() === 1;
    const f = fc[key];
    const evs = (byDay[key] || []).map((e) => eventLi(e, { dayKey: key, month: true })).join("");
    html += `<div class="${cls.join(" ")}">
      <div class="head">
        <div class="date-l">${showMonth ? `<span class="mon">${mon(d)}</span>` : ""}<span class="num">${d.getDate()}</span></div>
        ${f && key >= todayKey ? `<div class="fc">${iconFor(f.code)}${showMonth ? "" : `<span class="hi">${f.hi}°</span> ${f.lo}°`}</div>` : ""}
      </div>
      <ul class="events">${evs}</ul></div>`;
  }
  el.innerHTML = html;
  requestAnimationFrame(trimOverflow);
}

// A single word too long for a narrow day box ("Reservation") is shown slightly smaller
// instead of being broken in the middle; only if it still won't fit is it allowed to break.
function fitWords() {
  for (const txt of document.querySelectorAll(".cell .ev .txt")) {
    if (txt.scrollWidth <= txt.clientWidth + 1) continue;
    const base = parseFloat(getComputedStyle(txt).fontSize);
    let size = base;
    while (txt.scrollWidth > txt.clientWidth + 1 && size > base * 0.72) {
      size -= base * 0.04;
      txt.style.fontSize = `${size}px`;
    }
    if (txt.scrollWidth > txt.clientWidth + 1) txt.style.overflowWrap = "anywhere";
  }
}

// Hide events that don't fit in a day box and show "+N more" instead.
function trimOverflow() {
  fitWords();
  for (const ul of document.querySelectorAll(".cell .events")) {
    const items = [...ul.children];
    const overflowing = () => ul.scrollHeight > ul.clientHeight + 1;
    if (!overflowing()) continue;
    const more = document.createElement("li");
    more.className = "more";
    ul.appendChild(more);
    let hidden = 0;
    while (overflowing() && hidden < items.length) {
      items[items.length - 1 - hidden].style.display = "none";
      hidden++;
      more.textContent = `+${hidden} more`;
    }
  }
}

/* ---------------- List view: agenda ---------------- */
function renderAgenda(cal, weather) {
  const el = $("agenda");
  if (!cal) { el.innerHTML = ""; return; }
  const byDay = eventsByDay(cal.events);
  const fc = Object.fromEntries((weather?.days || []).map((d) => [d.date, d]));
  const today = new Date();
  const now = Date.now();
  const days = [];
  for (let i = 0; i < settings.agendaDays; i++) {
    const d = addDays(today, i), key = ymd(d);
    let evs = byDay[key] || [];
    if (i === 0) evs = evs.filter((e) => e.allDay || new Date(e.end) > now); // hide finished events
    if (!evs.length && i > 1) continue;  // skip empty days after tomorrow
    days.push({ i, d, key, evs });
  }
  el.innerHTML = days.map(({ i, d, key, evs }) => {
    const name = i === 0 ? "Today" : i === 1 ? "Tomorrow" : DAYS[d.getDay()];
    const f = fc[key];
    return `<div class="aday${i === 0 ? " today" : ""}">
      <div class="anum">${i === 0 ? `<span>${d.getDate()}</span>` : d.getDate()}</div>
      <div class="ahead"><span class="aname">${name}${i > 6 ? ` <span class="amon">${mon(d)}</span>` : ""}</span>
        ${f ? `<span class="afc">${iconFor(f.code)}<span class="hi">${f.hi}°</span> ${f.lo}°</span>` : ""}</div>
      <ul>${evs.length ? evs.map((e) => eventLi(e, { withEnd: true, dayKey: key })).join("") : `<li class="none">Nothing scheduled</li>`}</ul>
    </div>`;
  }).join("");
  requestAnimationFrame(() => fitAgenda(el, days));
}

// Use the whole column: the last day that doesn't fit is cut short with "+N more", and
// any days after it are listed one line each ("Mon 23  No school · Gym · …").
function fitAgenda(el, days) {
  const limit = () => el.getBoundingClientRect().bottom;
  const blocks = [...el.children];
  let keep = blocks.length;
  for (let b = 0; b < blocks.length; b++) {
    const block = blocks[b];
    if (block.getBoundingClientRect().bottom <= limit()) continue;
    const items = [...block.querySelectorAll("ul > li.ev")];
    const ul = block.querySelector("ul");
    const more = document.createElement("li");
    more.className = "more";
    ul.appendChild(more);
    let hidden = 0;
    while (block.getBoundingClientRect().bottom > limit() && hidden < items.length) {
      items[items.length - 1 - hidden].style.display = "none";
      hidden++;
      more.textContent = `+${hidden} more`;
    }
    const shown = items.length - hidden;
    keep = shown >= 1 && block.getBoundingClientRect().bottom <= limit() ? b + 1 : b;
    break;
  }
  blocks.slice(keep).forEach((n) => n.remove());
  const rest = days.slice(keep);
  if (!rest.length) return;
  const later = document.createElement("div");
  later.className = "later";
  later.innerHTML = `<h3>Later</h3>`;
  el.appendChild(later);
  for (const { d, evs } of rest) {
    const line = document.createElement("div");
    line.className = "lline";
    const titles = evs.map((e) => esc(e.summary)).join(" · ");
    line.innerHTML = `<span class="ld">${dow(d)} ${d.getDate()}</span><span class="lt">${titles || "—"}</span>`;
    later.appendChild(line);
    if (later.getBoundingClientRect().bottom > limit()) { line.remove(); break; }
  }
  if (later.children.length < 2) later.remove();
}

/* ---------------- Panels ---------------- */
function renderTodo(tasks) {
  const ul = $("todo");
  if (!tasks) { ul.innerHTML = ""; return; }
  const today = ymd(new Date());
  const longAgo = ymd(addDays(new Date(), -30));
  const multi = tasks.lists.length > 1;
  let html = "";
  for (const l of tasks.lists) {
    if (multi) html += `<li class="list-name">${esc(l.title)}</li>`;
    let old = 0;
    for (const t of l.items) {
      if (t.due && t.due < longAgo) { old++; continue; }   // overdue for over a month: summarized below
      let due = "";
      if (t.due) {
        const d = parseDay(t.due);
        const label = t.due === today ? "Today" : t.due === ymd(addDays(new Date(), 1)) ? "Tomorrow"
          : `${mon(d)} ${d.getDate()}`;
        due = `<span class="due${t.due < today ? " overdue" : ""}">${label}</span>`;
      }
      html += `<li><span>${esc(t.title)}</span>${due}</li>`;
    }
    if (old) html += `<li class="list-name">+ ${old} older overdue item${old > 1 ? "s" : ""}</li>`;
  }
  if (!tasks.lists.some((l) => l.items.length)) html = `<li class="empty">All done!</li>`;
  ul.innerHTML = html;
}

// "Coming up": countdown to the next all-day events (No school, holidays, birthdays…).
function renderCountdown(cal) {
  const el = $("countdown");
  if (!cal) { el.innerHTML = ""; return; }
  const today = ymd(new Date());
  const seen = new Set(), items = [];
  for (const e of [...cal.events].filter((e) => e.allDay && e.start > today).sort((a, b) => (a.start < b.start ? -1 : 1))) {
    const k = e.summary.trim().toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    items.push(e);
    if (items.length === 5) break;
  }
  if (!items.length) { el.innerHTML = ""; return; }
  el.innerHTML = `<h2>Coming Up</h2><ul>${items.map((e) => {
    const n = dayDiff(today, e.start), d = parseDay(e.start);
    return `<li><span class="cdot" style="background:${bg(e.colors || [e.color])}"></span>
      <span class="ctitle">${esc(e.summary)}</span>
      <span class="cwhen"><b>${n === 1 ? "Tomorrow" : `${n} days`}</b> · ${dow(d)} ${mon(d)} ${d.getDate()}</span></li>`;
  }).join("")}</ul>`;
}

function renderCfm(c) {
  $("cfm").innerHTML = c ? `<h2>Come Follow Me</h2>
    <div class="reading">${esc(c.reading)}</div>
    ${c.theme ? `<div class="theme">“${esc(c.theme)}”</div>` : ""}
    <div class="dates">${esc(c.dates)}</div>` : "";
}
function renderWotd(w) {
  $("wotd").innerHTML = w ? `<h2>Word of the Day</h2>
    <div class="word">${esc(w.word)}</div>
    <div class="meta">${w.pronunciation ? `\\${esc(w.pronunciation)}\\ · ` : ""}${esc(w.partOfSpeech)}</div>
    <div class="def">${esc(w.definition)}</div>` : "";
}
function renderJoke(j) {
  $("joke").innerHTML = j ? `<h2>Dad Joke</h2><p>${esc(j.joke)}</p>` : "";
}

// Fit the right-hand column: drop to-do items, then countdown items, until everything fits.
function fitSide() {
  const side = document.querySelector(".side");
  const over = () => side.scrollHeight > side.clientHeight + 1;
  for (const sel of ["#todo > li:not(.list-name)", "#countdown li"]) {
    const items = [...side.querySelectorAll(sel)];
    while (over() && items.length > 1) items.pop().remove();
  }
}

function renderKey(cal) {
  const cals = (cal && cal.calendars) || [];
  const show = settings.showKey !== false && cals.length > 1;
  $("key").innerHTML = show
    ? cals.map((c) => `<span><i style="background:${esc(c.color)}"></i>${esc(c.name)}</span>`).join("") : "";
  const hero = document.querySelector(".hero");
  hero.classList.toggle("has-key", show);
  // Lift the clock and weather above the key, however many lines it wraps to.
  requestAnimationFrame(() => hero.style.setProperty("--key-h", `${show ? $("key").offsetHeight : 0}px`));
}

function render(data) {
  const p = settings.panels || {};
  for (const [k, id] of [["todo", "panel-todo"], ["countdown", "countdown"], ["cfm", "cfm"], ["wotd", "wotd"], ["joke", "joke"]]) {
    $(id).classList.toggle("hidden", p[k] === false);
  }
  const cal = data.calendar ? { ...data.calendar, events: dedupe(data.calendar.events) } : null;
  renderWeather(data.weather);
  renderKey(cal);
  renderCalendar(cal, data.weather);
  renderAgenda(cal, data.weather);
  renderTodo(data.tasks);
  renderCountdown(cal);
  renderCfm(data.cfm);
  renderWotd(data.wotd);
  renderJoke(data.joke);
  requestAnimationFrame(fitSide);
  const errs = Object.entries(data.errors || {});
  $("status").textContent = errs.length ? `⚠ ${errs.map(([k]) => k).join(", ")}` : "";
  $("status").title = errs.map(([k, v]) => `${k}: ${v}`).join("\n");
}

async function load() {
  try {
    const r = await fetch("/api/data", { cache: "no-store" });
    const data = await r.json();
    const s = JSON.stringify(data);
    if (data.settings) settings = { ...settings, ...data.settings };
    if (!lastData || s !== JSON.stringify(lastData)) { render(data); if (data.photosVersion !== lastData?.photosVersion) loadPhotos(); }
    lastData = data;
  } catch (e) {
    $("status").textContent = "⚠ offline";
  }
}

/* ---------------- Photos + videos ---------------- */
// Photos show for the set interval; videos play once, muted, from start to finish.
let media = [], mediaIdx = 0, front = "photoA", mediaTimer = null;
const MAX_VIDEO_SECONDS = 180;  // a very long video still moves on after 3 minutes
async function loadPhotos() {
  try {
    const r = await fetch("/api/photos", { cache: "no-store" });
    const list = (await r.json()).items || [];
    // No photos yet: give the calendar the space instead of an empty picture area.
    const had = document.body.classList.contains("no-photos");
    document.body.classList.toggle("no-photos", !list.length);
    if (had !== !list.length && lastData) render(lastData);
    const sig = (l) => l.map((m) => m.url).sort().join();
    if (sig(list) !== sig(media)) {
      media = list.sort(() => Math.random() - 0.5);
      mediaIdx = 0;
      nextMedia();
    }
  } catch (e) { /* keep what's showing */ }
}
function scheduleNext(seconds) {
  clearTimeout(mediaTimer);
  mediaTimer = setTimeout(nextMedia, seconds * 1000);
}
function swapTo(back, fill) {
  fill($(back));
  $(back).classList.add("show");
  const old = $(front);
  old.classList.remove("show");
  setTimeout(() => { if (!old.classList.contains("show")) { old.innerHTML = ""; old.style.backgroundImage = ""; } }, 3000);
  front = back;
}
function nextMedia() {
  clearTimeout(mediaTimer);
  if (!media.length) return;
  const item = media[mediaIdx++ % media.length];
  const back = front === "photoA" ? "photoB" : "photoA";
  const interval = Math.max(10, settings.photoIntervalSeconds);
  if (!item.video) {
    const img = new Image();
    img.onload = () => swapTo(back, (el) => { el.innerHTML = ""; el.style.backgroundImage = `url("${item.url}")`; });
    img.onerror = () => scheduleNext(1);
    img.src = item.url;
    scheduleNext(interval);
    return;
  }
  const v = document.createElement("video");
  v.muted = true; v.defaultMuted = true; v.volume = 0;   // never any sound
  v.setAttribute("muted", ""); v.playsInline = true; v.preload = "auto";
  v.src = item.url;
  let started = false;
  v.oncanplay = () => {
    if (started) return;
    started = true;
    swapTo(back, (el) => { el.style.backgroundImage = ""; el.innerHTML = ""; el.appendChild(v); });
    v.play().catch(() => scheduleNext(1));
    const secs = isFinite(v.duration) && v.duration > 0 ? Math.min(v.duration, MAX_VIDEO_SECONDS) : interval;
    scheduleNext(secs + 1);   // backup in case "ended" never fires
  };
  v.onended = () => nextMedia();
  v.onerror = () => scheduleNext(1);   // unsupported format: skip it
  scheduleNext(20);                    // didn't start loading within 20 s: skip it
}

/* ---------------- View rotation ---------------- */
let viewIdx = 0, viewTimer = null, timersKey = "";
const FORCED_VIEW = new URLSearchParams(location.search).get("view");  // settings-page preview
if (FORCED_VIEW) document.documentElement.classList.add("preview");
function showView() {
  const views = (settings.views || []).filter((v) => $(`view-${v}`));
  if (!views.length) views.push("month");
  const name = FORCED_VIEW && $(`view-${FORCED_VIEW}`) ? FORCED_VIEW : views[viewIdx % views.length];
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
}
function applyTimers() {
  const key = [settings.views.join(), settings.viewSeconds].join("|");
  if (key === timersKey) return;
  timersKey = key;
  clearInterval(viewTimer);
  viewIdx = 0; showView();
  viewTimer = setInterval(() => { viewIdx++; showView(); }, Math.max(5, settings.viewSeconds) * 1000);
}

/* ---------------- Start ---------------- */
tick();
setInterval(tick, 1000);
loadPhotos().then(load).then(() => { applyTimers(); });
setInterval(() => load().then(applyTimers), 30 * 1000);
setInterval(loadPhotos, 10 * 60 * 1000);
window.addEventListener("resize", () => lastData && render(lastData));
