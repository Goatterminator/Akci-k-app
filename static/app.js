// Akciók – frontend (vanilla JS, build lépés nélkül)

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const view = $("#view");

// ------------------------------------------------------------------ segédek
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const fmtNum = (n, d = 0) =>
  n == null ? "" : Number(n).toLocaleString("hu-HU", { maximumFractionDigits: d, minimumFractionDigits: d });

function fmtPrice(item, field = "price") {
  const v = item[field];
  if (v == null) return "";
  if (item.currency === "EUR") return `${fmtNum(v, 2)} €`;
  return `${fmtNum(v)} Ft`;
}

function hufHint(item) {
  if (item.currency !== "EUR" || item.price_huf == null) return "";
  return `≈ ${fmtNum(item.price_huf)} Ft`;
}

function relTime(iso) {
  if (!iso) return "soha";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "most";
  if (diff < 3600) return `${Math.floor(diff / 60)} perce`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} órája`;
  return `${Math.floor(diff / 86400)} napja`;
}

function untilText(iso) {
  if (!iso) return "";
  const ms = new Date(iso).getTime() - Date.now();
  if (ms < 0) return "lejárt";
  const h = ms / 3600000;
  if (h < 24) return `még ${Math.max(1, Math.floor(h))} óráig`;
  const d = Math.floor(h / 24);
  return d === 1 ? "holnapig" : `még ${d} napig`;
}

function countdown(iso) {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "lejárt";
  const d = Math.floor(ms / 86400000);
  const h = Math.floor((ms % 86400000) / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  return d > 0 ? `${d} nap ${h} óra` : `${h} óra ${m} perc`;
}

function fmtDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("hu-HU", { month: "short", day: "numeric", weekday: "short" });
}

async function api(path, opts = {}) {
  const init = { headers: {}, ...opts };
  if (opts.body && typeof opts.body !== "string") {
    init.body = JSON.stringify(opts.body);
    init.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, init);
  let data = null;
  try { data = await res.json(); } catch { /* üres válasz */ }
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    showAuth();
    throw new Error("Bejelentkezés szükséges");
  }
  if (!res.ok) {
    const d = data && data.detail;
    throw new Error(Array.isArray(d) ? "Hibás adatok – ellenőrizd a mezőket." : d || `Hiba (${res.status})`);
  }
  return data;
}

let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
}

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* privát mód */ } },
};

const ICONS = {
  deals: '<svg viewBox="0 0 24 24"><path d="M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><circle cx="7" cy="7" r="1.5"/></svg>',
  ai: '<svg viewBox="0 0 24 24"><path d="M12 3l1.9 4.8L18.7 9.7l-4.8 1.9L12 16.4l-1.9-4.8L5.3 9.7l4.8-1.9z"/><path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z"/></svg>',
  coupons: '<svg viewBox="0 0 24 24"><path d="M3 9a3 3 0 0 0 0 6v3a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3a3 3 0 0 0 0-6V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2z"/><path d="M13 5v2M13 17v2M13 11v2"/></svg>',
  games: '<svg viewBox="0 0 24 24"><rect x="2" y="6" width="20" height="12" rx="4"/><path d="M6 12h4M8 10v4"/><circle cx="15.5" cy="11" r=".8"/><circle cx="17.5" cy="13" r=".8"/></svg>',
  list: '<svg viewBox="0 0 24 24"><path d="M9 6h11M9 12h11M9 18h11"/><path d="m3 6 1 1 2-2M3 12l1 1 2-2M3 18l1 1 2-2"/></svg>',
  star: '<svg viewBox="0 0 24 24"><path d="m12 2 3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>',
  bell: '<svg viewBox="0 0 24 24"><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>',
  gear: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/></svg>',
  search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
  sun: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  moon: '<svg viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>',
  close: '<svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>',
  user: '<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
};

const ROUTES = [
  { path: "", label: "Akciók", title: "Top akciók", icon: "deals", nav: "both", render: renderDeals },
  { path: "ai", label: "AI kereső", title: "AI kereső", icon: "ai", nav: "both", render: renderAi },
  { path: "kuponok", label: "Kuponok", title: "Gyorsétterem kuponok", icon: "coupons", nav: "both", render: renderCoupons },
  { path: "jatekok", label: "Játékok", title: "Játékok", icon: "games", nav: "both", render: renderGames },
  { path: "lista", label: "Lista", title: "Bevásárlólista", icon: "list", nav: "both", render: renderShopping },
  { path: "mentett", label: "Mentett", title: "Mentett akciók", icon: "star", nav: "side", render: renderFavorites },
  { path: "figyelo", label: "Figyelő", title: "Figyelő és értesítések", icon: "bell", nav: "side", render: renderWatches },
  { path: "profil", label: "Profil", title: "Profil", icon: "user", nav: "side", render: renderProfile },
  { path: "beallitasok", label: "Admin beállítások", title: "Admin beállítások", icon: "gear", nav: "side", admin: true, render: renderSettings },
];

let META = { user: null, categories: [], stores: [], ai_enabled: false, unseen_alerts: 0, refresh: {} };
const isAdmin = () => !!(META.user && META.user.is_admin);
const STORE_COLORS = () => Object.fromEntries(META.stores.map((s) => [s.name, s.color]));

// ------------------------------------------------------------------ téma
function applyTheme() {
  const t = store.get("theme", "auto");
  if (t === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
  const dark = t === "dark" || (t === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  $("#theme-btn").innerHTML = dark ? ICONS.sun : ICONS.moon;
}
$("#theme-btn").addEventListener("click", () => {
  const dark = document.documentElement.getAttribute("data-theme") === "dark" ||
    (!document.documentElement.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
  store.set("theme", dark ? "light" : "dark");
  applyTheme();
});

// ------------------------------------------------------------------ navigáció
function buildNav() {
  const cur = currentPath();
  const item = (r) =>
    `<a class="nav-item ${r.path === cur ? "active" : ""}" href="#/${r.path}">${ICONS[r.icon]}<span>${r.label}</span></a>`;
  $("#bottom-nav").innerHTML = ROUTES.filter((r) => r.nav === "both").map(item).join("");
  const main = ROUTES.filter((r) => r.nav === "both").map(item).join("");
  const side = ROUTES.filter((r) => r.nav === "side" && (!r.admin || isAdmin())).map(item).join("");
  $("#side-nav").innerHTML = main + '<div class="sep"></div>' + side;
}

function currentPath() {
  return location.hash.replace(/^#\/?/, "").split("?")[0];
}

async function router() {
  const path = currentPath();
  let route = ROUTES.find((r) => r.path === path) || ROUTES[0];
  if (route.admin && !isAdmin()) route = ROUTES.find((r) => r.path === "profil");
  document.title = route.path ? `${route.label} · Akciók` : "Akciók";
  $("#page-title").textContent = route.title;
  buildNav();
  view.innerHTML = "";
  window.scrollTo(0, 0);
  try {
    await route.render(view);
  } catch (e) {
    view.innerHTML = `<div class="empty"><div class="big">⚠️</div><div>${esc(e.message)}</div></div>`;
  }
}

// ------------------------------------------------------------------ meta + frissítés állapot
async function loadMeta() {
  try {
    META = await api("/api/meta");
  } catch { return; }
  const gear = $("#gear-link");
  gear.href = isAdmin() ? "#/beallitasok" : "#/profil";
  gear.title = isAdmin() ? "Admin beállítások" : "Profil";
  gear.setAttribute("aria-label", gear.title);
  $("#alert-dot").hidden = !META.unseen_alerts;
  $("#side-status").textContent = META.last_refresh ? `Adatok frissítve ${relTime(META.last_refresh)}` : "Még nincs adat";
  const r = META.refresh || {};
  const banner = $("#refresh-banner");
  if (r.running) {
    banner.hidden = false;
    banner.innerHTML = `<span class="spinner"></span> Frissítés folyamatban: <b>${esc(r.current || "")}</b>…`;
  } else banner.hidden = true;
}

let wasRunning = false;
setInterval(async () => {
  if (document.body.classList.contains("auth-mode")) return;
  await loadMeta();
  const running = !!(META.refresh && META.refresh.running);
  if (wasRunning && !running && ["", "jatekok", "kuponok"].includes(currentPath())) router();
  wasRunning = running;
}, 15000);

// ------------------------------------------------------------------ kártya
function imgOrPlaceholder(item, cls = "") {
  const cat = META.categories.find((c) => c.key === item.category);
  const ph = `<span class="ph">${cat ? cat.icon : "🏷️"}</span>`;
  if (!item.image) return `<div class="deal-img ${cls}">${ph}</div>`;
  return `<div class="deal-img ${cls}"><img loading="lazy" referrerpolicy="no-referrer" src="${esc(item.image)}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'ph',textContent:'${cat ? cat.icon : "🏷️"}'}))"></div>`;
}

function discBadge(item) {
  if (item.kind === "free_game" || (item.discount_pct === 100 && item.price === 0)) return `<span class="disc free">INGYEN</span>`;
  if (item.discount_pct) return `<span class="disc">-${Math.round(item.discount_pct)}%</span>`;
  return "";
}

const CARD_APPS = new Map(); // tétel id -> a lánc appjának adatai (kuponoknál)

function dealCard(item, { reason } = {}) {
  const color = STORE_COLORS()[item.store] || "var(--text-3)";
  const until = item.valid_to ? untilText(item.valid_to) : "";
  const isGame = item.category === "jatek";
  const tags = [];
  if (item.badge) tags.push(`<span class="tag ${/hűség|plus/i.test(item.badge) ? "warn" : ""}">${esc(item.badge)}</span>`);
  if (until) tags.push(`<span class="tag ${/óráig|holnap/.test(until) ? "hot" : ""}">${until}</span>`);
  const app = item.extra && item.extra.app && item.extra.app.link ? item.extra.app : null;
  if (app) CARD_APPS.set(item.id, app);
  const unit = item.unit_price && item.unit && item.source === "arfigyelo"
    ? `<span>${fmtNum(item.unit_price)} Ft/${esc(item.unit)}</span>`
    : item.unit && item.source === "lidl" && /=/.test(item.unit) ? `<span>${esc(item.unit)}</span>` : "";
  return `
  <article class="deal" data-id="${esc(item.id)}" tabindex="0">
    ${imgOrPlaceholder(item, isGame ? "cover" : "")}
    ${discBadge(item)}
    <button class="fav-btn ${item.favorite ? "on" : ""}" data-fav="${esc(item.id)}" aria-label="Mentés">${ICONS.star}</button>
    <div class="deal-body">
      <span class="store-pill"><i style="background:${color}"></i>${esc(item.store)}</span>
      <div class="deal-title">${esc(item.title)}</div>
      ${tags.length ? `<div class="meta">${tags.join("")}</div>` : ""}
      <div class="price-row">
        ${item.price != null ? `<span class="price">${item.price === 0 ? "0 Ft" : fmtPrice(item)}</span>` : `<span class="muted small">ár az appban</span>`}
        ${item.old_price ? `<span class="old">${fmtPrice(item, "old_price")}</span>` : ""}
      </div>
      ${hufHint(item) || unit ? `<div class="meta">${hufHint(item) ? `<span>${hufHint(item)}</span>` : ""}${unit}</div>` : ""}
      ${reason ? `<div class="reason">✨ ${esc(reason)}</div>` : ""}
      ${app ? `<div class="app-open">📱 Megnyitás a ${esc(app.name)} appban</div>` : ""}
    </div>
  </article>`;
}

// ------------------------------------------------------------------ lánc appjának megnyitása (kuponok)
const IS_ANDROID = /Android/i.test(navigator.userAgent);
const IS_IOS = /iPhone|iPad|iPod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

function appOpenUrl(app) {
  // Androidon "intent" link: biztosan az appot nyitja meg, ha nincs telepítve, a Play Áruházat.
  if (IS_ANDROID && app.android_package) {
    const u = new URL(app.link);
    return `intent://${u.host}${u.pathname}${u.search}#Intent;scheme=https;package=${app.android_package};` +
      `S.browser_fallback_url=${encodeURIComponent(app.play || app.link)};end`;
  }
  // iPhone-on a lánc linkje (Universal Link) nyitja meg az appot; gépen a weboldalt.
  return app.link;
}

