// ---------- 📊 BLITZED PROJECTIONS (shared by the NHL, NFL and NBA pages) ----------
// Model numbers only: win chances, projected scores, player projections. No odds, no betting.
// Each page sets PJA (its adapter) and calls pjRender():
//   PJA.games()      -> [{id, state: pre|live|final, time, detail, a, h, ph, lph, sa, sh, score: {a, h}, stats: [[label, value]], note}]
//                       team = {abbr, name, color, logo, sub}
//   PJA.players()    -> [{id, gid, name, team, pos, img, logo, color, num, meta, vals: {mk: {v, txt, chance, live}}}]
//   PJA.markets      -> [{k, label, unit}]          (Players tab chips, in order)
//   PJA.panels(g)    -> [{k, label, html()}]        (a game card's details)
//   PJA.playerLines(id) -> [[label, chance]]        (player sheet: chances at common lines)
//   PJA.top()        -> [{p, mk}]                   (Home: headline projections)
//   PJA.kicker(), PJA.modelHtml(), PJA.modelWire(render), PJA.record(), PJA.after(render)
document.body.classList.add("shell", "pj");
// the date / last-update line sits on the league-tab row so the title row stays clean
(() => { const sub = document.getElementById("sub"), hb2 = document.querySelector(".hb2"); if (sub && hb2) hb2.insertBefore(sub, hb2.querySelector(".iconbtn")); })();
let PJA = null;
const PJ = {mk: null, q: "", game: "all", open: new Set(), panel: {}, n: 40};
const PJ_TABS = [["home", "Home"], ["games", "Games"], ["players", "Players"], ["model", "Model"]];
const PJ_IC = {
  home: '<path d="M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1z"/>',
  games: '<rect x="3.5" y="5" width="17" height="14" rx="2.5"/><path d="M12 5v14M3.5 12h17"/>',
  players: '<circle cx="12" cy="8" r="3.6"/><path d="M4.8 20c.9-3.7 3.7-5.6 7.2-5.6s6.3 1.9 7.2 5.6"/>',
  model: '<path d="M4 19V5M4 19h16"/><path d="m7 15 4-4 3 3 5-6"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
};
const pjIc = k => `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PJ_IC[k] || ""}</svg>`;
const pjImg = (src, cls = "", fb = "") => src ? `<img class="${cls}" src="${esc(src)}" alt="" loading="lazy" onerror="${fb ? `this.outerHTML='${fb}'` : "this.remove()"}">` : fb;
const pjLogo = (t, cls = "") => pjImg(t.logo, cls, `<i class=&quot;pj-code&quot;>${esc(t.abbr)}</i>`);
const pjPct = p => p == null || !isFinite(p) ? "–" : Math.round(100 * p) + "%";

// ---- headshot fallbacks: a photo that fails swaps to its alternate before the page falls back to initials ----
const PJ_IMG_ALT = {};
document.addEventListener("error", e => { const im = e.target; if (!im || im.tagName !== "IMG" || im.dataset.alt) return;
  const alt = PJ_IMG_ALT[im.getAttribute("src")]; if (!alt) return; im.dataset.alt = "1"; e.stopImmediatePropagation(); im.src = alt; }, true);
