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
  if (!res.ok) throw new Error((data && data.detail) || `Hiba (${res.status})`);
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
};

const ROUTES = [
  { path: "", label: "Akciók", title: "Top akciók", icon: "deals", nav: "both", render: renderDeals },
  { path: "ai", label: "AI kereső", title: "AI kereső", icon: "ai", nav: "both", render: renderAi },
  { path: "kuponok", label: "Kuponok", title: "Gyorsétterem kuponok", icon: "coupons", nav: "both", render: renderCoupons },
  { path: "jatekok", label: "Játékok", title: "Játékok", icon: "games", nav: "both", render: renderGames },
  { path: "lista", label: "Lista", title: "Bevásárlólista", icon: "list", nav: "both", render: renderShopping },
  { path: "mentett", label: "Mentett", title: "Mentett akciók", icon: "star", nav: "side", render: renderFavorites },
  { path: "figyelo", label: "Figyelő", title: "Figyelő és értesítések", icon: "bell", nav: "side", render: renderWatches },
  { path: "beallitasok", label: "Beállítások", title: "Beállítások", icon: "gear", nav: "side", render: renderSettings },
];

let META = { categories: [], stores: [], ai_enabled: false, unseen_alerts: 0, refresh: {} };
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
  const side = ROUTES.filter((r) => r.nav === "side").map(item).join("");
  $("#side-nav").innerHTML = main + '<div class="sep"></div>' + side;
}