function openApp(app) {
  const url = appOpenUrl(app);
  if (IS_ANDROID || IS_IOS) window.location.href = url;  // ugyanabban a lapon: így vált át az appra
  else window.open(url, "_blank", "noopener");
}

function bindCards(root) {
  root.addEventListener("click", async (e) => {
    const fav = e.target.closest("[data-fav]");
    if (fav) {
      e.stopPropagation();
      await toggleFav(fav.dataset.fav, fav);
      return;
    }
    const card = e.target.closest(".deal");
    if (!card) return;
    // kupon: rányomásra a lánc appja nyílik meg (KFC, Burger King)
    const app = CARD_APPS.get(card.dataset.id);
    if (app) openApp(app);
    else openDetail(card.dataset.id);
  });
  root.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.classList.contains("deal")) openDetail(e.target.dataset.id);
  });
}

async function toggleFav(id, btn) {
  const on = btn.classList.contains("on");
  try {
    await api(`/api/favorites/${encodeURIComponent(id)}`, { method: on ? "DELETE" : "POST" });
    $$(`[data-fav="${CSS.escape(id)}"]`).forEach((b) => b.classList.toggle("on", !on));
    toast(on ? "Eltávolítva a mentettek közül" : "Elmentve ⭐");
  } catch (e) { toast(e.message); }
}

function skeletonGrid(n = 8) {
  return `<div class="grid">${Array.from({ length: n }, () => '<div class="skeleton sk-card"></div>').join("")}</div>`;
}

function emptyState(icon, text, extra = "") {
  return `<div class="empty"><div class="big">${icon}</div><div>${text}</div>${extra}</div>`;
}

// ------------------------------------------------------------------ részletek
const sheet = $("#sheet");
sheet.addEventListener("click", (e) => { if (e.target === sheet) sheet.close(); });

function sparkline(history) {
  const pts = history.filter((h) => h.price != null);
  if (pts.length < 2) return "";
  const W = 600, H = 90, P = 8;
  const prices = pts.map((p) => p.price);
  const min = Math.min(...prices), max = Math.max(...prices);
  const t0 = new Date(pts[0].day).getTime(), t1 = new Date(pts[pts.length - 1].day).getTime() || t0 + 1;
  const x = (d) => P + ((new Date(d).getTime() - t0) / Math.max(1, t1 - t0)) * (W - 2 * P);
  const y = (v) => H - P - ((v - min) / Math.max(1, max - min)) * (H - 2 * P);
  // lépcsős görbe: az ár a következő változásig érvényes
  let d = `M${x(pts[0].day)},${y(pts[0].price)}`;
  for (let i = 1; i < pts.length; i++) d += ` H${x(pts[i].day)} V${y(pts[i].price)}`;
  d += ` H${W - P}`;
  const area = `${d} V${H} H${P} Z`;
  const last = pts[pts.length - 1];
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Árelőzmény">
    <path class="area" d="${area}" opacity=".6"/><path class="line" d="${d}"/>
    <circle cx="${W - P}" cy="${y(last.price)}" r="4"/></svg>
    <div class="row small muted"><span>${fmtDate(pts[0].day)}</span><span class="grow"></span><span>min ${fmtNum(min)} · max ${fmtNum(max)}</span></div>`;
}

async function openDetail(id) {
  $("#sheet-body").innerHTML = `<div class="loading"><span class="spinner"></span> Betöltés…</div>`;
  if (!sheet.open) sheet.showModal();
  let item;
  try {
    item = await api(`/api/items/${encodeURIComponent(id)}`);
  } catch (e) {
    $("#sheet-body").innerHTML = emptyState("⚠️", esc(e.message));
    return;
  }
  const color = STORE_COLORS()[item.store] || "var(--text-3)";
  const pc = item.price_check || {};
  const verdictIcon = { good: "✅", ok: "👍", meh: "🤔", bad: "⚠️", unknown: "ℹ️" }[pc.verdict] || "ℹ️";
  const others = (item.other_stores || []).map((o) => `
    <div class="list-row" data-other="${esc(o.id)}" style="cursor:pointer">
      <span class="store-pill grow"><i style="background:${STORE_COLORS()[o.store] || "#999"}"></i>${esc(o.store)}
      ${o.discount_pct ? `<span class="tag hot">-${Math.round(o.discount_pct)}%</span>` : ""}</span>
      <span class="p">${fmtPrice(o)}</span>
    </div>`).join("");
  const isGame = item.category === "jatek";
  $("#sheet-body").innerHTML = `
    <div class="sheet-close"><button class="icon-btn" aria-label="Bezárás" id="sheet-x">${ICONS.close}</button></div>
    <div class="detail-img ${isGame ? "cover" : ""}">${item.image ? `<img src="${esc(item.image)}" alt="" referrerpolicy="no-referrer">` : ""}</div>
    <div class="detail">
      <div class="row"><span class="store-pill"><i style="background:${color}"></i>${esc(item.store)}</span>
        ${item.badge ? `<span class="tag">${esc(item.badge)}</span>` : ""}
        ${discBadge(item).replace('class="disc', 'style="position:static" class="disc')}
      </div>
      <h2>${esc(item.title)}</h2>
      ${item.description ? `<div class="muted small">${esc(item.description)}</div>` : ""}
      <div class="price-row">
        ${item.price != null ? `<span class="price">${fmtPrice(item)}</span>` : `<span class="muted">Az ár a bolt appjában látható</span>`}
        ${item.old_price ? `<span class="old">${fmtPrice(item, "old_price")}</span>` : ""}
        ${item.old_price && item.price != null ? `<span class="tag good">${fmtNum(item.old_price - item.price, item.currency === "EUR" ? 2 : 0)} ${item.currency === "EUR" ? "€" : "Ft"} megtakarítás</span>` : ""}
      </div>
      ${hufHint(item) ? `<div class="muted small">${hufHint(item)} (beállított árfolyammal)</div>` : ""}
      ${item.unit_price && item.unit ? `<div class="muted small">Egységár: ${fmtNum(item.unit_price)} Ft/${esc(item.unit)}</div>` : ""}
      ${item.valid_from || item.valid_to ? `<div class="small">📅 ${item.valid_from ? fmtDate(item.valid_from) : ""} – ${item.valid_to ? fmtDate(item.valid_to) : ""} ${item.valid_to ? `<b>(${untilText(item.valid_to)})</b>` : ""}</div>` : ""}
      ${["deal", "normal"].includes(item.kind) ? `<div class="verdict ${pc.verdict}"><span>${verdictIcon}</span><span><b>Valódi akció?</b> ${esc(pc.text || "")}</span></div>` : ""}
      ${item.history && item.history.length > 1 ? `<div><div class="small" style="font-weight:600;margin-bottom:6px">Árelőzmény</div>${sparkline(item.history)}</div>` : ""}
      ${others ? `<div><div class="small" style="font-weight:600">Ugyanez más boltokban</div><div class="list">${others}</div></div>` : ""}
      <div class="actions">
        ${item.extra && item.extra.app && item.extra.app.link
          ? `<button class="btn primary" id="d-app">📱 Megnyitás a ${esc(item.extra.app.name)} appban</button>`
          : item.url ? `<a class="btn primary" href="${esc(item.url)}" target="_blank" rel="noopener">Megnyitás ↗</a>` : ""}
        <button class="btn" id="d-fav">${item.favorite ? "★ Mentve" : "☆ Mentés"}</button>
        <button class="btn" id="d-watch">🔔 Figyelő</button>
        ${item.source === "manual" && (isAdmin() || (item.extra || {}).added_by === META.user?.id) ? `<button class="btn" id="d-del">🗑 Törlés</button>` : ""}
      </div>
      <div class="muted small">Frissítve: ${relTime(item.last_seen)} · Forrás: ${esc(item.source)}</div>
    </div>`;
  $("#sheet-x").onclick = () => sheet.close();
  $("#d-fav").onclick = async () => {
    try {
      await api(`/api/favorites/${encodeURIComponent(item.id)}`, { method: item.favorite ? "DELETE" : "POST" });
      item.favorite = !item.favorite;
      $("#d-fav").textContent = item.favorite ? "★ Mentve" : "☆ Mentés";
      $$(`[data-fav="${CSS.escape(item.id)}"]`).forEach((b) => b.classList.toggle("on", item.favorite));
      toast(item.favorite ? "Elmentve ⭐" : "Eltávolítva");
    } catch (e) { toast(e.message); }
  };
  $("#d-watch").onclick = () => {
    sheet.close();
    const words = item.title.split(/\s+/).slice(0, 3).join(" ");
    location.hash = `#/figyelo?q=${encodeURIComponent(words)}`;
  };
  const appBtn = $("#d-app");
  if (appBtn) appBtn.onclick = () => openApp(item.extra.app);
  const del = $("#d-del");
  if (del) del.onclick = async () => {
    if (!confirm("Biztosan törlöd ezt a saját tételt?")) return;
    await api(`/api/manual/${encodeURIComponent(item.id)}`, { method: "DELETE" });
    sheet.close();
    toast("Törölve");
    router();
  };
  $$("[data-other]").forEach((r) => (r.onclick = () => openDetail(r.dataset.other)));
}

// ------------------------------------------------------------------ Akciók nézet
const DEFAULT_FILTERS = { q: "", category: "", stores: [], sort: "mix", min_discount: "", max_price: "", min_price: "", favorites: false };