function pjImgAlts(players) { for (const p of players || []) { if (!p.headshot || PJ_IMG_ALT[p.headshot]) continue;
  const alt = p.headshot_alt || (/\/mugs\/nhl\/\d+\/[A-Z]+\//.test(p.headshot) ? p.headshot.replace(/\/mugs\/nhl\/\d+\/[A-Z]+\//, "/mugs/nhl/latest/") : null);
  if (alt) PJ_IMG_ALT[p.headshot] = alt; } }

// ---- shell: docked tab bar, sheet ----
function pjNav() {
  const el = document.getElementById("nav"); if (!el) return;
  el.style.setProperty("--n", PJ_TABS.length);
  el.innerHTML = PJ_TABS.map(([k, n]) => `<button class="${TAB === k ? "on" : ""}" data-k="${k}">${pjIc(k)}<span>${n}</span></button>`).join("");
  el.querySelectorAll("[data-k]").forEach(b => b.onclick = () => pjGo(b.dataset.k));
}
function pjGo(tab) {   // one smooth cross-fade between tabs where the browser supports it
  const go = () => { TAB = tab; pjRender(); window.scrollTo(0, 0); };
  if (document.startViewTransition && TAB !== tab) document.startViewTransition(go); else go();
}
function pjSheet(html) {
  const sh = document.getElementById("sheet"); sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>${html}`;
  document.getElementById("shx").onclick = closeSheet;
  document.getElementById("scrim").classList.add("open"); sh.classList.add("open"); sh.scrollTop = 0;
}
function closeSheet() { document.getElementById("scrim").classList.remove("open"); document.getElementById("sheet").classList.remove("open"); }

// ---- pieces ----
function pjMeter(p, cls = "") { return `<span class="pj-meter ${cls}"><i style="width:${Math.max(2, Math.min(100, Math.round(100 * (p || 0))))}%"></i></span>`; }
function pjStatus(g) {
  return g.state === "live" ? `<b class="bx-live">LIVE</b><span>${esc(g.detail || "")}</span>` : g.state === "final" ? `<b class="bx-fin">FINAL</b>` : `<span class="bx-time">${esc(g.time || "")}</span>`;
}
// compact row (Home lists): logos, names, win chance or score
function pjGameRow(g) {
  const side = (t, p, sc, other) => `<span class="gl-t">${pjLogo(t)}<b>${esc(t.name)}</b>${g.state === "pre" ? `<em>${pjPct(p)}</em>` : `<strong class="${g.state === "final" && sc < other ? "lose" : ""}">${sc ?? 0}</strong>`}</span>`;
  const right = g.state === "pre" ? `<span class="pj-proj"><b>${esc(g.sa)}–${esc(g.sh)}</b><i>proj</i></span>`
    : g.lph != null ? `<span class="pj-proj live"><b>${pjPct(g.state === "live" ? (g.lph >= 0.5 ? g.lph : 1 - g.lph) : null)}</b><i>${esc((g.lph >= 0.5 ? g.h : g.a).abbr)} live</i></span>`
    : g.state === "final" ? `<span class="pj-proj ${g.hit ? "hit" : g.hit === false ? "miss" : ""}"><b>${g.hit ? "✓" : g.hit === false ? "✗" : ""}</b><i>model</i></span>` : "";
  return `<button class="gl-r gs-${g.state}" data-gogame="${esc(g.id)}"><span class="gl-m"><span class="gl-st">${pjStatus(g)}</span>
    ${side(g.a, 1 - g.ph, g.score && g.score.a, g.score && g.score.h)}${side(g.h, g.ph, g.score && g.score.h, g.score && g.score.a)}</span>${right}</button>`;
}
// the game card: teams, win chance, projected score, the model's numbers; details open below
function pjGameCard(g) {
  const p = g.state === "live" && g.lph != null ? g.lph : g.ph;
  const team = (t, side) => { const mine = side === "h" ? p : 1 - p, sc = g.score ? g.score[side] : null, other = g.score ? g.score[side === "h" ? "a" : "h"] : null;
    return `<div class="pj-team ${mine >= 0.5 ? "fav" : ""}" style="--tc:${esc(t.color || "#556")}"><span class="bx-lg">${pjLogo(t)}</span>
      <span class="bx-nm"><b>${esc(t.name)}</b><i>${t.sub || ""}</i></span>
      ${g.state === "pre" ? `<span class="pj-ps">${esc(side === "h" ? g.sh : g.sa)}<i>proj</i></span>` : `<strong class="bx-sc ${g.state === "final" && sc < other ? "lose" : ""}">${sc ?? 0}</strong>`}
      <span class="pj-wp"><b>${pjPct(mine)}</b><i>${g.state === "live" && g.lph != null ? "live" : g.state === "final" ? "model" : "win"}</i></span></div>`; };
  const pa = Math.round(100 * (1 - p)), open = PJ.open.has(String(g.id));
  let body = "";
  if (open) { const P = PJA.panels(g), k = PJ.panel[g.id] && P.some(x => x.k === PJ.panel[g.id]) ? PJ.panel[g.id] : (P[0] || {}).k;
    body = `<div class="xpanel"><div class="xtabs">${P.map(x => `<button class="${x.k === k ? "on" : ""}" data-pv="${esc(g.id)}|${x.k}">${x.label}</button>`).join("")}</div>
      <div class="xbody">${(P.find(x => x.k === k) || {html: () => ""}).html()}</div></div>`; }
  return `<div class="card gc2 pj-gc ${g.state === "live" ? "islive" : ""}" data-gid="${esc(g.id)}"><div class="pj-in">
      <div class="pj-top"><span class="bx-st">${pjStatus(g)}</span>${g.note ? `<span class="pj-note">${g.note}</span>` : ""}</div>
      ${team(g.a, "a")}${team(g.h, "h")}
      <div class="bx-tug pj-tug"><i style="width:${pa}%;background:${esc(g.a.color || "#556")}"></i><i style="width:${100 - pa}%;background:${esc(g.h.color || "#556")}"></i></div>
      ${g.stats && g.stats.length ? `<div class="pj-stats">${g.stats.map(([l, v]) => `<div><i>${l}</i><b>${v}</b></div>`).join("")}</div>` : ""}</div>
    ${body}<button class="more" data-more="${esc(g.id)}">${open ? "Hide details" : "Matchup · players · details"}<span class="chev ${open ? "up" : ""}">›</span></button></div>`;
}
function pjPlayerRow(p, mk) {
  const m = PJA.markets.find(x => x.k === mk) || PJA.markets[0], v = p.vals[mk] || {};
  return `<button class="pj-pr" data-player="${esc(p.id)}" style="--tc:${esc(p.color || "#556")}">
    <span class="pav"><span>${esc(pjIni(p.name))}</span>${p.img ? `<img src="${esc(p.img)}" alt="" loading="lazy" onload="this.previousElementSibling.style.visibility='hidden'" onerror="this.remove()">` : ""}${p.logo ? `<img class="ptl" src="${esc(p.logo)}" alt="" onerror="this.remove()">` : ""}</span>
    <span class="pj-pi"><b>${esc(p.name)}</b><i>${esc(p.meta || "")}</i>${v.chance != null ? `<span class="pj-pc">${pjMeter(v.chance)}<em>${v.txt === pjPct(v.chance) ? "" : `${pjPct(v.chance)} ${esc(v.chanceLab || "")}`}</em></span>` : ""}</span>
    <span class="pj-pv"><b>${esc(v.txt ?? "–")}</b><i>${esc(m.unit)}</i>${v.live != null ? `<em class="pj-live">${esc(v.live)} now</em>` : ""}</span></button>`;
}
const pjIni = n => { const q = String(n).split(" ").filter((w, k) => w && (!k || !/^(jr|sr|ii|iii|iv|v)\.?$/i.test(w))); return q.length > 1 ? q[0][0] + q[q.length - 1][0] : String(n).slice(0, 2); };

// ---- screens ----
function pjHome() {
  const G = PJA.games(), P = PJA.players();
  if (!G.length) return `<div class="card empty"><div class="e">🗓️</div><div class="t">No games on the board</div><div class="note">Projections appear once the next slate is set.</div></div>`;
  const pre = G.filter(g => g.state === "pre"), live = G.filter(g => g.state === "live");
  const fav = [...pre].sort((x, y) => Math.max(y.ph, 1 - y.ph) - Math.max(x.ph, 1 - x.ph))[0];
  const close = [...pre].sort((x, y) => Math.abs(x.ph - 0.5) - Math.abs(y.ph - 0.5))[0];
  const hi = [...pre].sort((x, y) => (y.total || 0) - (x.total || 0))[0];
  const tile = (k, g, v, s) => g ? `<button class="pj-ht" data-gogame="${esc(g.id)}"><i>${k}</i><b>${v}</b><span>${s}</span></button>` : "";
  const hero = `<section class="w-card pj-hero"><div class="w-top"><span class="w-k">${esc(PJA.kicker())}</span>${live.length ? `<span class="w-run"><em class="up">● ${live.length} live</em></span>` : ""}</div>
      <div class="w-bal">${G.length}<small> game${G.length > 1 ? "s" : ""}</small></div>
      <div class="w-sub"><span>Model projections · win chances · player outlooks</span></div>
      <div class="pj-hts">${tile("Biggest favourite", fav, fav ? `${esc((fav.ph >= 0.5 ? fav.h : fav.a).abbr)} ${pjPct(Math.max(fav.ph, 1 - fav.ph))}` : "", fav ? `vs ${esc((fav.ph >= 0.5 ? fav.a : fav.h).abbr)}` : "")}
        ${tile("Closest game", close, close ? `${esc(close.a.abbr)}–${esc(close.h.abbr)}` : "", close ? `${pjPct(1 - close.ph)} / ${pjPct(close.ph)}` : "")}
        ${tile(PJA.totalLabel || "Highest total", hi, hi ? esc(hi.totalTxt || "") : "", hi ? `${esc(hi.a.abbr)} @ ${esc(hi.h.abbr)}` : "")}</div></section>`;
  const top = (PJA.top ? PJA.top() : []).slice(0, 8);
  const cards = top.map(({p, mk}) => { const m = PJA.markets.find(x => x.k === mk), v = p.vals[mk] || {};
    return `<button class="fc fc-head pj-fc" data-player="${esc(p.id)}" style="--tc:${esc(p.color || "#556")}">${p.logo ? `<img class="fc-wm" src="${esc(p.logo)}" alt="" onerror="this.remove()">` : ""}${p.img ? `<img class="fc-cut" src="${esc(p.img)}" alt="" onerror="this.remove()">` : ""}
      <div class="fc-hd"><span class="fc-tag">${esc(m.label)}</span></div><b class="fc-t"><small>${esc(p.name.split(" ")[0])}</small>${esc(p.name.split(" ").slice(1).join(" ") || p.name)}</b><i class="fc-s">${esc(p.meta || "")}</i>
      <div class="pj-fcv"><b>${esc(v.txt ?? "–")}</b><i>${esc(v.chance != null && v.txt !== pjPct(v.chance) ? `${pjPct(v.chance)} ${v.chanceLab || ""}` : m.unit)}</i></div></button>`; }).join("");
  return `<div class="hx hx2">${hero}
    ${live.length ? `<div class="hx-h"><b>Live now</b><button data-go="games">All games ›</button></div><div class="gl">${live.map(pjGameRow).join("")}</div>` : ""}
    ${cards ? `<div class="hx-h"><b>${esc(PJA.topLabel || "Top projections")}</b><button data-go="players">All players ›</button></div><div class="fz">${cards}</div>` : ""}
    <div class="hx-h"><b>${esc(PJA.gamesLabel || "Tonight's games")}</b><button data-go="games">Details ›</button></div><div class="gl">${G.filter(g => g.state !== "live").map(pjGameRow).join("")}</div>
    ${PJA.record ? PJA.record() : ""}</div>`;
}
function pjGames() {
  const G = PJA.games();
  if (!G.length) return `<div class="card empty"><div class="e">🗓️</div><div class="t">No games on the board</div><div class="note">Check back on the next game day.</div></div>`;
  return (PJA.gamesHead ? PJA.gamesHead() : "") + G.map(pjGameCard).join("");
}
function pjPlayers() {
  const all = PJA.players();
  if (!all.length) return `<div class="card empty"><div class="e">👤</div><div class="t">No player projections yet</div><div class="note">They appear once lineups are in.</div></div>`;
  if (!PJ.mk || !PJA.markets.some(m => m.k === PJ.mk)) PJ.mk = PJA.markets[0].k;
  const m = PJA.markets.find(x => x.k === PJ.mk), q = PJ.q.trim().toLowerCase(), G = PJA.games();
  let L = all.filter(p => p.vals[m.k] && p.vals[m.k].v != null && (PJ.game === "all" || String(p.gid) === PJ.game)
    && (!q || p.name.toLowerCase().includes(q) || String(p.team).toLowerCase() === q));
  L.sort((x, y) => y.vals[m.k].v - x.vals[m.k].v);
  const tabs = `<div class="ptabs props-seg pj-mk" style="--n:${PJA.markets.length}"><i class="mkpill" style="--i:${PJA.markets.indexOf(m)}"></i>${PJA.markets.map(x => `<button class="${x.k === m.k ? "on" : ""}" data-pjmk="${x.k}">${x.label}</button>`).join("")}</div>`;
  const chips = `<div class="strip pj-strip"><button class="chip ${PJ.q ? "on" : ""}" data-pjsearch="1" aria-label="Search">${pjIc("search")}</button><button class="chip ${PJ.game === "all" ? "on" : ""}" data-pjg="all">All games</button>${G.map(g => `<button class="chip ${PJ.game === String(g.id) ? "on" : ""}" data-pjg="${esc(g.id)}">${pjLogo(g.a)}${pjLogo(g.h)}${esc(g.a.abbr)} @ ${esc(g.h.abbr)}</button>`).join("")}</div>
    ${PJ.searching || PJ.q ? `<input class="search" id="pjq" placeholder="Search a player or team" value="${esc(PJ.q)}" autocomplete="off">` : ""}`;
  return tabs + chips + `<div class="pj-note2">${esc(m.note || "")}</div><div class="card pj-list">${L.slice(0, PJ.n).map(p => pjPlayerRow(p, m.k)).join("") || `<div class="note">No players match.</div>`}</div>
    ${L.length > PJ.n ? `<button class="gmore" data-pjmore="1">Show more (${L.length - PJ.n})</button>` : ""}`;
}
function pjOpenPlayer(id) {
  const p = PJA.players().find(x => String(x.id) === String(id)); if (!p) return;
  const tiles = PJA.markets.filter(m => p.vals[m.k] && p.vals[m.k].v != null).map(m => { const v = p.vals[m.k];
    return `<div class="ps-tile"><b>${esc(v.txt)}</b><span>${esc(m.label)}</span>${v.live != null ? `<em class="pj-live">${esc(v.live)} now</em>` : ""}</div>`; }).join("");
  const lines = PJA.playerLines ? PJA.playerLines(p.id) : [];
  pjSheet(`<div class="pj-ph" style="--tc:${esc(p.color || "#556")}"><span class="pav big"><span>${esc(pjIni(p.name))}</span>${p.img ? `<img src="${esc(p.img)}" alt="" onload="this.previousElementSibling.style.visibility='hidden'" onerror="this.remove()">` : ""}</span>
      <div><div class="sh-t">${esc(p.name)}</div><div class="sh-s">${esc(p.meta || "")}</div></div>${p.logo ? `<img class="pj-phl" src="${esc(p.logo)}" alt="" onerror="this.remove()">` : ""}</div>
    <div class="pj-tiles">${tiles}</div>
    ${lines.length ? `<div class="sec">Chances by line</div><div class="pj-lines">${lines.map(([l, c]) => `<div class="pj-ln"><span>${esc(l)}</span>${pjMeter(c)}<b>${pjPct(c)}</b></div>`).join("")}</div>` : ""}
    <div class="hint">${esc(PJA.sheetNote || "")}</div>`);
}
function pjRender() {
  if (!PJA) return;
  try { PJA.header && PJA.header(); PJA.strip && PJA.strip(); } catch (e) {}
  pjNav();
  const b = document.body;
  [...b.classList].filter(c => c.startsWith("tab-")).forEach(c => b.classList.remove(c)); b.classList.add("tab-" + TAB);
  const v = document.getElementById("view");
  const html = ({home: pjHome, games: pjGames, players: pjPlayers, model: () => PJA.modelHtml()}[TAB] || pjHome)();
  if (html !== window.PJ_HTML || v.dataset.tab !== TAB) { window.PJ_HTML = html; v.dataset.tab = TAB; v.innerHTML = html; }   // identical redraws leave the screen alone
  window.PJ_LAST = TAB;
  v.querySelectorAll("[data-go]").forEach(x => x.onclick = () => pjGo(x.dataset.go));
  v.querySelectorAll("[data-gogame]").forEach(x => x.onclick = () => { PJ.open.add(String(x.dataset.gogame)); TAB = "games"; pjRender();
    const c = document.querySelector(`.pj-gc[data-gid="${CSS.escape(String(x.dataset.gogame))}"]`); if (c) window.scrollTo({top: c.getBoundingClientRect().top + scrollY - 120}); });
  v.querySelectorAll("[data-more]").forEach(x => x.onclick = () => { const k = String(x.dataset.more); PJ.open.has(k) ? PJ.open.delete(k) : PJ.open.add(k); pjRender(); });
  v.querySelectorAll("[data-pv]").forEach(x => x.onclick = () => { const [id, k] = x.dataset.pv.split("|"); PJ.panel[id] = k; pjRender(); });
  v.querySelectorAll("[data-player]").forEach(x => x.onclick = e => { e.stopPropagation(); pjOpenPlayer(x.dataset.player); });
  v.querySelectorAll("[data-pjmk]").forEach(x => x.onclick = () => { PJ.mk = x.dataset.pjmk; PJ.n = 40; pjRender(); });
  v.querySelectorAll("[data-pjg]").forEach(x => x.onclick = () => { PJ.game = x.dataset.pjg; PJ.n = 40; pjRender(); });
  v.querySelectorAll("[data-pjmore]").forEach(x => x.onclick = () => { PJ.n += 40; pjRender(); });
  v.querySelectorAll("[data-pjsearch]").forEach(x => x.onclick = () => { PJ.searching = !PJ.searching; if (!PJ.searching) PJ.q = ""; pjRender(); const i = document.getElementById("pjq"); if (i) i.focus(); });
  const q = document.getElementById("pjq");
  if (q) q.oninput = () => { PJ.q = q.value; const pos = q.selectionStart; pjRender(); const n = document.getElementById("pjq"); if (n) { n.focus(); n.setSelectionRange(pos, pos); } };
  if (TAB === "model" && PJA.modelWire) PJA.modelWire(pjRender);
  if (PJA.after) PJA.after(pjRender);
  requestAnimationFrame(() => { const h = document.querySelector(".hdr"); if (h) { const hv = h.offsetHeight + "px"; if (window.PJ_HH !== hv) { window.PJ_HH = hv; document.documentElement.style.setProperty("--hdrh", hv); } } });
  const sp = document.getElementById("splash"); if (sp && !sp.classList.contains("out")) { sp.classList.add("out"); setTimeout(() => sp.remove(), 600); }
}
window.addEventListener("scroll", () => { const h = document.querySelector(".hdr"); if (h) h.classList.toggle("stuck", window.scrollY > 8); }, {passive: true});
