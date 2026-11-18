"use strict";

const $ = (id) => document.getElementById(id);
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
  "September", "October", "November", "December"];
let settings = { clock24h: false, showSeconds: true, photoIntervalSeconds: 60,
  views: ["month", "list"], viewSeconds: 45, agendaDays: 14, panels: {} };
let lastData = null;
let lastDay = new Date().getDate();

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parseDay = (s) => { const [y, m, d] = s.slice(0, 10).split("-").map(Number); return new Date(y, m - 1, d); };
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };

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

/* ---------------- Clock ---------------- */
function tick() {
  const now = new Date();
  let h = now.getHours();
  let ampm = "";
  if (!settings.clock24h) { ampm = h >= 12 ? "PM" : "AM"; h = h % 12 || 12; }
  $("hm").textContent = `${settings.clock24h ? pad(h) : h}:${pad(now.getMinutes())}`;
  $("sec").textContent = settings.showSeconds ? pad(now.getSeconds()) : "";
  $("ampm").textContent = settings.showSeconds ? "" : ampm;
  $("date").textContent = `${DAYS[now.getDay()]}, ${MONTHS[now.getMonth()]} ${now.getDate()}`;
  if (now.getDate() !== lastDay) { lastDay = now.getDate(); if (lastData) render(lastData); load(); }
}

/* ---------------- Weather ---------------- */
function renderWeather(w) {
  if (!w) { $("weather").innerHTML = ""; return; }
  const today = ymd(new Date());
  const t = w.days.find((d) => d.date === today) || w.days[0];
  const next = w.days.filter((d) => d.date > today).slice(0, 3);
  $("weather").innerHTML = `
    <div class="now"><span class="icon">${iconFor(w.code, w.isDay)}</span><span class="temp">${w.temp}°</span></div>
    <div class="desc">${esc(describe(w.code))}</div>
    <div class="feels">Feels like ${w.feels}° · ${t.hi}° / ${t.lo}° · ${t.pop ?? 0}% rain</div>
    <div class="days">${next.map((d) => `
      <div class="day"><span class="name">${DAYS[parseDay(d.date).getDay()].slice(0, 3)}</span>
        <span class="icon">${iconFor(d.code)}</span><span>${d.hi}° <span class="lo">${d.lo}°</span></span></div>`).join("")}
    </div>`;
}

/* ---------------- Calendar ---------------- */
function fmtTime(d) {
  let h = d.getHours(); const m = d.getMinutes();
  if (settings.clock24h) return `${pad(h)}:${pad(m)}`;
  const ap = h >= 12 ? "p" : "a"; h = h % 12 || 12;
  return `${h}${m ? `<sup>${pad(m)}</sup>` : ""}${ap}`;
}

function eventsByDay(events) {
  const byDay = {};
  const push = (key, ev) => (byDay[key] ||= []).push(ev);
  for (const e of events) {
    if (e.allDay) {
      for (let d = parseDay(e.start); d < parseDay(e.end); d = addDays(d, 1)) push(ymd(d), e);
    } else {
      push(ymd(new Date(e.start)), e);
    }
  }
  for (const k in byDay) {
    byDay[k].sort((a, b) => (b.allDay - a.allDay) || (a.allDay ? 0 : new Date(a.start) - new Date(b.start)));
  }
  return byDay;
}

function eventLi(e, withEnd) {
  if (e.allDay) return `<li class="ev allday" style="background:${esc(e.color)}">${esc(e.summary)}</li>`;
  const s = new Date(e.start), en = new Date(e.end);
  const t = withEnd && en > s ? `${fmtTime(s)}–${fmtTime(en)}` : fmtTime(s);
  return `<li class="ev"><span class="dot" style="background:${esc(e.color)}"></span>
    <span class="txt"><span class="t">${t}</span> ${esc(e.summary)}</span></li>`;
}

function renderCalendar(cal, weather) {
  const el = $("calendar");
  if (!cal) { el.innerHTML = ""; return; }
  const start = parseDay(cal.start), end = parseDay(cal.end);
  const todayKey = ymd(new Date());
  const fc = Object.fromEntries((weather?.days || []).map((d) => [d.date, d]));

  const byDay = eventsByDay(cal.events);
  let html = ["S", "M", "T", "W", "T", "F", "S"]
    .map((d, i) => `<div class="dow${i % 6 === 0 ? " weekend" : ""}">${d}</div>`).join("");
  for (let d = new Date(start), i = 0; d < end; d = addDays(d, 1), i++) {
    const key = ymd(d);
    const cls = ["cell"];
    if (d.getDay() % 6 === 0) cls.push("weekend");
    if (key === todayKey) cls.push("today");
    if (key < todayKey) cls.push("past");
    const showMonth = i === 0 || d.getDate() === 1;
    const f = fc[key];
    const evs = (byDay[key] || []).map((e) => eventLi(e, false)).join("");
    html += `<div class="${cls.join(" ")}">
      <div class="head">
        <div class="num${showMonth && key !== todayKey ? " month" : ""}">${showMonth && key !== todayKey ? MONTHS[d.getMonth()].slice(0, 3) : d.getDate()}</div>
        ${f && key >= todayKey ? `<div class="fc">${iconFor(f.code)}<span class="hi">${f.hi}°</span> ${f.lo}°</div>` : ""}
      </div>
      <ul class="events">${evs}</ul></div>`;
  }
  el.innerHTML = html;
  requestAnimationFrame(trimOverflow);
}