async function renderDeals(root) {
  const f = { ...DEFAULT_FILTERS, ...store.get("filters", {}) };
  const sortOpts = [
    ["mix", "Legdurvább (vegyes boltok)"], ["discount", "Legnagyobb kedvezmény"], ["savings", "Legtöbb megtakarítás (Ft)"], ["price", "Legolcsóbb"],
    ["ending", "Hamarosan lejár"], ["newest", "Legújabb"],
  ];
  root.innerHTML = `
    <div class="search-wrap">${ICONS.search}<input class="input" id="f-q" type="search" placeholder="Keresés az akciók között… (pl. kávé, Parkside, pelenka)" value="${esc(f.q)}" autocomplete="off"></div>
    <div class="chips" id="f-cats" style="margin-top:12px"></div>
    <div class="filter-bar">
      <select class="select" id="f-sort">${sortOpts.map(([v, l]) => `<option value="${v}" ${f.sort === v ? "selected" : ""}>${l}</option>`).join("")}</select>
      <button class="chip ${f.favorites ? "on" : ""}" id="f-fav">★ Mentettek</button>
      <button class="chip" id="f-more">⚙︎ Szűrők${f.stores.length || f.min_discount || f.max_price || f.min_price ? " •" : ""}</button>
      <span class="result-count" id="f-count"></span>
    </div>
    <div class="filters card-box" id="f-panel" hidden>
      <div><div class="small muted" style="margin-bottom:6px">Boltok</div><div class="chips wrap" id="f-stores"></div></div>
      <div class="form-grid">
        <label class="field">Min. kedvezmény (%)<input class="input" id="f-mind" type="number" min="0" max="99" inputmode="numeric" value="${esc(f.min_discount)}" placeholder="pl. 30"></label>
        <label class="field">Min. ár (Ft)<input class="input" id="f-minp" type="number" min="0" inputmode="numeric" value="${esc(f.min_price)}"></label>
        <label class="field">Max. ár (Ft)<input class="input" id="f-maxp" type="number" min="0" inputmode="numeric" value="${esc(f.max_price)}"></label>
      </div>
      <div class="row"><button class="btn small" id="f-reset">Szűrők törlése</button></div>
    </div>
    <div id="f-results">${skeletonGrid()}</div>
    <div class="more"><button class="btn" id="f-load" hidden>Továbbiak betöltése</button></div>`;

  const cats = $("#f-cats");
  const renderCats = () => {
    cats.innerHTML = `<button class="chip ${!f.category ? "on" : ""}" data-cat="">Mind</button>` +
      META.categories.filter((c) => c.count > 0 || c.key === f.category)
        .map((c) => `<button class="chip ${f.category === c.key ? "on" : ""}" data-cat="${c.key}">${c.icon} ${c.label} <span class="count">${c.count}</span></button>`).join("");
  };
  const storesEl = $("#f-stores");
  const renderStores = () => {
    storesEl.innerHTML = META.stores.filter((s) => s.count > 0)
      .map((s) => `<button class="chip ${f.stores.includes(s.name) ? "on" : ""}" data-store="${esc(s.name)}"><span class="swatch" style="background:${s.color}"></span>${esc(s.name)} <span class="count">${s.count}</span></button>`).join("");
  };
  renderCats();
  renderStores();

  let offset = 0;
  const PAGE = 48;
  const results = $("#f-results");
  bindCards(results);

  const save = () => store.set("filters", f);
  async function load(reset = true) {
    if (reset) { offset = 0; results.innerHTML = skeletonGrid(); }
    const params = new URLSearchParams({ sort: f.sort, limit: PAGE, offset });
    if (f.q) params.set("q", f.q);
    if (f.category) params.set("category", f.category);
    // a játékoknak saját fülük van; a "Mind" nézetben csak akkor, ha kifejezetten keresel vagy szűrsz rájuk
    else if (!f.q && !f.stores.some((s) => ["Steam", "Epic Games"].includes(s))) params.set("exclude", "jatek");
    if (f.stores.length) params.set("stores", f.stores.join(","));
    if (f.min_discount) params.set("min_discount", f.min_discount);
    if (f.min_price) params.set("min_price", f.min_price);
    if (f.max_price) params.set("max_price", f.max_price);
    if (f.favorites) params.set("favorites", "true");
    // a gyorsétterem kategóriában a kuponok is látszódjanak
    params.set("kinds", f.category === "gyorsetterem" ? "deal,coupon" : f.category === "jatek" ? "deal,free_game" : "deal");
    let data;
    try {
      data = await api(`/api/deals?${params}`);
    } catch (e) {
      results.innerHTML = emptyState("⚠️", esc(e.message));
      return;
    }
    $("#f-count").textContent = `${fmtNum(data.total)} találat`;
    if (reset && !data.items.length) {
      const noData = META.stores.every((s) => !s.count);
      results.innerHTML = noData
        ? emptyState("⏳", "Még nincs adat. Az első frissítés pár perc, utána itt lesznek a legdurvább akciók.",
          isAdmin() ? `<button class="btn primary" id="first-refresh">Frissítés most</button>` : "")
        : emptyState("🔍", "Nincs a szűrésnek megfelelő akció.");
      const fr = $("#first-refresh");
      if (fr) fr.onclick = async () => { await api("/api/refresh", { method: "POST" }); toast("Frissítés elindult"); loadMeta(); };
      $("#f-load").hidden = true;
      return;
    }
    const html = data.items.map((i) => dealCard(i)).join("");
    if (reset) results.innerHTML = `<div class="grid">${html}</div>`;
    else $(".grid", results).insertAdjacentHTML("beforeend", html);
    offset += data.items.length;
    $("#f-load").hidden = offset >= data.total;
  }

  let qTimer;
  $("#f-q").addEventListener("input", (e) => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => { f.q = e.target.value.trim(); save(); load(); }, 300);
  });
  cats.addEventListener("click", (e) => {
    const b = e.target.closest("[data-cat]");
    if (!b) return;
    f.category = b.dataset.cat; save(); renderCats(); load();
  });
  storesEl.addEventListener("click", (e) => {
    const b = e.target.closest("[data-store]");
    if (!b) return;
    const s = b.dataset.store;
    f.stores = f.stores.includes(s) ? f.stores.filter((x) => x !== s) : [...f.stores, s];
    save(); renderStores(); load();
  });
  $("#f-sort").onchange = (e) => { f.sort = e.target.value; save(); load(); };
  $("#f-fav").onclick = (e) => { f.favorites = !f.favorites; e.target.classList.toggle("on", f.favorites); save(); load(); };
  $("#f-more").onclick = () => { $("#f-panel").hidden = !$("#f-panel").hidden; };
  const numInput = (id, key) => $(id).addEventListener("change", (e) => { f[key] = e.target.value; save(); load(); });
  numInput("#f-mind", "min_discount");
  numInput("#f-minp", "min_price");
  numInput("#f-maxp", "max_price");
  $("#f-reset").onclick = () => { Object.assign(f, DEFAULT_FILTERS, { q: f.q, category: f.category }); save(); renderDeals(root); };
  $("#f-load").onclick = () => load(false);
  await load();
}

// ------------------------------------------------------------------ AI nézet
const AI_EXAMPLES = [
  "olcsó mosógél 3000 Ft alatt",
  "akciós kávé, ami jó ár/érték",
  "akkus fúró vagy csavarbehajtó",
  "pelenka 4-es méret a legolcsóbban",
  "csirkemell a legjobb kilós áron",
  "ingyenes vagy nagyon olcsó jó PC játék",
];

async function renderAi(root) {
  const last = store.get("ai_last", null);
  root.innerHTML = `
    <div class="ai-hero">
      <h2>Mit keresel? ✨</h2>
      <div class="muted">Írd le természetes nyelven, az AI átnézi az összes aktuális akciót és normál árat, és kiválasztja a legjobbakat.</div>
      <form class="ai-box" id="ai-form">
        <input class="input grow" id="ai-q" placeholder="pl. olcsó mosógél 3000 Ft alatt" maxlength="300" autocomplete="off" value="${esc(last?.query || "")}">
        <button class="btn primary" type="submit">${ICONS.search.replace("<svg", '<svg style="width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2"')}<span>Keresés</span></button>
      </form>
      <div class="privacy-note"><span>🔒</span><span><b>Ne írj be személyes adatot</b> (név, cím, telefonszám, e-mail, kártyaszám stb.)! A keresést a Google Gemini dolgozza fel, és az ingyenes API kulcsnál a Google a beküldött szöveget felhasználhatja a szolgáltatás fejlesztésére.</span></div>
      <div class="form-grid">
        <label class="field">Termék típusa
          <select class="select" id="ai-cat"><option value="">Bármilyen</option>
            ${META.categories.map((c) => `<option value="${c.key}" ${last?.category === c.key ? "selected" : ""}>${c.icon} ${c.label}</option>`).join("")}
          </select></label>
        <label class="field">Min. ár (Ft)<input class="input" id="ai-min" type="number" min="0" inputmode="numeric" value="${esc(last?.min_price ?? "")}"></label>
        <label class="field">Max. ár (Ft)<input class="input" id="ai-max" type="number" min="0" inputmode="numeric" value="${esc(last?.max_price ?? "")}"></label>
      </div>
      <div class="row"><label class="toggle"><input type="checkbox" id="ai-deals" ${last?.only_deals ? "checked" : ""}> Csak akciós termékek</label>
        <span class="grow"></span>${META.ai_enabled && META.ai_limit != null ? `<span class="small muted" id="ai-quota">Ma: ${META.ai_today} / ${META.ai_limit} AI keresés</span>` : ""}</div>
      <div class="chips wrap" id="ai-ex">${AI_EXAMPLES.map((e) => `<button class="chip" type="button">${esc(e)}</button>`).join("")}</div>
      ${META.ai_enabled ? "" : `<div class="summary small">ℹ️ Még nincs Gemini API kulcs megadva, így egyszerű kulcsszavas keresés fut. ${isAdmin() ? `<a href="#/beallitasok">Kulcs megadása az Admin beállításokban →</a>` : "Az admin tudja beállítani."}</div>`}
    </div>
    <div id="ai-results" class="section"></div>`;

  const results = $("#ai-results");
  bindCards(results);

  async function run() {
    const body = {
      query: $("#ai-q").value.trim(),
      category: $("#ai-cat").value,
      min_price: $("#ai-min").value ? Number($("#ai-min").value) : null,
      max_price: $("#ai-max").value ? Number($("#ai-max").value) : null,
      only_deals: $("#ai-deals").checked,
    };
    if (body.query.length < 2) { toast("Írj be legalább 2 karaktert"); return; }
    store.set("ai_last", body);
    results.innerHTML = `<div class="loading"><span class="spinner"></span> ${META.ai_enabled ? "Az AI átnézi az ajánlatokat…" : "Keresés…"}</div>`;
    try {
      const data = await api("/api/ai/search", { method: "POST", body });
      loadMeta().then(() => { const q = $("#ai-quota"); if (q && META.ai_limit != null) q.textContent = `Ma: ${META.ai_today} / ${META.ai_limit} AI keresés`; });
      const kws = (data.keywords || []).map((k) => `<span class="tag">${esc(k)}</span>`).join("");
      results.innerHTML = `
        <div class="summary">${esc(data.summary)}
          ${kws ? `<div class="kw"><span class="small muted">Keresett szavak:</span>${kws}</div>` : ""}
          ${data.considered ? `<div class="small muted" style="margin-top:6px">${data.considered} tételt nézett át · ${data.seconds} mp</div>` : ""}
        </div>
        ${data.results.length ? `<div class="grid">${data.results.map((r) => dealCard(r.item, { reason: r.reason })).join("")}</div>` : ""}
        ${data.results.length ? `<div class="row" style="margin-top:14px"><button class="btn" id="ai-watch">🔔 Szólj, ha lesz új akció erre</button></div>` : ""}`;
      const w = $("#ai-watch");
      if (w) w.onclick = () => { location.hash = `#/figyelo?q=${encodeURIComponent((data.keywords || [body.query])[0])}`; };
    } catch (e) {
      results.innerHTML = emptyState("⚠️", esc(e.message));
    }
  }
  $("#ai-form").onsubmit = (e) => { e.preventDefault(); run(); };
  $("#ai-ex").onclick = (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    $("#ai-q").value = b.textContent;
    run();
  };
}

