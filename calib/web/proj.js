// ---------- BLITZED (shared by the NHL, NFL and NBA pages) ----------
// Model projections plus a play-coin book priced by the model (calib/web/book.js).
// Each page sets PJA (its adapter) and calls pjRender():
//   PJA.games()      -> [{id, state: pre|live|final, time, detail, a, h, ph, lph, sa, sh, score: {a, h}, stats: [[label, value]], note}]
//                       team = {abbr, name, color, logo, sub}
//   PJA.players()    -> [{id, gid, name, team, pos, img, logo, color, meta, vals: {mk: {v, txt, chance, chanceLab, live}}}]
//   PJA.markets      -> [{k, label, unit, note}]     (Players tab, in order)
//   PJA.panels(g)    -> [{k, label, html()}]          (a game card's details)
//   PJA.playerLines(id) -> [[label, chance, {stat, n}]]  (player sheet; the third item makes the line bettable)
//   PJA.ctx(gid)     -> {sport, game, start, open, ev: {date, home, away, id}}   (what a bet needs to be graded)
//   PJA.lines(gid)   -> {spreadLab, spread: [a, h], total: [over, under], ml: [a, h]} of bkSel selections
//   PJA.top(), PJA.kicker(), PJA.modelHtml(), PJA.modelWire(render), PJA.record(), PJA.after(render)
document.body.classList.add("pj");
let PJA = null;
const PJ = {mk: null, q: "", game: "all", open: new Set(), panel: {}, n: 40};
const PJ_TABS = [["home", "Home"], ["games", "Games"], ["players", "Players"], ["bets", "Bets"], ["model", "Model"]];
const PJ_IC = {
  home: '<path d="M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1z"/>',
  games: '<rect x="3.5" y="5" width="17" height="14" rx="3"/><path d="M12 5v14M3.5 12h17"/>',
  players: '<circle cx="12" cy="8" r="3.6"/><path d="M4.8 20c.9-3.7 3.7-5.6 7.2-5.6s6.3 1.9 7.2 5.6"/>',
  bets: '<path d="M4 7.5A1.5 1.5 0 0 1 5.5 6h13A1.5 1.5 0 0 1 20 7.5V10a2 2 0 0 0 0 4v2.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 16.5V14a2 2 0 0 0 0-4z"/><path d="M14.5 6v12" stroke-dasharray="2 2"/>',
  model: '<path d="M4 19V5M4 19h16"/><path d="m7 15 4-4 3 3 5-6"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
};
const pjIc = k => `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PJ_IC[k] || ""}</svg>`;
const pjImg = (src, cls = "", fb = "") => src ? `<img class="${cls}" src="${esc(src)}" alt="" loading="lazy" onerror="${fb ? `this.outerHTML='${fb}'` : "this.remove()"}">` : fb;
const pjLogo = (t, cls = "") => pjImg(t.logo, cls, `<i class=&quot;pj-code&quot;>${esc(t.abbr)}</i>`);
const pjPct = p => p == null || !isFinite(p) ? "–" : Math.round(100 * p) + "%";
const pjIni = n => { const q = String(n).split(" ").filter((w, k) => w && (!k || !/^(jr|sr|ii|iii|iv|v)\.?$/i.test(w))); return q.length > 1 ? q[0][0] + q[q.length - 1][0] : String(n).slice(0, 2); };
const pjSp = x => x == null ? "" : x === 0 ? "PK" : (x > 0 ? "+" : "−") + Math.abs(x);

// ---- headshot fallbacks: a photo that fails swaps to its alternate before the page falls back to initials ----
const PJ_IMG_ALT = {};
document.addEventListener("error", e => { const im = e.target; if (!im || im.tagName !== "IMG" || im.dataset.alt) return;
  const alt = PJ_IMG_ALT[im.getAttribute("src")]; if (!alt) return; im.dataset.alt = "1"; e.stopImmediatePropagation(); im.src = alt; }, true);