function currentPath() {
  return location.hash.replace(/^#\/?/, "").split("?")[0];
}

async function router() {
  const path = currentPath();
  const route = ROUTES.find((r) => r.path === path) || ROUTES[0];
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
  $("#alert-dot").hidden = !META.unseen_alerts;
  const r = META.refresh || {};
  const banner = $("#refresh-banner");
  if (r.running) {
    banner.hidden = false;
    banner.innerHTML = `<span class="spinner"></span> Frissítés folyamatban: <b>${esc(r.current || "")}</b>…`;
  } else banner.hidden = true;
}

let wasRunning = false;
setInterval(async () => {
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

function dealCard(item, { reason } = {}) {
  const color = STORE_COLORS()[item.store] || "var(--text-3)";
  const until = item.valid_to ? untilText(item.valid_to) : "";
  const isGame = item.category === "jatek";
  const tags = [];
  if (item.badge) tags.push(`<span class="tag ${/hűség|plus/i.test(item.badge) ? "warn" : ""}">${esc(item.badge)}</span>`);
  if (until) tags.push(`<span class="tag ${/óráig|holnap/.test(until) ? "hot" : ""}">${until}</span>`);
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
    </div>
  </article>`;
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
    if (card) openDetail(card.dataset.id);
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
        ${item.url ? `<a class="btn primary" href="${esc(item.url)}" target="_blank" rel="noopener">Megnyitás ↗</a>` : ""}
        <button class="btn" id="d-fav">${item.favorite ? "★ Mentve" : "☆ Mentés"}</button>
        <button class="btn" id="d-watch">🔔 Figyelő</button>
        ${item.source === "manual" ? `<button class="btn" id="d-del">🗑 Törlés</button>` : ""}
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
          `<button class="btn primary" id="first-refresh">Frissítés most</button>`)
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
      <label class="toggle"><input type="checkbox" id="ai-deals" ${last?.only_deals ? "checked" : ""}> Csak akciós termékek</label>
      <div class="chips wrap" id="ai-ex">${AI_EXAMPLES.map((e) => `<button class="chip" type="button">${esc(e)}</button>`).join("")}</div>
      ${META.ai_enabled ? "" : `<div class="summary small">ℹ️ Még nincs Gemini API kulcs megadva, így egyszerű kulcsszavas keresés fut. <a href="#/beallitasok">Kulcs megadása a Beállításokban →</a></div>`}
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
      <div class="grow small">A kuponok a láncok saját appjában válthatók be. A <b>McDonald's</b> ajánlatai csak a MyMcDonald's appban vannak, azokat (és bármilyen más akciót) kézzel is felveheted.</div>
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
  root.innerHTML = `
    <form class="card-box" id="w-form" style="display:grid;gap:12px">
      <div><b>Új figyelő</b> <span class="muted small">Szólunk, ha új akció jelenik meg erre (az appban${" "}és ntfy push értesítésben, ha beállítottad).</span></div>
      <div class="form-grid">
        <label class="field" style="grid-column:1/-1">Kulcsszó<input class="input" name="query" required minlength="2" placeholder="pl. Nutella, Parkside fúró, Pampers 4" value="${esc(params.get("q") || "")}"></label>
        <label class="field">Max. ár (Ft)<input class="input" name="max_price" type="number" min="0" inputmode="numeric"></label>
        <label class="field">Min. kedvezmény (%)<input class="input" name="min_discount" type="number" min="0" max="99" inputmode="numeric"></label>
        <label class="field">Kategória<select class="select" name="category"><option value="">Bármelyik</option>
          ${META.categories.map((c) => `<option value="${c.key}">${c.icon} ${c.label}</option>`).join("")}</select></label>
      </div>
      <div class="row"><button class="btn primary" type="submit">Figyelő hozzáadása</button></div>
    </form>
    <section class="section">
      <div class="section-head"><h2>Figyelőid</h2></div>
      ${data.watches.length ? `<div class="card-box list">${data.watches.map((w) => `
        <div class="list-row"><div class="grow"><div class="t">🔔 ${esc(w.query)}</div>
          <div class="s">${[w.max_price ? `max ${fmtNum(w.max_price)} Ft` : "", w.min_discount ? `min -${w.min_discount}%` : "",
            w.category ? META.categories.find((c) => c.key === w.category)?.label : ""].filter(Boolean).join(" · ") || "bármilyen akció"}</div></div>
          <button class="btn small ghost" data-del="${w.id}">Törlés</button></div>`).join("")}</div>`
        : `<div class="muted">Még nincs figyelőd.</div>`}
    </section>
    <section class="section">
      <div class="section-head"><h2>Találatok</h2><span class="sub">${data.alerts.filter((a) => !a.seen).length} új</span></div>
      ${data.alerts.length ? `<div class="grid" id="w-alerts">${data.alerts.map((a) => dealCard({ ...a, badge: (a.seen ? "" : "ÚJ · ") + "🔔 " + a.watch_query })).join("")}</div>`
        : `<div class="muted">Amint valami megfelel a figyelőidnek, itt jelenik meg.</div>`}
    </section>`;
  const alertsEl = $("#w-alerts");
  if (alertsEl) bindCards(alertsEl);
  $("#w-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    const body = {
      query: fd.query.trim(), category: fd.category,
      max_price: fd.max_price ? Number(fd.max_price) : null,
      min_discount: fd.min_discount ? Number(fd.min_discount) : null,
    };
    try {
      const r = await api("/api/watches", { method: "POST", body });
      toast(r.matches_now ? `Figyelő kész – már most ${r.matches_now} találat!` : "Figyelő kész ✔");
      history.replaceState(null, "", "#/figyelo");
      renderWatches(root);
    } catch (err) { toast(err.message); }
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
      <div class="row"><button class="btn primary" id="s-save-ai">Mentés</button><button class="btn" id="s-test-ai">Kapcsolat tesztelése</button><span class="small" id="s-ai-msg"></span></div>
    </section>

    <section class="card-box section" style="display:grid;gap:12px">
      <div><b>🔔 Push értesítés (ntfy)</b><div class="muted small">Telepítsd az <a href="https://ntfy.sh" target="_blank" rel="noopener">ntfy</a> appot, iratkozz fel egy egyedi, nehezen kitalálható témára (pl. <code>akciok-${Math.random().toString(36).slice(2, 8)}</code>), és írd be ide ugyanazt.</div></div>
      <div class="form-grid">
        <label class="field">Téma (topic)<input class="input" id="s-topic" value="${esc(s.ntfy_topic)}" placeholder="akciok-valami-titkos"></label>
        <label class="field">Szerver<input class="input" id="s-ntfy" value="${esc(s.ntfy_server)}"></label>
      </div>
      <div class="row"><button class="btn primary" id="s-save-ntfy">Mentés</button><button class="btn" id="s-test-ntfy">Teszt értesítés</button></div>
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
    $("#s-ai-msg").innerHTML = '<span class="spinner"></span>';
    const r = await api("/api/ai/test", { method: "POST" });
    $("#s-ai-msg").innerHTML = `<span style="color:${r.ok ? "var(--good)" : "var(--bad)"}">${esc(r.message)}</span>`;
  };
  $("#s-save-ntfy").onclick = () => saveSettings({ ntfy_topic: $("#s-topic").value.trim(), ntfy_server: $("#s-ntfy").value.trim() || "https://ntfy.sh" });
  $("#s-test-ntfy").onclick = async () => {
    await saveSettings({ ntfy_topic: $("#s-topic").value.trim(), ntfy_server: $("#s-ntfy").value.trim() || "https://ntfy.sh" }, "Mentve");
    const r = await api("/api/notify/test", { method: "POST" });
    toast(r.ok ? "Teszt értesítés elküldve 📱" : "Nem sikerült – ellenőrizd a témát");
  };
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

// ------------------------------------------------------------------ indulás
applyTheme();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
window.addEventListener("hashchange", router);
(async () => {
  await loadMeta();
  wasRunning = !!(META.refresh && META.refresh.running);
  const src = await api("/api/sources").catch(() => null);
  if (src) {
    const last = src.sources.map((s) => s.last_ok).filter(Boolean).sort().pop();
    $("#side-status").textContent = last ? `Frissítve ${relTime(last)}` : "Még nincs adat";
  }
  router();
})();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