// ------------------------------------------------------------------ Kuponok
async function renderCoupons(root) {
  root.innerHTML = `<div class="loading"><span class="spinner"></span></div>`;
  const data = await api("/api/coupons");
  const order = ["KFC", "Burger King", "McDonald's"];
  const names = [...new Set([...order.filter((n) => data.stores[n]), ...Object.keys(data.stores)])];
  root.innerHTML = `
    <div class="card-box row">
      <div class="grow small">📱 <b>Nyomj rá egy kuponra</b>, és megnyílik a lánc appja a kuponoknál – ott a kupon számáról (pl. „Kupon #3”) gyorsan megtalálod. A <b>McDonald's</b> ajánlatai csak a MyMcDonald's appban vannak, azokat (és bármilyen más akciót) kézzel is felveheted.</div>
      <button class="btn primary small" id="add-manual">+ Saját akció</button>
    </div>
    ${names.length ? names.map((n) => `
      <section class="section">
        <div class="section-head"><h2>${esc(n)}</h2><span class="sub">${data.stores[n].length} kupon</span></div>
        <div class="grid">${data.stores[n].map((i) => dealCard(i)).join("")}</div>
      </section>`).join("") : emptyState("🍔", "Még nincsenek kuponok. Az első frissítés után itt lesznek.")}
    ${data.stores["Burger King"] && data.stores["Burger King"].some((i) => i.price == null) && !META.ai_enabled
      ? `<div class="summary small section">💡 A Burger King kuponok ára csak a képen szerepel. Ha megadsz Gemini kulcsot, az AI kiolvassa az árakat a képekről.</div>` : ""}`;
  bindCards(root);
  $("#add-manual").onclick = () => manualForm();
}

function manualForm() {
  $("#sheet-body").innerHTML = `
    <div class="sheet-close"><button class="icon-btn" aria-label="Bezárás" id="sheet-x">${ICONS.close}</button></div>
    <form class="detail" id="m-form">
      <h2>Saját akció hozzáadása</h2>
      <div class="muted small">Pl. egy McDonald's app kupon, vagy egy akció, amit szórólapon láttál.</div>
      <label class="field">Bolt / lánc<input class="input" name="store" list="m-stores" required value="McDonald's"></label>
      <datalist id="m-stores">${META.stores.map((s) => `<option value="${esc(s.name)}">`).join("")}</datalist>
      <label class="field">Mi az ajánlat?<input class="input" name="title" required placeholder="pl. 2 db McChicken 1490 Ft"></label>
      <div class="form-grid">
        <label class="field">Ár (Ft)<input class="input" name="price" type="number" min="0" inputmode="numeric"></label>
        <label class="field">Eredeti ár (Ft)<input class="input" name="old_price" type="number" min="0" inputmode="numeric"></label>
        <label class="field">Érvényes eddig<input class="input" name="valid_to" type="date"></label>
      </div>
      <label class="field">Kategória<select class="select" name="category">
        ${META.categories.map((c) => `<option value="${c.key}" ${c.key === "gyorsetterem" ? "selected" : ""}>${c.icon} ${c.label}</option>`).join("")}</select></label>
      <label class="field">Link (nem kötelező)<input class="input" name="url" type="url" placeholder="https://"></label>
      <div class="actions"><button class="btn primary" type="submit">Mentés</button></div>
    </form>`;
  if (!sheet.open) sheet.showModal();
  $("#sheet-x").onclick = () => sheet.close();
  $("#m-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    const body = { ...fd, price: fd.price ? Number(fd.price) : null, old_price: fd.old_price ? Number(fd.old_price) : null };
    for (const k of ["url", "valid_to"]) if (!body[k]) body[k] = null;
    try {
      await api("/api/manual", { method: "POST", body });
      sheet.close();
      toast("Hozzáadva ✔");
      await loadMeta();
      router();
    } catch (err) { toast(err.message); }
  };
}

// ------------------------------------------------------------------ Játékok
let countdownTimer;
async function renderGames(root) {
  root.innerHTML = `<div class="loading"><span class="spinner"></span></div>`;
  const data = await api("/api/games");
  const gameCard = (g, upcoming) => `
    <a class="game-card" href="${esc(g.url)}" target="_blank" rel="noopener">
      ${g.image ? `<img src="${esc(g.image)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">` : ""}
      <div class="body">
        <span class="store-pill"><i style="background:${STORE_COLORS()[g.store] || "#333"}"></i>${esc(g.store)}</span>
        <h3>${esc(g.title)}</h3>
        <div class="row small">
          ${g.old_price ? `<span class="old">${fmtPrice(g, "old_price")}</span>` : ""}
          <span class="tag good">${upcoming ? "Hamarosan ingyenes" : "INGYENES"}</span>
        </div>
        <div class="small">${upcoming
          ? `Ingyenes lesz: <b>${fmtDate(g.valid_from)}</b>`
          : g.valid_to ? `Lejár: <span class="countdown" data-until="${esc(g.valid_to)}">${countdown(g.valid_to)}</span> múlva` : ""}</div>
      </div>
    </a>`;
  root.innerHTML = `
    <section class="section">
      <div class="section-head"><h2>🎁 Most ingyenes</h2><span class="sub">Epic Games & Steam – tiéd marad, ha most begyűjtöd</span></div>
      ${data.free_now.length ? `<div class="game-hero">${data.free_now.map((g) => gameCard(g, false)).join("")}</div>` : emptyState("🎮", "Most nincs ingyenes játék.")}
    </section>
    ${data.upcoming.length ? `<section class="section">
      <div class="section-head"><h2>⏳ Hamarosan ingyenes</h2><span class="sub">Epic Games</span></div>
      <div class="game-hero">${data.upcoming.map((g) => gameCard(g, true)).join("")}</div></section>` : ""}
    <section class="section">
      <div class="section-head"><h2>🔥 Steam akciók</h2><span class="sub">a legjobban értékelt leárazott játékok</span></div>
      <div class="grid" id="steam-grid">${data.deals.map((g) => dealCard(g)).join("")}</div>
      ${data.deals.length ? `<div class="more"><a class="btn" href="#/" id="all-games">Összes játék akció</a></div>` : emptyState("🎮", "Még nincsenek Steam adatok.")}
    </section>`;
  bindCards($("#steam-grid"));
  const ag = $("#all-games");
  if (ag) ag.onclick = () => store.set("filters", { ...DEFAULT_FILTERS, category: "jatek" });
  clearInterval(countdownTimer);
  countdownTimer = setInterval(() => {
    const els = $$(".countdown");
    if (!els.length) return clearInterval(countdownTimer);
    els.forEach((el) => (el.textContent = countdown(el.dataset.until)));
  }, 30000);
}

// ------------------------------------------------------------------ Bevásárlólista
async function renderShopping(root) {
  const saved = store.get("shopping", "tej\nkenyér\ntojás\ncsirkemell\nbanán\nmosogatószer");
  root.innerHTML = `
    <div class="card-box" style="display:grid;gap:12px">
      <div><b>Mit vennél?</b> <span class="muted small">Soronként egy tétel. Megmutatjuk, hol a legolcsóbb (akciós és normál árak alapján, ${esc(META.stores.filter((s) => ["Spar","Aldi","Tesco","Penny","Auchan","Lidl","dm","Rossmann","Müller"].includes(s.name)).length)} lánc).</span></div>
      <textarea class="textarea" id="s-lines" rows="7">${esc(saved)}</textarea>
      <div class="row">
        <label class="toggle"><input type="checkbox" id="s-ai" ${META.ai_enabled ? "checked" : "disabled"}> AI pontosítás ${META.ai_enabled ? "" : '<span class="muted small">(Gemini kulcs kell)</span>'}</label>
        <span class="grow"></span>
        <button class="btn primary" id="s-go">Hol a legolcsóbb?</button>
      </div>
    </div>
    <div id="s-results" class="section"></div>`;
  const out = $("#s-results");
  bindCards(out);
  $("#s-lines").addEventListener("input", (e) => store.set("shopping", e.target.value));
  $("#s-go").onclick = async () => {
    const lines = $("#s-lines").value.split("\n").map((l) => l.trim()).filter(Boolean);
    if (!lines.length) return toast("Írj be legalább egy tételt");
    out.innerHTML = `<div class="loading"><span class="spinner"></span> Számolás…</div>`;
    try {
      const plan = await api("/api/shopping", { method: "POST", body: { lines, use_ai: $("#s-ai").checked } });
      const best = plan.stores[0];
      out.innerHTML = `
        ${plan.note ? `<div class="summary small">${esc(plan.note)}</div>` : ""}
        <div class="section-head"><h2>Boltok összesítve</h2><span class="sub">${plan.found}/${lines.length} tételt találtunk</span></div>
        <div class="store-rank">
          <div class="r"><span>🧺</span><span class="n">Vegyesen, mindent a legolcsóbb helyen</span><span class="tot">${fmtNum(plan.mixed_total)} Ft</span></div>
          ${plan.stores.slice(0, 9).map((s) => `
            <div class="r ${s === best && s.found === plan.found ? "best" : ""}">
              <span class="store-pill"><i style="background:${STORE_COLORS()[s.store] || "#999"}"></i></span>
              <span><span class="n">${esc(s.store)}</span><br><span class="small muted">${s.found}/${lines.length} tétel kapható</span></span>
              <span class="tot">${fmtNum(s.total)} Ft</span>
            </div>`).join("")}
        </div>
        <div class="section-head section"><h2>Tételenként</h2><span class="sub">${plan.ai_used ? "✨ AI-val pontosítva" : ""}</span></div>
        <div class="card-box list">
          ${plan.lines.map((l) => l.best ? `
            <div class="list-row deal-row" data-id="${esc(l.best.id)}" style="cursor:pointer">
              ${l.best.image ? `<img src="${esc(l.best.image)}" alt="" loading="lazy">` : ""}
              <div class="grow"><div class="s">${esc(l.line)}</div><div class="t">${esc(l.best.title)}</div>
                <div class="s">${esc(l.best.store)}${l.best.discount_pct ? ` · <span style="color:var(--accent-text)">-${Math.round(l.best.discount_pct)}%</span>` : ""}
                ${l.per_store.length > 1 ? ` · máshol: ${l.per_store.slice(1, 4).map((p) => `${esc(p.store)} ${fmtNum(p.price_huf)}`).join(", ")}` : ""}</div></div>
              <div class="p">${fmtNum(l.best.price_huf)} Ft</div>
            </div>` : `
            <div class="list-row"><div class="grow"><div class="s">${esc(l.line)}</div><div class="t muted">Nem találtuk – próbáld máshogy írni</div></div></div>`).join("")}
        </div>
        <div class="muted small" style="margin-top:10px">Az árak tájékoztató jellegűek (GVH Árfigyelő + Lidl), boltonként eltérhetnek.</div>`;
      $$(".deal-row", out).forEach((r) => (r.onclick = () => openDetail(r.dataset.id)));
    } catch (e) {
      out.innerHTML = emptyState("⚠️", esc(e.message));
    }
  };
}