function pjImgAlts(players) { for (const p of players || []) { if (!p.headshot || PJ_IMG_ALT[p.headshot]) continue;
  const alt = p.headshot_alt || (/\/mugs\/nhl\/\d+\/[A-Z]+\//.test(p.headshot) ? p.headshot.replace(/\/mugs\/nhl\/\d+\/[A-Z]+\//, "/mugs/nhl/latest/") : null);
  if (alt) PJ_IMG_ALT[p.headshot] = alt; } }

// ---- shell: header coin, docked tab bar, sheet ----
(() => {
  const sub = document.getElementById("sub"), hb2 = document.querySelector(".hb2"), hb1 = document.querySelector(".hb1");
  if (sub && hb2) hb2.insertBefore(sub, hb2.querySelector(".iconbtn"));
  if (hb1 && !document.getElementById("coin")) { const c = document.createElement("button"); c.id = "coin"; c.className = "coin"; c.setAttribute("aria-label", "Wallet");
    c.onclick = () => pjGo("bets"); hb1.appendChild(c); }
})();
function pjNav() {
  const el = document.getElementById("nav"); if (!el) return;
  const open = BKS.bets.filter(b => b.st === "open").length;
  const html = PJ_TABS.map(([k, n]) => `<button class="${TAB === k ? "on" : ""}" data-k="${k}">${pjIc(k)}<span>${n}</span>${k === "bets" && open ? `<em>${open}</em>` : ""}</button>`).join("");
  if (el.dataset.h !== html) { el.dataset.h = html; el.innerHTML = html; el.querySelectorAll("[data-k]").forEach(b => b.onclick = () => pjGo(b.dataset.k)); }
}
function pjGo(tab) {   // one smooth cross-fade between tabs where the browser supports it
  const go = () => { TAB = tab; pjRender(); window.scrollTo(0, 0); };
  if (document.startViewTransition && TAB !== tab) document.startViewTransition(go); else go();
}
function pjSheet(html) {
  const sh = document.getElementById("sheet"); sh.className = "sheet" + (sh.classList.contains("open") ? " open" : "");   // re-drawing an open sheet keeps it in place
  sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>${html}`;
  document.getElementById("shx").onclick = closeSheet;
  document.getElementById("scrim").onclick = closeSheet;
  document.getElementById("scrim").classList.add("open"); requestAnimationFrame(() => sh.classList.add("open")); sh.scrollTop = 0;
  bkWire(sh);
}
function closeSheet() { document.getElementById("scrim").classList.remove("open"); document.getElementById("sheet").classList.remove("open"); }

// ---- pieces ----
function pjMeter(p, cls = "") { return `<span class="pj-meter ${cls}"><i style="width:${Math.max(2, Math.min(100, Math.round(100 * (p || 0))))}%"></i></span>`; }
function pjStatus(g) {
  return g.state === "live" ? `<b class="st-live">Live</b><span>${esc(g.detail || "")}</span>` : g.state === "final" ? `<b class="st-fin">Final</b>` : `<span class="st-time">${esc(g.time || "")}</span>`;
}
// compact row (Home lists): logos, names, win chance or score
function pjGameRow(g) {
  const side = (t, p, sc, other) => `<span class="gl-t">${pjLogo(t)}<b>${esc(t.name)}</b>${g.state === "pre" ? `<em>${pjPct(p)}</em>` : `<strong class="${g.state === "final" && sc < other ? "lose" : ""}">${sc ?? 0}</strong>`}</span>`;
  const right = g.state === "pre" ? `<span class="gl-p"><b>${esc(g.sa)}–${esc(g.sh)}</b><i>proj</i></span>`
    : g.lph != null ? `<span class="gl-p live"><b>${pjPct(g.state === "live" ? (g.lph >= 0.5 ? g.lph : 1 - g.lph) : null)}</b><i>${esc((g.lph >= 0.5 ? g.h : g.a).abbr)} live</i></span>`
    : g.state === "final" ? `<span class="gl-p ${g.hit ? "hit" : g.hit === false ? "miss" : ""}"><b>${g.hit ? "✓" : g.hit === false ? "✕" : ""}</b><i>model</i></span>` : "";
  return `<button class="gl-r gs-${g.state}" data-gogame="${esc(g.id)}"><span class="gl-m"><span class="gl-st">${pjStatus(g)}</span>
    ${side(g.a, 1 - g.ph, g.score && g.score.a, g.score && g.score.h)}${side(g.h, g.ph, g.score && g.score.h, g.score && g.score.a)}</span>${right}</button>`;
}
// the market grid on a game card: spread / total / moneyline, priced from the model
function pjMarkets(g) {
  if (g.state !== "pre" || !PJA.lines) return "";
  const M = PJA.lines(g.id); if (!M) return "";
  const sp = (M.spread || [])[0], tot = (M.total || [])[0];
  const row = (t, i) => `<span class="mk-t">${pjLogo(t)}<b>${esc(t.abbr)}</b></span>
    ${bkBtn((M.spread || [])[i], (M.spread || [])[i] ? pjSp((M.spread || [])[i].line) : "")}
    ${bkBtn((M.total || [])[i], (M.total || [])[i] ? `${i ? "U" : "O"} ${(M.total || [])[i].line}` : "")}
    ${bkBtn((M.ml || [])[i])}`;
  return `<div class="mk"><span></span><i>${esc(M.spreadLab || "Spread")}</i><i>Total</i><i>Money</i>${row(g.a, 0)}${row(g.h, 1)}</div>`;
}
// the game card: teams, win chance, projected score, prices; details open below
function pjGameCard(g) {
  const p = g.state === "live" && g.lph != null ? g.lph : g.ph;
  const team = (t, side) => { const mine = side === "h" ? p : 1 - p, sc = g.score ? g.score[side] : null, other = g.score ? g.score[side === "h" ? "a" : "h"] : null;
    return `<div class="gc-t ${mine >= 0.5 ? "fav" : ""}" style="--tc:${esc(t.color || "#556")}"><span class="gc-lg">${pjLogo(t)}</span>
      <span class="gc-nm"><b>${esc(t.name)}</b><i>${t.sub || ""}</i></span>
      ${g.state === "pre" ? `<span class="gc-ps">${esc(side === "h" ? g.sh : g.sa)}<i>proj</i></span>` : `<strong class="gc-sc ${g.state === "final" && sc < other ? "lose" : ""}">${sc ?? 0}</strong>`}
      <span class="gc-wp"><b>${pjPct(mine)}</b><i>${g.state === "live" && g.lph != null ? "live" : g.state === "final" ? "model" : "win"}</i></span></div>`; };
  const pa = Math.round(100 * (1 - p)), open = PJ.open.has(String(g.id));
  let body = "";
  if (open) { const P = PJA.panels(g), k = PJ.panel[g.id] && P.some(x => x.k === PJ.panel[g.id]) ? PJ.panel[g.id] : (P[0] || {}).k;
    body = `<div class="xpanel"><div class="seg" style="--n:${P.length}">${P.map(x => `<button class="${x.k === k ? "on" : ""}" data-pv="${esc(g.id)}|${x.k}">${x.label}</button>`).join("")}</div>
      <div class="xbody">${(P.find(x => x.k === k) || {html: () => ""}).html()}</div></div>`; }
  return `<article class="gc ${g.state === "live" ? "islive" : ""}" data-gid="${esc(g.id)}">
      <div class="gc-top"><span class="gc-st">${pjStatus(g)}</span>${g.note ? `<span class="gc-note">${g.note}</span>` : ""}</div>
      ${team(g.a, "a")}${team(g.h, "h")}
      <div class="gc-tug"><i style="width:${pa}%;background:${esc(g.a.color || "#556")}"></i><i style="width:${100 - pa}%;background:${esc(g.h.color || "#556")}"></i></div>
      ${g.stats && g.stats.length ? `<div class="gc-stats">${g.stats.map(([l, v]) => `<div><i>${l}</i><b>${v}</b></div>`).join("")}</div>` : ""}
      ${pjMarkets(g)}
    ${body}<button class="more" data-more="${esc(g.id)}">${open ? "Hide details" : "Matchup · players · details"}<span class="chev ${open ? "up" : ""}">›</span></button></article>`;
}
function pjAv(p, cls = "") {
  return `<span class="pav ${cls}" style="--tc:${esc(p.color || "#556")}"><span>${esc(pjIni(p.name))}</span>${p.img ? `<img src="${esc(p.img)}" alt="" loading="lazy" onload="this.previousElementSibling.style.visibility='hidden'" onerror="this.remove()">` : ""}</span>`;
}
function pjPlayerRow(p, mk) {
  const m = PJA.markets.find(x => x.k === mk) || PJA.markets[0], v = p.vals[mk] || {};
  return `<button class="pj-pr" data-player="${esc(p.id)}" style="--tc:${esc(p.color || "#556")}">${pjAv(p)}
    <span class="pj-pi"><b>${esc(p.name)}</b><i>${esc(p.meta || "")}</i>${v.chance != null ? `<span class="pj-pc">${pjMeter(v.chance)}<em>${v.txt === pjPct(v.chance) ? "" : `${pjPct(v.chance)} ${esc(v.chanceLab || "")}`}</em></span>` : ""}</span>
    <span class="pj-pv"><b>${esc(v.txt ?? "–")}</b><i>${esc(m.unit)}</i>${v.live != null ? `<em class="pj-live">${esc(v.live)} now</em>` : ""}</span></button>`;
}
const pjEmpty = (t, s) => `<div class="empty"><div class="t">${esc(t)}</div><div class="note">${esc(s)}</div></div>`;

// ---- screens ----
function pjHome() {
  const G = PJA.games(), s = bkStats();
  const book = `<button class="hm-book" data-go="bets"><span class="hm-bal">${BK_COIN}<b>${bkN(BKS.coins)}</b></span>
      <span class="hm-bs"><i>${s.open ? `${s.open} open · ${bkN(s.risk)} in play` : "No open bets"}</i>${BKS.drop !== bkDay() ? `<em>Daily drop ready</em>` : s.today ? `<em class="${s.today > 0 ? "up" : "dn"}">${s.today > 0 ? "+" : "−"}${bkN(Math.abs(s.today))} today</em>` : ""}</span><span class="chev">›</span></button>`;
  if (!G.length) return book + pjEmpty("No games on the board", "Projections and prices appear once the next slate is set.");
  const pre = G.filter(g => g.state === "pre"), live = G.filter(g => g.state === "live");
  const fav = [...pre].sort((x, y) => Math.max(y.ph, 1 - y.ph) - Math.max(x.ph, 1 - x.ph))[0];
  const close = [...pre].sort((x, y) => Math.abs(x.ph - 0.5) - Math.abs(y.ph - 0.5))[0];
  const hi = [...pre].sort((x, y) => (y.total || 0) - (x.total || 0))[0];
  const tile = (k, g, v, sub) => g ? `<button class="hm-tile" data-gogame="${esc(g.id)}"><i>${k}</i><b>${v}</b><span>${sub}</span></button>` : "";
  const hero = `<section class="hm-hero"><div class="hm-k">${esc(PJA.kicker())}${live.length ? `<em>● ${live.length} live</em>` : ""}</div>
      <div class="hm-n">${G.length}<small>game${G.length > 1 ? "s" : ""}</small></div>
      ${pre.length ? `<div class="hm-tiles">${tile("Biggest favourite", fav, fav ? `${esc((fav.ph >= 0.5 ? fav.h : fav.a).abbr)} ${pjPct(Math.max(fav.ph, 1 - fav.ph))}` : "", fav ? `vs ${esc((fav.ph >= 0.5 ? fav.a : fav.h).abbr)}` : "")}
        ${tile("Coin flip", close, close ? `${esc(close.a.abbr)}–${esc(close.h.abbr)}` : "", close ? `${pjPct(1 - close.ph)} / ${pjPct(close.ph)}` : "")}
        ${tile(PJA.totalLabel || "Highest total", hi, hi ? esc(hi.totalTxt || "") : "", hi ? `${esc(hi.a.abbr)} @ ${esc(hi.h.abbr)}` : "")}</div>` : ""}</section>`;
  const top = (PJA.top ? PJA.top() : []).slice(0, 8);
  const cards = top.map(({p, mk}) => { const m = PJA.markets.find(x => x.k === mk), v = p.vals[mk] || {};
    return `<button class="tp" data-player="${esc(p.id)}" style="--tc:${esc(p.color || "#556")}">${p.logo ? `<img class="tp-wm" src="${esc(p.logo)}" alt="" onerror="this.remove()">` : ""}${p.img ? `<img class="tp-cut" src="${esc(p.img)}" alt="" onerror="this.remove()">` : ""}
      <span class="tp-tag">${esc(m.label)}</span><b class="tp-n"><small>${esc(p.name.split(" ")[0])}</small>${esc(p.name.split(" ").slice(1).join(" ") || p.name)}</b><i class="tp-m">${esc(p.meta || "")}</i>
      <span class="tp-v"><b>${esc(v.txt ?? "–")}</b><i>${esc(v.chance != null && v.txt !== pjPct(v.chance) ? `${pjPct(v.chance)} ${v.chanceLab || ""}` : m.unit)}</i></span></button>`; }).join("");
  return book + hero
    + (live.length ? `<div class="hd"><b>Live now</b><button data-go="games">All games ›</button></div><div class="gl">${live.map(pjGameRow).join("")}</div>` : "")
    + (cards ? `<div class="hd"><b>${esc(PJA.topLabel || "Top projections")}</b><button data-go="players">All players ›</button></div><div class="tps">${cards}</div>` : "")
    + `<div class="hd"><b>${esc(PJA.gamesLabel || "Tonight's games")}</b><button data-go="games">Prices ›</button></div><div class="gl">${G.filter(g => g.state !== "live").map(pjGameRow).join("")}</div>`
    + (PJA.record ? PJA.record() : "");
}
function pjGames() {
  const G = PJA.games();
  if (!G.length) return pjEmpty("No games on the board", "Check back on the next game day.");
  return (PJA.gamesHead ? PJA.gamesHead() : "") + G.map(pjGameCard).join("");
}
function pjPlayers() {
  const all = PJA.players();
  if (!all.length) return pjEmpty("No player projections yet", "They appear once lineups are in.");
  if (!PJ.mk || !PJA.markets.some(m => m.k === PJ.mk)) PJ.mk = PJA.markets[0].k;
  const m = PJA.markets.find(x => x.k === PJ.mk), q = PJ.q.trim().toLowerCase(), G = PJA.games();
  let L = all.filter(p => p.vals[m.k] && p.vals[m.k].v != null && (PJ.game === "all" || String(p.gid) === PJ.game)
    && (!q || p.name.toLowerCase().includes(q) || String(p.team).toLowerCase() === q));
  L.sort((x, y) => y.vals[m.k].v - x.vals[m.k].v);
  const tabs = `<div class="seg pj-mk" style="--n:${PJA.markets.length}">${PJA.markets.map(x => `<button class="${x.k === m.k ? "on" : ""}" data-pjmk="${x.k}">${x.label}</button>`).join("")}</div>`;
  const chips = `<div class="strip pj-strip"><button class="chip ${PJ.q ? "on" : ""}" data-pjsearch="1" aria-label="Search">${pjIc("search")}</button><button class="chip ${PJ.game === "all" ? "on" : ""}" data-pjg="all">All games</button>${G.map(g => `<button class="chip ${PJ.game === String(g.id) ? "on" : ""}" data-pjg="${esc(g.id)}">${pjLogo(g.a)}${pjLogo(g.h)}${esc(g.a.abbr)} @ ${esc(g.h.abbr)}</button>`).join("")}</div>
    ${PJ.searching || PJ.q ? `<input class="search" id="pjq" placeholder="Search a player or team" value="${esc(PJ.q)}" autocomplete="off">` : ""}`;
  return tabs + chips + `<div class="pj-note2">${esc(m.note || "")} · tap a player for prices</div><div class="list">${L.slice(0, PJ.n).map(p => pjPlayerRow(p, m.k)).join("") || `<div class="note">No players match.</div>`}</div>
    ${L.length > PJ.n ? `<button class="gmore" data-pjmore="1">Show more (${L.length - PJ.n})</button>` : ""}`;
}
function pjOpenPlayer(id) {
  const p = PJA.players().find(x => String(x.id) === String(id)); if (!p) return;
  const tiles = PJA.markets.filter(m => p.vals[m.k] && p.vals[m.k].v != null).map(m => { const v = p.vals[m.k];
    return `<div class="ps-tile"><b>${esc(v.txt)}</b><span>${esc(m.label)}</span>${v.live != null ? `<em class="pj-live">${esc(v.live)} now</em>` : ""}</div>`; }).join("");
  const lines = PJA.playerLines ? PJA.playerLines(p.id) : [], C = PJA.ctx ? PJA.ctx(p.gid) : null;
  const priced = ([l, c, spec]) => { if (!spec || !C || c == null || c < 0.02 || c > 0.985) return "";
    return bkBtn(bkSel({sport: C.sport, gid: p.gid, kind: "prop", side: "yes", line: spec.n, p: c, pick: `${p.name} ${l}`, mkt: "Player prop", game: C.game, start: C.start, open: C.open, ev: C.ev,
      pl: {name: p.name, id: String(p.id), espn: !!C.espnIds, team: p.team, stat: spec.stat, n: spec.n}})); };
  pjSheet(`<div class="ps-h" style="--tc:${esc(p.color || "#556")}">${pjAv(p, "big")}
      <div><div class="sh-t">${esc(p.name)}</div><div class="sh-s">${esc(p.meta || "")}</div></div>${p.logo ? `<img class="ps-lg" src="${esc(p.logo)}" alt="" onerror="this.remove()">` : ""}</div>
    <div class="ps-tiles">${tiles}</div>
    ${lines.length ? `<div class="sec">Lines${C && C.open ? " · tap a price to bet" : ""}</div><div class="ps-lines">${lines.map(x => `<div class="ps-ln"><span>${esc(x[0])}</span>${pjMeter(x[1])}<b>${pjPct(x[1])}</b>${priced(x)}</div>`).join("")}</div>` : ""}
    <div class="hint">${esc(PJA.sheetNote || "")}</div>`);
}
function pjRender() {
  if (!PJA) return;
  try { PJA.header && PJA.header(); PJA.strip && PJA.strip(); } catch (e) {}
  if (TAB === "bets") { const s = document.getElementById("strip"); if (s) s.style.display = "none"; }
  pjNav();
  const b = document.body;
  [...b.classList].filter(c => c.startsWith("tab-")).forEach(c => b.classList.remove(c)); b.classList.add("tab-" + TAB);
  const v = document.getElementById("view");
  const html = ({home: pjHome, games: pjGames, players: pjPlayers, bets: bkScreen, model: () => PJA.modelHtml()}[TAB] || pjHome)();
  if (html !== window.PJ_HTML || v.dataset.tab !== TAB) { window.PJ_HTML = html; v.dataset.tab = TAB; v.innerHTML = html; }   // identical redraws leave the screen alone
  v.querySelectorAll("[data-go]").forEach(x => x.onclick = () => pjGo(x.dataset.go));
  v.querySelectorAll("[data-gogame]").forEach(x => x.onclick = () => { PJ.open.add(String(x.dataset.gogame)); TAB = "games"; pjRender();
    const c = document.querySelector(`.gc[data-gid="${CSS.escape(String(x.dataset.gogame))}"]`); if (c) window.scrollTo({top: c.getBoundingClientRect().top + scrollY - (parseInt(getComputedStyle(document.documentElement).getPropertyValue("--hdrh")) || 120) - 8}); });
  v.querySelectorAll("[data-more]").forEach(x => x.onclick = () => { const k = String(x.dataset.more); PJ.open.has(k) ? PJ.open.delete(k) : PJ.open.add(k); pjRender(); });
  v.querySelectorAll("[data-pv]").forEach(x => x.onclick = () => { const [id, k] = x.dataset.pv.split("|"); PJ.panel[id] = k; pjRender(); });
  v.querySelectorAll("[data-player]").forEach(x => x.onclick = e => { e.stopPropagation(); pjOpenPlayer(x.dataset.player); });
  v.querySelectorAll("[data-pjmk]").forEach(x => x.onclick = () => { PJ.mk = x.dataset.pjmk; PJ.n = 40; pjRender(); });
  v.querySelectorAll("[data-pjg]").forEach(x => x.onclick = () => { PJ.game = x.dataset.pjg; PJ.n = 40; pjRender(); });
  v.querySelectorAll("[data-pjmore]").forEach(x => x.onclick = () => { PJ.n += 40; pjRender(); });
  v.querySelectorAll("[data-pjsearch]").forEach(x => x.onclick = () => { PJ.searching = !PJ.searching; if (!PJ.searching) PJ.q = ""; pjRender(); const i = document.getElementById("pjq"); if (i) i.focus(); });
  const q = document.getElementById("pjq");
  if (q) q.oninput = () => { PJ.q = q.value; const pos = q.selectionStart; pjRender(); const n = document.getElementById("pjq"); if (n) { n.focus(); n.setSelectionRange(pos, pos); } };
  bkWire(v);
  if (TAB === "model" && PJA.modelWire) PJA.modelWire(pjRender);
  if (PJA.after) PJA.after(pjRender);
  const c = document.getElementById("coin"); if (c) { const h = bkPill(); if (c.dataset.h !== h) { c.dataset.h = h; c.innerHTML = h; } }
  bkBar();
  requestAnimationFrame(() => { const h = document.querySelector(".hdr"); if (h) { const hv = h.offsetHeight + "px"; if (window.PJ_HH !== hv) { window.PJ_HH = hv; document.documentElement.style.setProperty("--hdrh", hv); } } });
  const sp = document.getElementById("splash"); if (sp && !sp.classList.contains("out")) { sp.classList.add("out"); setTimeout(() => sp.remove(), 500); }
}
window.addEventListener("scroll", () => { const h = document.querySelector(".hdr"); if (h) h.classList.toggle("stuck", window.scrollY > 8); }, {passive: true});