// Hide events that don't fit in a day box and show "+N more" instead.
function trimOverflow() {
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

/* ---------------- Agenda (list view) ---------------- */
function renderAgenda(cal, weather) {
  const el = $("agenda");
  if (!cal) { el.innerHTML = ""; return; }
  const byDay = eventsByDay(cal.events);
  const fc = Object.fromEntries((weather?.days || []).map((d) => [d.date, d]));
  const today = new Date();
  const now = Date.now();
  let html = "";
  for (let i = 0; i < settings.agendaDays; i++) {
    const d = addDays(today, i), key = ymd(d);
    let evs = byDay[key] || [];
    if (i === 0) evs = evs.filter((e) => e.allDay || new Date(e.end) > now); // hide finished events
    if (!evs.length && i > 1) continue;  // skip empty days after tomorrow
    const name = i === 0 ? "Today" : i === 1 ? "Tomorrow" : DAYS[d.getDay()];
    const f = fc[key];
    html += `<div class="aday${i === 0 ? " today" : ""}">
      <div class="anum">${i === 0 ? `<span>${d.getDate()}</span>` : d.getDate()}</div>
      <div class="ahead"><span class="aname">${name}${i > 6 ? ` <span style="color:var(--muted)">${MONTHS[d.getMonth()].slice(0, 3)}</span>` : ""}</span>
        ${f ? `<span class="afc">${iconFor(f.code)}<span class="hi">${f.hi}°</span> ${f.lo}°</span>` : ""}</div>
      <ul>${evs.length ? evs.map((e) => eventLi(e, true)).join("") : `<li class="none">Nothing scheduled</li>`}</ul>
    </div>`;
  }
  el.innerHTML = html;
  requestAnimationFrame(() => {
    const days = [...el.children];
    while (el.scrollHeight > el.clientHeight + 1 && days.length > 1) days.pop().remove();
  });
}

/* ---------------- Panels ---------------- */
function renderTodo(tasks) {
  const ul = $("todo");
  if (!tasks) { ul.innerHTML = ""; return; }
  const today = ymd(new Date());
  const multi = tasks.lists.length > 1;
  let html = "";
  for (const l of tasks.lists) {
    if (multi) html += `<li class="list-name">${esc(l.title)}</li>`;
    for (const t of l.items) {
      let due = "";
      if (t.due) {
        const d = parseDay(t.due);
        const label = t.due === today ? "Today" : t.due === ymd(addDays(new Date(), 1)) ? "Tomorrow"
          : `${MONTHS[d.getMonth()].slice(0, 3)} ${d.getDate()}`;
        due = `<span class="due${t.due < today ? " overdue" : ""}">${label}</span>`;
      }
      html += `<li><span>${esc(t.title)}</span>${due}</li>`;
    }
  }
  if (!tasks.lists.some((l) => l.items.length)) html = `<li class="empty">All done!</li>`;
  ul.innerHTML = html;
  // Drop items that don't fit.
  requestAnimationFrame(() => {
    const panel = ul.closest(".side");
    const items = [...ul.children];
    while (panel.scrollHeight > panel.clientHeight + 1 && items.length > 1) items.pop().remove();
  });
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
  for (const [k, id] of [["todo", "panel-todo"], ["cfm", "cfm"], ["wotd", "wotd"], ["joke", "joke"]]) {
    $(id).classList.toggle("hidden", p[k] === false);
  }
  renderWeather(data.weather);
  renderKey(data.calendar);
  renderCalendar(data.calendar, data.weather);
  renderAgenda(data.calendar, data.weather);
  renderCfm(data.cfm);
  renderWotd(data.wotd);
  renderJoke(data.joke);
  renderTodo(data.tasks);
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

/* ---------------- Photos ---------------- */
let photos = [], photoIdx = 0, front = "photoA";
async function loadPhotos() {
  try {
    const r = await fetch("/api/photos", { cache: "no-store" });
    const list = (await r.json()).photos;
    if (list.join() !== [...photos].sort().join()) {
      photos = list.sort(() => Math.random() - 0.5);
      photoIdx = 0;
      if (photos.length) nextPhoto();
    }
  } catch (e) { /* keep current photos */ }
}
function nextPhoto() {
  if (!photos.length) return;
  const url = photos[photoIdx++ % photos.length];
  const img = new Image();
  img.onload = () => {
    const back = front === "photoA" ? "photoB" : "photoA";
    $(back).style.backgroundImage = `url("${url}")`;
    $(back).classList.add("show");
    $(front).classList.remove("show");
    front = back;
  };
  img.src = url;
}

/* ---------------- View rotation ---------------- */
let viewIdx = 0, viewTimer = null, photoTimer = null, timersKey = "";
function showView() {
  const views = (settings.views || []).filter((v) => $(`view-${v}`));
  if (!views.length) views.push("month");
  const name = views[viewIdx % views.length];
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
}
function applyTimers() {
  const key = [settings.views.join(), settings.viewSeconds, settings.photoIntervalSeconds].join("|");
  if (key === timersKey) return;
  timersKey = key;
  clearInterval(viewTimer); clearInterval(photoTimer);
  viewIdx = 0; showView();
  viewTimer = setInterval(() => { viewIdx++; showView(); }, Math.max(5, settings.viewSeconds) * 1000);
  photoTimer = setInterval(nextPhoto, Math.max(10, settings.photoIntervalSeconds) * 1000);
}

/* ---------------- Start ---------------- */
tick();
setInterval(tick, 1000);
load().then(() => { applyTimers(); loadPhotos(); });
setInterval(() => load().then(applyTimers), 30 * 1000);
setInterval(loadPhotos, 10 * 60 * 1000);
window.addEventListener("resize", () => lastData && render(lastData));