// ------------------------------------------------------------------ Mentett
async function renderFavorites(root) {
  root.innerHTML = skeletonGrid(4);
  const data = await api("/api/favorites");
  root.innerHTML = data.items.length
    ? `<div class="muted small">A mentett akciók itt maradnak, akkor is, ha már lejártak – így látod, ha újra akciós lesz.</div><div class="grid">${data.items.map((i) => dealCard(i)).join("")}</div>`
    : emptyState("⭐", "Még nincs mentett akciód. A kártyákon a csillaggal menthetsz.");
  bindCards(root);
}

// ------------------------------------------------------------------ Figyelő
async function renderWatches(root) {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const data = await api("/api/watches");
  const aiOn = store.get("watch_ai", false) && META.ai_enabled;
  const catLabel = (k) => META.categories.find((c) => c.key === k)?.label;
  const planText = (p) => !p ? "" : [
    p.stores && p.stores.length ? p.stores.join(", ") : "",
    p.category ? catLabel(p.category) : "",
    p.max_price ? `max ${fmtNum(p.max_price)} Ft` : "",
    p.keywords && p.keywords.length ? `„${p.keywords.slice(0, 4).join(", ")}”` : "",
  ].filter(Boolean).join(" · ");
  root.innerHTML = `
    <form class="card-box" id="w-form" style="display:grid;gap:12px">
      <div><b>Új figyelő</b> <span class="muted small">Szólunk, ha új akció jelenik meg erre: itt az appban, és push értesítésben is, ha a <a href="#/profil">Profilban</a> beállítottad az ntfy-t.</span></div>
      <div>
        <label class="toggle"><input type="checkbox" id="w-ai" ${aiOn ? "checked" : ""} ${META.ai_enabled ? "" : "disabled"}> <b>✨ AI figyelő</b></label>
        <div class="muted small" style="margin-top:4px">${META.ai_enabled ? "Írd le szabadon, mit keresel (pl. „olcsó jó steames játék”), és az AI dönti el, melyik új akció illik hozzá." : "Az admin még nem állított be Gemini kulcsot."}</div>
      </div>
      <div class="form-grid">
        <label class="field" style="grid-column:1/-1"><span id="w-qlabel">${aiOn ? "Mit keresel? (szabad szöveg)" : "Kulcsszó"}</span>
          <input class="input" name="query" required minlength="2" maxlength="200" id="w-q"
            placeholder="${aiOn ? "pl. olcsó, jó értékelésű Steam játék" : "pl. Nutella, Parkside fúró, Pampers 4"}" value="${esc(params.get("q") || "")}"></label>
        <label class="field">Max. ár (Ft)<input class="input" name="max_price" type="number" min="0" inputmode="numeric"></label>
        <label class="field" id="w-mind" ${aiOn ? "hidden" : ""}>Min. kedvezmény (%)<input class="input" name="min_discount" type="number" min="0" max="99" inputmode="numeric"></label>
        <label class="field">Kategória<select class="select" name="category"><option value="">${aiOn ? "Az AI dönti el" : "Bármelyik"}</option>
          ${META.categories.map((c) => `<option value="${c.key}">${c.icon} ${c.label}</option>`).join("")}</select></label>
      </div>
      <div class="privacy-note small" id="w-ainote" ${aiOn ? "" : "hidden"}><span>🔒</span><span><b>Ne írj be személyes adatot.</b> A leírást a Google Gemini dolgozza fel. Az AI figyelő minden frissítéskor, ha van új jelölt, 1 AI-keresést használ a napi keretedből${META.ai_limit != null ? ` (ma: ${META.ai_today} / ${META.ai_limit})` : ""}.</span></div>
      <div class="row"><button class="btn primary" type="submit" id="w-submit">Figyelő hozzáadása</button></div>
    </form>
    <section class="section">
      <div class="section-head"><h2>Figyelőid</h2></div>
      ${data.watches.length ? `<div class="card-box list">${data.watches.map((w) => `
        <div class="list-row"><div class="grow"><div class="t">${w.use_ai ? "✨" : "🔔"} ${esc(w.query)} ${w.use_ai ? '<span class="tag hot">AI</span>' : ""}</div>
          <div class="s">${w.use_ai
            ? (planText(w.ai_plan) ? `AI értelmezése: ${esc(planText(w.ai_plan))}` : "AI figyelő")
            : [w.max_price ? `max ${fmtNum(w.max_price)} Ft` : "", w.min_discount ? `min -${w.min_discount}%` : "",
               w.category ? catLabel(w.category) : ""].filter(Boolean).join(" · ") || "bármilyen akció"}</div></div>
          <button class="btn small ghost" data-del="${w.id}">Törlés</button></div>`).join("")}</div>`
        : `<div class="muted">Még nincs figyelőd.</div>`}
    </section>
    <section class="section">
      <div class="section-head"><h2>Találatok</h2><span class="sub">${data.alerts.filter((a) => !a.seen).length} új</span></div>
      ${data.alerts.length ? `<div class="grid" id="w-alerts">${data.alerts.map((a) =>
        dealCard({ ...a, badge: (a.seen ? "" : "ÚJ · ") + (a.watch_ai ? "✨ " : "🔔 ") + a.watch_query }, { reason: a.reason })).join("")}</div>`
        : `<div class="muted">Amint valami megfelel a figyelőidnek, itt jelenik meg.</div>`}
    </section>`;
  const alertsEl = $("#w-alerts");
  if (alertsEl) bindCards(alertsEl);
  $("#w-ai").onchange = (e) => {
    store.set("watch_ai", e.target.checked);
    const typed = $("#w-q").value.trim();  // a beírt szöveg ne vesszen el váltáskor
    history.replaceState(null, "", typed ? `#/figyelo?q=${encodeURIComponent(typed)}` : "#/figyelo");
    renderWatches(root);
  };
  $("#w-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    const useAi = $("#w-ai").checked;
    const body = {
      query: fd.query.trim(), category: fd.category, use_ai: useAi,
      max_price: fd.max_price ? Number(fd.max_price) : null,
      min_discount: fd.min_discount ? Number(fd.min_discount) : null,
    };
    const btn = $("#w-submit");
    btn.disabled = true;
    if (useAi) btn.innerHTML = '<span class="spinner"></span> Az AI értelmezi és átnézi a mostani akciókat…';
    try {
      const r = await api("/api/watches", { method: "POST", body });
      toast(r.matches_now ? `Figyelő kész – már most ${r.matches_now} találat!` : "Figyelő kész ✔ Szólunk, ha lesz találat.");
      history.replaceState(null, "", "#/figyelo");
      await loadMeta();
      renderWatches(root);
    } catch (err) {
      toast(err.message);
      btn.disabled = false;
      btn.textContent = "Figyelő hozzáadása";
    }
  };
  $$("[data-del]", root).forEach((b) => (b.onclick = async () => {
    await api(`/api/watches/${b.dataset.del}`, { method: "DELETE" });
    renderWatches(root);
  }));
  if (data.alerts.some((a) => !a.seen)) {
    await api("/api/alerts/seen", { method: "POST" });
    $("#alert-dot").hidden = true;
  }
}

// ------------------------------------------------------------------ Beállítások
async function renderSettings(root) {
  const [s, src] = await Promise.all([api("/api/settings"), api("/api/sources")]);
  const disabled = new Set((s.disabled_sources || "").split(",").filter(Boolean));
  root.innerHTML = `
    <section class="card-box" style="display:grid;gap:12px">
      <div><b>✨ Gemini AI</b><div class="muted small">Ingyenes kulcs: <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">aistudio.google.com/apikey</a> → „Create API key”. A kulcs csak a Pi-n tárolódik.</div></div>
      <div class="form-grid">
        <label class="field" style="grid-column:1/-1">API kulcs<input class="input" id="s-key" type="password" autocomplete="off" placeholder="AIza…" value="${esc(s.gemini_api_key)}"></label>
        <label class="field">Modell<input class="input" id="s-model" value="${esc(s.gemini_model)}" placeholder="gemini-flash-latest"></label>
      </div>
      <div class="row"><button class="btn primary" id="s-save-ai">Mentés</button><button class="btn" id="s-test-ai">Kapcsolat tesztelése</button><button class="btn" id="s-models">Elérhető modellek</button></div>
      <div class="small" id="s-ai-msg"></div>
      <div class="chips wrap" id="s-model-list"></div>
    </section>

    <section class="card-box section" style="display:grid;gap:12px">
      <div><b>👥 Felhasználók</b><div class="muted small">Te vagy az admin (az első felhasználó). A többiek a saját mentéseiket és figyelőiket látják, a beállításokat nem.</div></div>
      <label class="toggle"><input type="checkbox" id="s-reg" ${s.allow_registration === "1" ? "checked" : ""}> Új felhasználók regisztrálhatnak (sima, nem admin fiókkal)</label>
      <div class="form-grid">
        <label class="field">AI keresés / fő / nap (0 = korlátlan)<input class="input" id="s-ailimit" type="number" min="0" value="${esc(s.ai_daily_limit)}"></label>
        <label class="field">Max. regisztráció (adminon kívül, 0 = korlátlan)<input class="input" id="s-maxusers" type="number" min="0" value="${esc(s.max_registrations)}"></label>
      </div>
      <div class="muted small">A napi AI-keret rád (adminra) nem vonatkozik; azért van, hogy a regisztrált felhasználók ne merítsék ki az ingyenes Gemini kulcsodat. Lent felhasználónként egyedi keretet is adhatsz (0 = nem használhat AI-t). A keresések tartalmát nem tároljuk, csak a darabszámot.</div>
      <div class="row"><button class="btn primary small" id="s-save-users">Korlátok mentése</button></div>
      <div class="list" id="s-users"><div class="muted small">Betöltés…</div></div>
    </section>

    <section class="card-box section" style="display:grid;gap:12px">
      <div><b>🔔 ntfy szerver</b><div class="muted small">Ezen keresztül mennek a push értesítések. A témát (topic) mindenki a saját Profiljában állítja be.</div></div>
      <label class="field">Szerver<input class="input" id="s-ntfy" value="${esc(s.ntfy_server)}"></label>
      <div class="row"><button class="btn primary" id="s-save-ntfy">Mentés</button></div>
    </section>

    <section class="card-box section" style="display:grid;gap:12px">
      <div><b>⏱ Frissítés</b></div>
      <div class="form-grid">
        <label class="field">Frissítés óránként<input class="input" id="s-hours" type="number" min="1" max="48" value="${esc(s.refresh_hours)}"></label>
        <label class="field">EUR → HUF árfolyam (Steam)<input class="input" id="s-eur" type="number" step="0.1" value="${esc(s.eur_huf)}"></label>
      </div>
      <div class="row"><button class="btn primary" id="s-save-gen">Mentés</button></div>
    </section>

    <section class="section">
      <div class="section-head"><h2>Források</h2><button class="btn small" id="s-refresh-all">↻ Összes frissítése most</button></div>
      <div class="card-box list">
        ${src.sources.map((x) => `
          <div class="list-row" style="align-items:flex-start">
            <span class="status-dot ${x.ok == null ? "none" : x.ok ? "ok" : "err"}" style="margin-top:7px"></span>
            <div class="grow">
              <div class="t">${esc(x.label)} ${x.experimental ? '<span class="tag warn">kísérleti</span>' : ""}</div>
              <div class="s">${esc(x.description)}</div>
              <div class="s">${x.last_run ? `Utoljára: ${relTime(x.last_run)} · ${fmtNum(x.count || 0)} tétel · ${x.duration ?? "?"} mp` : "Még nem futott"}</div>
              ${x.error ? `<div class="s" style="color:var(--bad)">${esc(x.error)}</div>` : ""}
            </div>
            <div class="row" style="flex-wrap:nowrap">
              <button class="btn small ghost" data-run="${x.name}" title="Frissítés most">↻</button>
              <label class="toggle"><input type="checkbox" data-src="${x.name}" ${disabled.has(x.name) ? "" : "checked"}></label>
            </div>
          </div>`).join("")}
      </div>
      <details class="card-box section">
        <summary><b>eMAG figyelt oldalak</b> <span class="muted small">(soronként egy URL; üresen az alapértelmezettek)</span></summary>
        <textarea class="textarea" id="s-emag" style="margin-top:10px" placeholder="https://www.emag.hu/laptopok/sort-discountdesc/c">${esc(s.emag_urls)}</textarea>
        <div class="row" style="margin-top:10px"><button class="btn primary small" id="s-save-emag">Mentés</button></div>
      </details>
    </section>

    <section class="section muted small" style="line-height:1.6">
      Az app privát használatra készült: nyilvánosan elérhető árakat olvas, kíméletes gyakorisággal. A captcha-val védett oldalakat (pl. eMAG) nem kerüli meg.
      Az árak tájékoztató jellegűek – vásárlás előtt mindig ellenőrizd a bolt oldalán.
    </section>`;

  const saveSettings = async (values, msg = "Mentve ✔") => {
    try { await api("/api/settings", { method: "PUT", body: values }); toast(msg); await loadMeta(); }
    catch (e) { toast(e.message); }
  };
  $("#s-save-ai").onclick = () => saveSettings({ gemini_api_key: $("#s-key").value.trim(), gemini_model: $("#s-model").value.trim() });
  $("#s-test-ai").onclick = async () => {
    await saveSettings({ gemini_api_key: $("#s-key").value.trim(), gemini_model: $("#s-model").value.trim() }, "Mentve, tesztelés…");
    $("#s-ai-msg").innerHTML = '<span class="spinner"></span> Tesztelés… (túlterhelésnél több modellt is kipróbál)';
    const r = await api("/api/ai/test", { method: "POST" });
    $("#s-ai-msg").innerHTML = `<span style="color:${r.ok ? "var(--good)" : "var(--bad)"}">${esc(r.message)}</span>`;
    if (r.ok && r.current_model) $("#s-model").value = r.current_model;
  };
  $("#s-models").onclick = async () => {
    const keyVal = $("#s-key").value.trim();
    if (keyVal && !keyVal.startsWith("•")) await saveSettings({ gemini_api_key: keyVal }, "Kulcs mentve");
    const list = $("#s-model-list");
    list.innerHTML = '<span class="small muted"><span class="spinner"></span> Modellek lekérése…</span>';
    try {
      const r = await api("/api/ai/models?refresh=true");
      if (!r.models.length) {
        list.innerHTML = '<span class="small muted">Nincs használható modell ehhez a kulcshoz.</span>';
        return;
      }
      list.innerHTML = '<div class="small muted" style="width:100%">Kattints egy modellre (a ⭐ a javasolt):</div>' +
        r.models.slice(0, 16).map((m, i) =>
          `<button class="chip ${m === $("#s-model").value ? "on" : ""}" data-model="${esc(m)}">${i === 0 ? "⭐ " : ""}${esc(m)}</button>`).join("");
      $$("[data-model]").forEach((b) => (b.onclick = async () => {
        $("#s-model").value = b.dataset.model;
        $$("[data-model]").forEach((x) => x.classList.toggle("on", x === b));
        await saveSettings({ gemini_model: b.dataset.model }, `Modell: ${b.dataset.model}`);
      }));
    } catch (e) {
      list.innerHTML = `<span class="small" style="color:var(--bad)">${esc(e.message)}</span>`;
    }
  };
  $("#s-save-ntfy").onclick = () => saveSettings({ ntfy_server: $("#s-ntfy").value.trim() || "https://ntfy.sh" });
  $("#s-reg").onchange = (e) => saveSettings({ allow_registration: e.target.checked ? "1" : "0" },
    e.target.checked ? "Regisztráció engedélyezve" : "Regisztráció letiltva");
  $("#s-save-users").onclick = async () => {
    await saveSettings({ ai_daily_limit: $("#s-ailimit").value, max_registrations: $("#s-maxusers").value });
    loadUsers();
  };
  const loadUsers = async () => {
    const data = await api("/api/admin/users");
    $("#s-users").innerHTML = `
      <div class="small muted" style="padding:4px 0 8px">Regisztrált fiókok: <b>${data.registered}</b> / ${Number(data.max_registrations) ? data.max_registrations : "korlátlan"} ·
        Közös napi AI-keret: <b>${Number(data.ai_daily_limit) ? data.ai_daily_limit : "korlátlan"}</b></div>` +
      data.users.map((u) => {
        const max = Math.max(1, ...u.ai_week.map((d) => d.count));
        const bars = u.ai_week.map((d) => `<span class="bar" title="${fmtDate(d.day)}: ${d.count} AI keresés" style="height:${Math.max(2, Math.round((d.count / max) * 26))}px"></span>`).join("");
        const lim = u.ai_effective_limit;
        return `
        <div class="user-row">
          <div class="row">
            <div class="grow"><div class="t">${esc(u.username)} ${u.is_admin ? '<span class="tag hot">admin</span>' : ""}</div>
              <div class="s">Regisztrált: ${fmtDate(u.created)} · Utoljára aktív: ${u.last_seen ? relTime(u.last_seen) : "–"} · ⭐ ${u.favorites} · 🔔 ${u.watches}</div></div>
            ${u.is_admin ? "" : `<button class="btn small ghost" data-deluser="${u.id}" data-name="${esc(u.username)}">🗑 Törlés</button>`}
          </div>
          <div class="row" style="margin-top:8px;align-items:flex-end">
            <div>
              <div class="s">Ma: <b>${u.ai_today}</b>${lim == null ? "" : ` / ${lim}`} AI keresés</div>
              <div class="bars" aria-label="AI keresések az elmúlt 7 napban">${bars}</div>
              <div class="s">elmúlt 7 nap: ${u.ai_week.reduce((a, d) => a + d.count, 0)}</div>
            </div>
            <span class="grow"></span>
            ${u.is_admin ? `<span class="s">Az adminnak nincs AI-korlátja</span>` : `
            <label class="field" style="width:150px">Egyedi napi AI-keret
              <input class="input" type="number" min="0" placeholder="közös (${Number(data.ai_daily_limit) || "∞"})" value="${u.ai_limit ?? ""}" data-limit="${u.id}"></label>
            <button class="btn small" data-savelimit="${u.id}">Mentés</button>`}
          </div>
        </div>`;
      }).join("");
    $$("[data-deluser]").forEach((b) => (b.onclick = async () => {
      if (!confirm(`Biztosan törlöd „${b.dataset.name}” fiókját? A mentései és figyelői is törlődnek.`)) return;
      await api(`/api/admin/users/${b.dataset.deluser}`, { method: "DELETE" });
      toast("Felhasználó törölve");
      loadUsers();
    }));
    $$("[data-savelimit]").forEach((b) => (b.onclick = async () => {
      const v = $(`[data-limit="${b.dataset.savelimit}"]`).value.trim();
      try {
        await api(`/api/admin/users/${b.dataset.savelimit}`, { method: "PUT", body: { ai_limit: v === "" ? null : Number(v) } });
        toast(v === "" ? "Közös keretre állítva" : Number(v) === 0 ? "AI letiltva ennél a felhasználónál" : `Napi keret: ${v}`);
        loadUsers();
      } catch (e) { toast(e.message); }
    }));
  };
  loadUsers();
  $("#s-save-gen").onclick = () => saveSettings({ refresh_hours: $("#s-hours").value, eur_huf: $("#s-eur").value });
  $("#s-save-emag").onclick = () => saveSettings({ emag_urls: $("#s-emag").value });
  $$("[data-src]").forEach((cb) => (cb.onchange = () => {
    const off = $$("[data-src]").filter((c) => !c.checked).map((c) => c.dataset.src);
    saveSettings({ disabled_sources: off.join(",") }, cb.checked ? "Forrás bekapcsolva" : "Forrás kikapcsolva");
  }));
  const startRefresh = async (source = "") => {
    const r = await api(`/api/refresh${source ? `?source=${source}` : ""}`, { method: "POST" });
    toast(r.started ? "Frissítés elindult – pár perc" : r.message);
    loadMeta();
  };
  $("#s-refresh-all").onclick = () => startRefresh();
  $$("[data-run]").forEach((b) => (b.onclick = () => startRefresh(b.dataset.run)));
}

// ------------------------------------------------------------------ Profil
async function renderProfile(root) {
  const u = META.user;
  root.innerHTML = `
    <section class="card-box row">
      <div class="grow"><div style="font-size:18px;font-weight:700">${esc(u.username)} ${u.is_admin ? '<span class="tag hot">admin</span>' : ""}</div>
        <div class="muted small">Tag ${fmtDate(u.created)} óta</div></div>
      <button class="btn" id="p-logout">Kijelentkezés</button>
    </section>
    ${u.is_admin ? `<a class="card-box section row" href="#/beallitasok" style="text-decoration:none">
      <span style="font-size:22px">⚙️</span><div class="grow"><b>Admin beállítások</b><div class="muted small">Gemini API kulcs, források, frissítés, felhasználók</div></div><span>→</span></a>` : ""}
    <section class="card-box section" style="display:grid;gap:12px">
      <div><b>🔔 Push értesítés a telefonodra (ntfy)</b><div class="muted small">1. Telepítsd az ingyenes <a href="https://ntfy.sh" target="_blank" rel="noopener">ntfy</a> appot. 2. Iratkozz fel egy egyedi, nehezen kitalálható témára (pl. <code>akciok-${Math.random().toString(36).slice(2, 8)}</code>). 3. Írd be ide ugyanazt. Így szól a telefonod, ha egy figyelődre új akció jön.</div></div>
      <label class="field">Téma (topic)<input class="input" id="p-topic" value="${esc(u.ntfy_topic)}" placeholder="akciok-valami-titkos" autocomplete="off"></label>
      <div class="row"><button class="btn primary" id="p-save-topic">Mentés</button><button class="btn" id="p-test">Teszt értesítés</button></div>
    </section>
    <section class="card-box section" style="display:grid;gap:12px">
      <div><b>📳 Rázós meglepetés</b><div class="muted small">Rázd meg a telefont (vagy nyomd meg fent a 🎲-t), és egy üveg darabjaira törve előugrik egy véletlen jó akció vagy kupon.</div></div>
      <label class="toggle"><input type="checkbox" id="p-shake" ${store.get("shake_on", true) ? "checked" : ""}> Rázásra induljon</label>
      <label class="toggle"><input type="checkbox" id="p-shake-sound" ${store.get("shake_sound", true) ? "checked" : ""}> Üvegcsörömpölés hang</label>
      ${Surprise.needsPermission() ? `<div class="row"><button class="btn small" id="p-shake-perm">Mozgásérzékelő engedélyezése (iPhone)</button></div>` : ""}
      <div class="row"><button class="btn small" id="p-shake-try">🎲 Kipróbálom</button></div>
    </section>
    <form class="card-box section" style="display:grid;gap:12px" id="p-pw">
      <b>🔑 Jelszó módosítása</b>
      <div class="form-grid">
        <label class="field">Jelenlegi jelszó<input class="input" type="password" name="current_password" autocomplete="current-password" required></label>
        <label class="field">Új jelszó (min. 6 karakter)<input class="input" type="password" name="new_password" autocomplete="new-password" minlength="6" required></label>
      </div>
      <div class="row"><button class="btn primary" type="submit">Jelszó módosítása</button></div>
    </form>`;
  const saveTopic = async () => {
    const r = await api("/api/me", { method: "PUT", body: { ntfy_topic: $("#p-topic").value.trim() } });
    META.user = r.user;
  };
  $("#p-save-topic").onclick = async () => { try { await saveTopic(); toast("Mentve ✔"); } catch (e) { toast(e.message); } };
  $("#p-test").onclick = async () => {
    try {
      await saveTopic();
      const r = await api("/api/me/notify-test", { method: "POST" });
      toast(r.ok ? "Teszt értesítés elküldve 📱" : "Nem sikerült – adj meg egy témát");
    } catch (e) { toast(e.message); }
  };
  $("#p-shake").onchange = (e) => { store.set("shake_on", e.target.checked); toast(e.target.checked ? "Rázás bekapcsolva 📳" : "Rázás kikapcsolva"); };
  $("#p-shake-sound").onchange = (e) => store.set("shake_sound", e.target.checked);
  $("#p-shake-try").onclick = () => $("#surprise-btn").click();
  const permBtn = $("#p-shake-perm");
  if (permBtn) permBtn.onclick = async () => toast((await Surprise.requestPermission()) ? "Engedélyezve – rázd meg! 📳" : "Nem kaptunk engedélyt a mozgásérzékelőhöz");
  $("#p-pw").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/me", { method: "PUT", body: Object.fromEntries(new FormData(e.target)) });
      e.target.reset();
      toast("Jelszó módosítva ✔");
    } catch (err) { toast(err.message); }
  };
  $("#p-logout").onclick = async () => {
    await api("/api/auth/logout", { method: "POST" });
    META.user = null;
    showAuth();
  };
}

// ------------------------------------------------------------------ bejelentkezés / regisztráció
async function showAuth() {
  if (document.body.classList.contains("auth-mode") && $("#auth-form")) return;
  document.body.classList.add("auth-mode");
  if (sheet.open) sheet.close();
  let state = { needs_setup: false, allow_registration: true };
  try { state = await api("/api/auth/state"); } catch { /* szerver nem elérhető */ }
  let mode = state.needs_setup ? "setup" : "login";
  const render = () => {
    const setup = mode === "setup", reg = mode === "register";
    view.innerHTML = `
      <div class="auth-wrap">
        <form class="card-box auth-card" id="auth-form">
          <img src="/icon.svg" alt="" width="52" height="52">
          <h2>${setup ? "Üdv az Akciók appban! 👋" : reg ? "Regisztráció" : "Bejelentkezés"}</h2>
          <div class="muted small">${setup
            ? "Hozd létre az első fiókot. <b>Ez lesz az admin fiók</b>: csak ez éri el a beállításokat (Gemini API kulcs, források, felhasználók)."
            : reg ? "Hozz létre egy fiókot. A mentéseid és figyelőid a sajátjaid lesznek." : "Lépj be a fiókodba."}</div>
          <label class="field">Felhasználónév<input class="input" name="username" autocomplete="username" required minlength="2" maxlength="40" autofocus></label>
          <label class="field">Jelszó${setup || reg ? " (min. 6 karakter)" : ""}<input class="input" type="password" name="password" autocomplete="${setup || reg ? "new-password" : "current-password"}" required minlength="6"></label>
          <button class="btn primary" type="submit">${setup ? "Admin fiók létrehozása" : reg ? "Regisztráció" : "Belépés"}</button>
          <div class="small auth-err" id="auth-err"></div>
          ${!setup && state.allow_registration ? `<button class="btn ghost small" type="button" id="auth-switch">${reg ? "Van már fiókom – belépés" : "Nincs még fiókod? Regisztráció"}</button>` : ""}
        </form>
      </div>`;
    const sw = $("#auth-switch");
    if (sw) sw.onclick = () => { mode = reg ? "login" : "register"; render(); };
    $("#auth-form").onsubmit = async (e) => {
      e.preventDefault();
      const body = Object.fromEntries(new FormData(e.target));
      const btn = $("button[type=submit]", e.target);
      btn.disabled = true;
      try {
        await api(mode === "login" ? "/api/auth/login" : "/api/auth/register", { method: "POST", body });
        document.body.classList.remove("auth-mode");
        await start();
      } catch (err) {
        $("#auth-err").textContent = err.message;
        btn.disabled = false;
      }
    };
  };
  render();
}

// ------------------------------------------------------------------ Rázós meglepetés 📳
// Rázásra (vagy a 🎲 gombra) egy üvegpanel repedezik meg és törik szilánkokra,
// mögüle egy véletlen jó akció / kupon ugrik elő.
const Surprise = (() => {
  let busy = false;
  let lastShake = 0;
  let peaks = [];
  let audio = null;
  const recent = [];
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const enabled = () => store.get("shake_on", true);
  const rand = (a, b) => a + Math.random() * (b - a);

  // --- hang: rövid üvegcsörömpölés WebAudio-val (fájl nélkül)
  function ensureAudio() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume();
    } catch { audio = null; }
  }
  function glassSound(big) {
    if (!audio || audio.state !== "running" || !store.get("shake_sound", true)) return;
    const t0 = audio.currentTime;
    const len = big ? 0.9 : 0.25;
    const buf = audio.createBuffer(1, Math.floor(audio.sampleRate * len), audio.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / d.length, big ? 3 : 6);
    const noise = audio.createBufferSource();
    noise.buffer = buf;
    const hp = audio.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = big ? 2500 : 4000;
    const gain = audio.createGain();
    gain.gain.value = big ? 0.35 : 0.25;
    noise.connect(hp).connect(gain).connect(audio.destination);
    noise.start(t0);
    if (big) { // csilingelő szilánkok
      for (let i = 0; i < 9; i++) {
        const o = audio.createOscillator();
        const g = audio.createGain();
        const t = t0 + rand(0.02, 0.45);
        o.type = "sine";
        o.frequency.value = rand(2600, 6200);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(rand(0.03, 0.08), t + 0.005);
        g.gain.exponentialRampToValueAtTime(0.0001, t + rand(0.15, 0.4));
        o.connect(g).connect(audio.destination);
        o.start(t);
        o.stop(t + 0.5);
      }
    }
  }
  const buzz = (p) => { try { navigator.vibrate && navigator.vibrate(p); } catch { /* nem támogatott */ } };

  // --- rázás felismerése
  function onMotion(e) {
    if (!enabled() || busy || document.body.classList.contains("auth-mode")) return;
    const a = e.accelerationIncludingGravity || e.acceleration;
    if (!a || a.x == null) return;
    const g = Math.sqrt(a.x * a.x + a.y * a.y + a.z * a.z);
    const jolt = e.accelerationIncludingGravity ? Math.abs(g - 9.81) : g;
    const now = Date.now();
    if (jolt > 13) {
      peaks = peaks.filter((t) => now - t < 900);
      peaks.push(now);
      if (peaks.length >= 3 && now - lastShake > 2500) {
        lastShake = now;
        peaks = [];
        show();
      }
    }
  }
  function needsPermission() {
    return typeof DeviceMotionEvent !== "undefined" && typeof DeviceMotionEvent.requestPermission === "function";
  }
  async function requestPermission() {
    // iPhone: csak felhasználói érintésre kérhető engedély
    if (!needsPermission()) return true;
    try {
      const r = await DeviceMotionEvent.requestPermission();
      store.set("shake_perm", r);
      return r === "granted";
    } catch { return false; }
  }
  function init() {
    window.addEventListener("devicemotion", onMotion);
    // az első érintés feloldja a hangot (böngésző-szabály)
    window.addEventListener("pointerdown", ensureAudio, { once: true });
    const btn = $("#surprise-btn");
    if (btn) btn.onclick = async () => {
      ensureAudio();
      if (needsPermission() && store.get("shake_perm", "") !== "granted") await requestPermission();
      show();
    };
    // egyszeri tipp telefonon
    if ((IS_ANDROID || IS_IOS) && !store.get("shake_tip", false)) {
      setTimeout(() => {
        if (document.body.classList.contains("auth-mode")) return;
        toast(IS_IOS ? "Tipp: nyomd meg a 🎲-t, utána elég megrázni a telefont! 📳" : "Tipp: rázd meg a telefont egy meglepetés akcióért! 📳");
        store.set("shake_tip", true);
      }, 4000);
    }
  }

  // --- törésminta: sugarak + gyűrűk -> négyszög szilánkok
  function buildShards(cx, cy, w, h) {
    const diag = Math.hypot(Math.max(cx, w - cx), Math.max(cy, h - cy));
    const rays = Math.round(rand(13, 17));
    const angles = Array.from({ length: rays }, (_, i) => ((i + rand(-0.35, 0.35)) / rays) * Math.PI * 2);
    const rings = [0, 0.07, 0.17, 0.32, 0.55, 1.15].map((r) => r * diag);
    const pt = (i, j) => {
      const ang = angles[i % rays] + (j ? rand(-0.06, 0.06) : 0);
      const r = j === 0 ? 0 : rings[j] * rand(0.85, 1.15);
      return [cx + Math.cos(ang) * r, cy + Math.sin(ang) * r];
    };
    const grid = angles.map((_, i) => rings.map((_, j) => pt(i, j)));
    const shards = [];
    for (let i = 0; i < rays; i++) {
      for (let j = 0; j < rings.length - 1; j++) {
        const a = grid[i][j], b = grid[(i + 1) % rays][j], c = grid[(i + 1) % rays][j + 1], d = grid[i][j + 1];
        const poly = j === 0 ? [a, c, d] : [a, b, c, d];
        const mx = poly.reduce((s, p) => s + p[0], 0) / poly.length;
        const my = poly.reduce((s, p) => s + p[1], 0) / poly.length;
        shards.push({ poly, mx, my, ring: j });
      }
    }
    const cracks = angles.map((ang) => {
      let x = cx, y = cy, path = `M${cx},${cy}`;
      const steps = 7;
      for (let s = 1; s <= steps; s++) {
        const r = (diag * 1.1 * s) / steps;
        const a2 = ang + rand(-0.05, 0.05);
        x = cx + Math.cos(a2) * r;
        y = cy + Math.sin(a2) * r;
        path += ` L${x.toFixed(1)},${y.toFixed(1)}`;
      }
      return path;
    });
    // gyűrű-repedések a belső részen
    for (let j = 1; j <= 3; j++) {
      for (let i = 0; i < rays; i++) {
        if (Math.random() < 0.55) {
          const a = grid[i][j], b = grid[(i + 1) % rays][j];
          cracks.push(`M${a[0].toFixed(1)},${a[1].toFixed(1)} L${b[0].toFixed(1)},${b[1].toFixed(1)}`);
        }
      }
    }
    return { shards, cracks };
  }

  const faceHtml = `
    <div class="sp-face">
      <div class="sp-face-inner">
        <div class="sp-gift">🎁</div>
        <div class="sp-face-title">Meglepetés akció</div>
        <div class="sp-face-sub">Valami jó vár rád…</div>
      </div>
    </div>`;

  function revealHtml(item) {
    const app = item.extra && item.extra.app && item.extra.app.link ? item.extra.app : null;
    const color = STORE_COLORS()[item.store] || "var(--accent)";
    const kindLabel = item.kind === "coupon" ? "🍔 Kupon" : item.kind === "free_game" ? "🎮 Ingyen játék" : item.category === "jatek" ? "🎮 Játék akció" : "🔥 Akció";
    return `
      <div class="sp-wrap">
      <div class="sp-glow"></div>
      <div class="sp-card" role="dialog" aria-label="Meglepetés ajánlat">
        <div class="sp-kind">${kindLabel}</div>
        <div class="sp-img">${item.image ? `<img src="${esc(item.image)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}
          ${discBadge(item)}</div>
        <div class="sp-body">
          <span class="store-pill"><i style="background:${color}"></i>${esc(item.store)}</span>
          <div class="sp-title">${esc(item.title)}</div>
          ${item.badge ? `<div class="meta"><span class="tag">${esc(item.badge)}</span>${item.valid_to ? `<span class="tag hot">${untilText(item.valid_to)}</span>` : ""}</div>` : ""}
          <div class="price-row">
            ${item.price != null ? `<span class="price">${item.price === 0 ? "INGYEN" : fmtPrice(item)}</span>` : `<span class="muted small">ár az appban</span>`}
            ${item.old_price ? `<span class="old">${fmtPrice(item, "old_price")}</span>` : ""}
          </div>
          ${hufHint(item) ? `<div class="muted small">${hufHint(item)}</div>` : ""}
          <div class="sp-actions">
            <button class="btn primary" id="sp-open">${app ? `📱 Megnyitás a ${esc(app.name)} appban` : "Megnézem"}</button>
            <button class="btn" id="sp-again">🎲 Még egyet</button>
          </div>
          <button class="sp-close" id="sp-close" aria-label="Bezárás">${ICONS.close}</button>
        </div>
      </div>
      </div>`;
  }

  function sparkles(layer, cx, cy) {
    const colors = ["#ffd166", "#ff6a4d", "#ffffff", "#7bdff2", "#f7a6ff"];
    for (let i = 0; i < 26; i++) {
      const s = document.createElement("i");
      s.className = "sp-spark";
      s.style.left = `${cx}px`;
      s.style.top = `${cy}px`;
      s.style.background = colors[i % colors.length];
      layer.appendChild(s);
      const ang = rand(0, Math.PI * 2), dist = rand(90, 260);
      s.animate([
        { transform: "translate(-50%,-50%) scale(1)", opacity: 1 },
        { transform: `translate(calc(-50% + ${Math.cos(ang) * dist}px), calc(-50% + ${Math.sin(ang) * dist}px)) scale(0)`, opacity: 0 },
      ], { duration: rand(600, 1100), easing: "cubic-bezier(.15,.7,.3,1)", fill: "forwards" });
    }
  }

  async function show() {
    if (busy) return;
    busy = true;
    if (sheet.open) sheet.close();
    const itemPromise = api(`/api/surprise?exclude=${encodeURIComponent(recent.join(","))}`).catch((e) => ({ error: e.message }));
    const w = innerWidth, h = innerHeight;
    const cx = w * rand(0.4, 0.6), cy = h * rand(0.38, 0.5);
    const layer = document.createElement("div");
    layer.className = "sp-layer";
    document.body.appendChild(layer);
    const close = () => {
      layer.classList.add("sp-out");
      setTimeout(() => layer.remove(), 250);
      busy = false;
    };

    if (!reduceMotion) {
      // 1) üvegpanel beúszik
      const panel = document.createElement("div");
      panel.className = "sp-panel";
      panel.innerHTML = faceHtml;
      layer.appendChild(panel);
      panel.animate([{ opacity: 0, transform: "scale(1.04)" }, { opacity: 1, transform: "scale(1)" }], { duration: 220, easing: "ease-out" });
      await new Promise((r) => setTimeout(r, 380));

      // 2) becsapódás: repedések
      const { shards, cracks } = buildShards(cx, cy, w, h);
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "sp-cracks");
      svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
      svg.innerHTML = cracks.map((d) => `<path d="${d}" pathLength="1"/>`).join("") +
        `<circle cx="${cx}" cy="${cy}" r="14" class="sp-impact"/>`;
      layer.appendChild(svg);
      buzz([25, 30, 40]);
      glassSound(false);
      $$("path", svg).forEach((p, i) => p.animate(
        [{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }],
        { duration: rand(220, 420), delay: i < 18 ? 0 : 120, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" }));
      layer.animate([{ transform: "translate(0,0)" }, { transform: "translate(-6px,3px)" }, { transform: "translate(5px,-4px)" },
        { transform: "translate(-3px,2px)" }, { transform: "translate(0,0)" }], { duration: 260 });
      await new Promise((r) => setTimeout(r, 520));

      // 3) szétrobban
      const flash = document.createElement("div");
      flash.className = "sp-flash";
      flash.style.setProperty("--x", `${cx}px`);
      flash.style.setProperty("--y", `${cy}px`);
      layer.appendChild(flash);
      flash.animate([{ opacity: 0.9 }, { opacity: 0 }], { duration: 450, fill: "forwards" });
      panel.remove();
      svg.remove();
      buzz([60, 40, 120]);
      glassSound(true);
      for (const s of shards) {
        const el = document.createElement("div");
        el.className = "sp-shard";
        el.innerHTML = faceHtml;
        el.style.clipPath = `polygon(${s.poly.map((p) => `${p[0].toFixed(1)}px ${p[1].toFixed(1)}px`).join(",")})`;
        el.style.transformOrigin = `${s.mx}px ${s.my}px`;
        layer.appendChild(el);
        const dx = s.mx - cx, dy = s.my - cy;
        const len = Math.hypot(dx, dy) || 1;
        const force = (5 - s.ring) * rand(60, 120) + rand(40, 120);
        const vx = (dx / len) * force, vy = (dy / len) * force;
        const rot = rand(-260, 260);
        const ax = rand(0, 1).toFixed(2), ay = rand(0, 1).toFixed(2);
        el.animate([
          { transform: "translate(0,0) rotate3d(0,0,1,0deg)", opacity: 1 },
          { transform: `translate(${vx * 0.45}px, ${vy * 0.45 - 30}px) rotate3d(${ax},${ay},1,${rot * 0.4}deg)`, opacity: 1, offset: 0.35 },
          { transform: `translate(${vx}px, ${vy + h * 0.85}px) rotate3d(${ax},${ay},1,${rot}deg)`, opacity: 0 },
        ], { duration: rand(900, 1400), delay: s.ring * 25, easing: "cubic-bezier(.25,.6,.45,1)", fill: "forwards" })
          .finished.then(() => el.remove()).catch(() => {});
      }
      await new Promise((r) => setTimeout(r, 450)); // hadd látszódjon a szétrepülés
    } else {
      await new Promise((r) => setTimeout(r, 150));
    }

    // 4) kiderül, mi volt mögötte
    const data = await itemPromise;
    if (data.error || !data.item) {
      toast(data.error || "Most nincs meglepetés. Próbáld később!");
      close();
      return;
    }
    const item = data.item;
    recent.push(item.id);
    if (recent.length > 15) recent.shift();
    const wrap = document.createElement("div");
    wrap.className = "sp-reveal";
    wrap.innerHTML = revealHtml(item);
    layer.appendChild(wrap);
    layer.classList.add("sp-dim");
    const card = $(".sp-wrap", wrap);
    card.animate([
      { transform: "scale(.3) rotate(-8deg)", opacity: 0 },
      { transform: "scale(1.08) rotate(2deg)", opacity: 1, offset: 0.6 },
      { transform: "scale(.98) rotate(-1deg)", offset: 0.8 },
      { transform: "scale(1) rotate(0)", opacity: 1 },
    ], { duration: reduceMotion ? 1 : 650, easing: "cubic-bezier(.2,.9,.3,1.2)", fill: "forwards" });
    if (!reduceMotion) sparkles(layer, w / 2, h / 2);
    $("#sp-close", wrap).onclick = close;
    layer.addEventListener("click", (e) => { if (e.target === wrap || e.target === layer) close(); });
    $("#sp-again", wrap).onclick = () => { layer.remove(); busy = false; ensureAudio(); show(); };
    $("#sp-open", wrap).onclick = () => {
      const app = item.extra && item.extra.app && item.extra.app.link ? item.extra.app : null;
      layer.remove();
      busy = false;
      if (app) openApp(app);
      else openDetail(item.id);
    };
  }

  return { init, show, requestPermission, needsPermission };
})();

// ------------------------------------------------------------------ indulás
applyTheme();
Surprise.init();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
window.addEventListener("hashchange", router);
async function start() {
  const state = await api("/api/auth/state").catch(() => null);
  if (!state || !state.user) return showAuth();
  document.body.classList.remove("auth-mode");
  await loadMeta();
  wasRunning = !!(META.refresh && META.refresh.running);
  router();
}
start();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
