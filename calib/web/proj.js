// ---------- PIKT (shared by the NHL, NFL and NBA pages) ----------
// A play-coin sportsbook: game lines and player props (calib/web/book.js). Prices are set in the page from each
// league's pricing engine; nothing on screen is a projection.
// Each page sets PJA (its adapter) and calls pjRender():
//   PJA.games()      -> [{id, state: pre|live|final, time, detail, a, h, ph, lph, sa, sh, score: {a, h}, stats: [[label, value]], note}]
//                       team = {abbr, name, color, logo, sub}
//   PJA.players()    -> [{id, gid, name, team, pos, img, logo, color, meta, vals: {mk: {v, txt, chance, chanceLab, live}}}]
//   PJA.markets      -> [{k, label}]                  (Props tab, in order; k is the prop's stat)
//   PJA.panels(g)    -> [{k, label, html()}]          (only the lineup view (rink / field / court) is kept)
//   PJA.playerLines(id) -> [[label, chance, {stat, n}]]  (player sheet; the third item makes the line bettable)
//   PJA.ctx(gid)     -> {sport, game, start, open, ev: {date, home, away, id}}   (what a bet needs to be graded)
//   PJA.lines(gid)   -> {spreadLab, spread: [a, h], total: [over, under], ml: [a, h]} of bkSel selections
//   PJA.top(), PJA.kicker(), PJA.after(render)
document.body.classList.add("pj");
let PJA = null;
const PJ = {mk: null, q: "", game: "all", open: new Set(), panel: {}, n: 40};
const PJ_TABS = [["home", "Home"], ["games", "Games"], ["players", "Props"], ["bets", "My bets"]];
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
// market odds (calib/odds.py): consensus game lines across US books, DraftKings props; the page's own prices fill the gaps
let PJ_ODDS = {};
fetch("odds.json?v=" + Date.now()).then(r => r.json()).then(d => { PJ_ODDS = d || {}; if (PJA) pjRender(); }).catch(() => {});
const pjDec = a => a > 0 ? 1 + a / 100 : 1 + 100 / -a;
const pjNoVig = (a, b) => { const x = 1 / pjDec(a), y = 1 / pjDec(b); return x / (x + y); };
function pjMarket(g) {
  const L = ((PJ_ODDS.lines || {})[PJA.sport] || {}).games || [], C = pjCtx(g.id), t = C && C.start ? new Date(C.start) : null;
  const is = (full, team) => { const a = bkNm(full), b = bkNm(team.name); return !!b && (a.endsWith(b) || a === bkNm(team.abbr)); };
  return L.find(x => is(x.home, g.h) && is(x.away, g.a) && (!t || !x.t || Math.abs(new Date(x.t) - t) < 36e5 * 18)) || null;
}
// game lines with their artwork: each side carries its team's logo and colour, totals carry both logos
function pjLines(g) {
  const M = PJA.lines ? PJA.lines(g.id) : null; if (!M) return null;
  const X = pjMarket(g);
  if (X) {   // swap in the market: its line and its price
    const R = (base, line, price, p, pick) => base && price != null ? bkSel(Object.assign({}, base, {line, p, dec: Math.round(pjDec(price) * 1e4) / 1e4, pick, src: "mkt"})) : base;
    if (X.ml && M.ml) M.ml = [R(M.ml[0], null, X.ml.away, pjNoVig(X.ml.away, X.ml.home), `${g.a.abbr} to win`), R(M.ml[1], null, X.ml.home, pjNoVig(X.ml.home, X.ml.away), `${g.h.abbr} to win`)];
    if (X.spread && M.spread) { const h = X.spread.home, ph = pjNoVig(X.spread.home_price, X.spread.away_price);
      M.spread = [R(M.spread[0], -h, X.spread.away_price, 1 - ph, `${g.a.abbr} ${pjSp(-h)}`), R(M.spread[1], h, X.spread.home_price, ph, `${g.h.abbr} ${pjSp(h)}`)]; }
    if (X.total && M.total) { const l = X.total.line, po = pjNoVig(X.total.over, X.total.under);
      M.total = [R(M.total[0], l, X.total.over, po, `Over ${l}`), R(M.total[1], l, X.total.under, 1 - po, `Under ${l}`)]; }
    M.books = X.books;
  }
  const side = (x, t) => { if (x) Object.assign(x, {logo: t.logo, color: t.color}); };
  for (const k of ["spread", "ml"]) { side((M[k] || [])[0], g.a); side((M[k] || [])[1], g.h); }
  for (const x of M.total || []) if (x) x.logos = [g.a.logo, g.h.logo];
  return M;
}
const pjCtx = gid => PJA.ctx ? PJA.ctx(gid) : null;
// a player's bettable lines for one stat: [{sel, top}] nearest even money first, then shown low to high
function pjProps(p, stat, max = 3) {
  const C = pjCtx(p.gid); if (!C || !PJA.playerLines) return [];
  const L = PJA.playerLines(p.id).filter(x => x[2] && x[2].stat === stat && x[1] != null && x[1] >= 0.1 && x[1] <= 0.88);   // no lottery tickets, no −3000 locks
  return L.sort((x, y) => Math.abs(x[1] - 0.5) - Math.abs(y[1] - 0.5)).slice(0, max).sort((x, y) => x[2].n - y[2].n).map(([l, c, spec]) => ({
    top: (stat === "td" || stat === "goals") && spec.n === 1 ? "Anytime" : `${Math.ceil(spec.n)}+`,
    sel: bkSel({dec: pjPropDec(p, stat, spec.n), img: p.img, logo: p.logo, color: p.color, sport: C.sport, gid: p.gid, kind: "prop", side: "yes", line: spec.n, p: c, pick: `${p.name} ${l}`, mkt: (PJA.markets.find(m => m.k === stat) || {}).label || "Player prop",
      game: C.game, start: C.start, open: C.open, ev: C.ev, pl: {name: p.name, id: String(p.id), espn: !!C.espnIds, team: p.team, stat, n: spec.n}})}));
}
function pjPropDec(p, stat, n) {   // DraftKings (via ESPN) quotes "N+" as over N - 0.5
  const P = ((PJ_ODDS.props || {})[PJA.sport] || {}).players || {}, a = (P[bkNm(p.name)] || {})[`${stat}|${n - 0.5}`];
  return a ? Math.round(pjDec(a) * 1e4) / 1e4 : undefined;
}
function pjAv(p, cls = "") {
  return `<span class="pav ${cls}" style="--tc:${esc(p.color || "#556")}"><span>${esc(pjIni(p.name))}</span>${p.img ? `<img src="${esc(p.img)}" alt="" loading="lazy" onload="this.previousElementSibling.style.visibility='hidden'" onerror="this.remove()">` : ""}</span>`;
}
const pjMeta = p => { const g = PJA.games().find(x => String(x.id) === String(p.gid)); if (!g) return `${p.team} · ${p.pos || ""}`;
  const home = g.h.abbr === p.team; return `${p.team}${p.pos ? " · " + p.pos : ""} · ${home ? "vs" : "@"} ${home ? g.a.abbr : g.h.abbr}`; };
// a prop row: who, then up to three ladder prices
function pjPropRow(p, stat) {
  const L = pjProps(p, stat); if (!L.length) return "";
  return `<div class="pr" style="--tc:${esc(p.color || "#556")}"><button class="pr-who" data-player="${esc(p.id)}">${pjAv(p)}<span><b>${esc(p.name)}</b><i>${esc(pjMeta(p))}</i></span></button>
    <div class="pr-px" style="--n:${L.length}">${L.map(x => bkBtn(x.sel, x.top)).join("")}</div></div>`;
}
const pjPlayerRow = (p, mk) => pjPropRow(p, mk);   // pages still call this name
function pjMarkets(g) {
  if (g.state !== "pre" || !PJA.lines) return "";
  const M = pjLines(g); if (!M) return "";
  const row = (t, i) => `<span class="mk-t">${pjLogo(t)}<b>${esc(t.abbr)}</b></span>
    ${bkBtn((M.spread || [])[i], (M.spread || [])[i] ? pjSp((M.spread || [])[i].line) : "")}
    ${bkBtn((M.total || [])[i], (M.total || [])[i] ? `${i ? "U" : "O"} ${(M.total || [])[i].line}` : "")}
    ${bkBtn((M.ml || [])[i])}`;
  return `<div class="mk"><span class="mk-src">${M.books ? `<b>Market</b>${M.books} books` : "<b>Pikt</b>lines"}</span><i>${esc(M.spreadLab || "Spread")}</i><i>Total</i><i>Money</i>${row(g.a, 0)}${row(g.h, 1)}</div>`;
}
// the game card: teams (score once it starts), the three main lines, then props and the lineup view
// alternate lines: a ladder around the main spread and total, priced by the page
function pjAlt(g) {
  const M = pjLines(g), C = pjCtx(g.id); if (!M || !PJA.price || !C) return "";
  const nhl = PJA.sport === "NHL", lh = (M.spread || [])[1] ? M.spread[1].line : 0, T = (M.total || [])[0] ? M.total[0].line : null;
  const main = [...(M.spread || []), ...(M.total || [])].filter(Boolean);
  const S = (kind, side, line, t) => { const same = main.find(x => x.kind === kind && x.side === side && x.line === line); if (same) return same;
    const p = PJA.price(g.id, kind, side, line); if (p == null || p < 0.1 || p > 0.9) return null;
    const x = bkSel(Object.assign({}, C, {gid: String(g.id), kind, side, line, p, mkt: kind === "spread" ? (nhl ? "Alt puck line" : "Alt spread") : "Alt total",
      pick: kind === "spread" ? `${t.abbr} ${pjSp(line)}` : `${side === "over" ? "Over" : "Under"} ${line}`}));
    if (kind === "spread") Object.assign(x, {logo: t.logo, color: t.color}); else x.logos = [g.a.logo, g.h.logo];
    return x; };
  const hs = nhl ? [-2.5, -1.5, 1.5, 2.5] : [-6, -3, 0, 3, 6].map(d => lh + d);
  const ts = T == null ? [] : (nhl ? [-1, 0, 1] : PJA.sport === "NBA" ? [-8, -4, 0, 4, 8] : [-6, -3, 0, 3, 6]).map(d => T + d);
  const sp = hs.map(h => [S("spread", "away", -h, g.a), S("spread", "home", h, g.h)]).filter(r => r[0] || r[1]);
  const to = ts.map(l => [S("total", "over", l), S("total", "under", l)]).filter(r => r[0] || r[1]);
  const cell = (x, top) => x ? bkBtn(x, top) : `<span class="bk-px off">–</span>`;
  return `<div class="alt"><div class="sec">Alt ${esc((M.spreadLab || "Spread").toLowerCase())}</div><div class="alt-h"><span>${pjLogo(g.a)}${esc(g.a.name)}</span><span>${pjLogo(g.h)}${esc(g.h.name)}</span></div>
      ${sp.map(([a, h]) => `<div class="alt-r">${cell(a, a ? pjSp(a.line) : "")}${cell(h, h ? pjSp(h.line) : "")}</div>`).join("")}
      ${to.length ? `<div class="sec">Alt total</div><div class="alt-h"><span>Over</span><span>Under</span></div>${to.map(([o, u]) => `<div class="alt-r">${cell(o, o ? "O " + o.line : "")}${cell(u, u ? "U " + u.line : "")}</div>`).join("")}` : ""}</div>`;
}
// each team's star (the page decides who: top producer, not just the likeliest scorer), with one price
function pjStar(g, t) {
  if (g.state !== "pre") return null;
  const P = PJA.players().filter(p => String(p.gid) === String(g.id) && p.team === t.abbr);
  const R = P.map(p => { const r = PJA.star ? PJA.star(p) : {s: (p.vals[PJA.markets[0].k] || {}).v || 0, mk: PJA.markets[0].k}; return Object.assign({p}, r); })
    .filter(r => r.s > 0).sort((x, y) => y.s - x.s);
  for (const r of R) { const x = pjProps(r.p, r.mk, 1)[0] || PJA.markets.map(m => pjProps(r.p, m.k, 1)[0]).find(Boolean); if (x) return {p: r.p, x}; }
  return null;
}
const PJ_UNIT = {goals: "goals", sog: "shots", points: "pts", assists: "ast", td: "TDs", pass_yds: "pass yds", rush_yds: "rush yds", rec_yds: "rec yds", rec: "rec", pts: "pts", reb: "reb", ast: "ast", fg3: "3PM", pra: "PRA"};
function pjStarChip(g, t) {
  const S = pjStar(g, t); if (!S) return "";
  const {p, x} = S, st = x.sel.pl.stat;
  const lab = x.top === "Anytime" ? (st === "td" ? "TD" : "goal") : `${x.top} ${PJ_UNIT[st] || st}`;
  const last = p.name.split(" ").filter(w => !/^(jr\.?|sr\.?|ii|iii|iv)$/i.test(w)).slice(-1)[0];
  return `<div class="mc-st"><button class="mc-av" data-player="${esc(p.id)}" style="--tc:${esc(p.color || "#556")}">${pjAv(p)}<span>${esc(last)}</span></button>${bkBtn(x.sel, lab)}</div>`;
}
function pjGamePanels(g) {
  const P = PJA.players().filter(p => String(p.gid) === String(g.id)), out = [];
  for (const m of PJA.markets) { const rows = P.slice().sort((x, y) => ((y.vals[m.k] || {}).v || 0) - ((x.vals[m.k] || {}).v || 0)).slice(0, 6).map(p => pjPropRow(p, m.k)).join("");
    if (rows) out.push({k: "p_" + m.k, label: m.label, html: () => `<div class="prs">${rows}</div>`}); }
  for (const x of (PJA.panels ? PJA.panels(g) : []).filter(x => ["rink", "field", "court"].includes(x.k))) out.push({k: x.k, label: "Lineup", html: x.html});
  const alt = g.state === "pre" ? pjAlt(g) : "";
  if (alt) out.unshift({k: "alt", label: "Alt lines", html: () => alt});
  return out;
}
function pjGameCard(g) {
  const open = PJ.open.has(String(g.id)), P = open ? pjGamePanels(g) : [], pre = g.state === "pre";
  let body = "";
  if (open && P.length) { const k = PJ.panel[g.id] && P.some(x => x.k === PJ.panel[g.id]) ? PJ.panel[g.id] : P[0].k;
    body = `<div class="xpanel"><div class="strip xtabs">${P.map(x => `<button class="chip ${x.k === k ? "on" : ""}" data-pv="${esc(g.id)}|${x.k}">${x.label}</button>`).join("")}</div>
      <div class="xbody">${P.find(x => x.k === k).html()}</div></div>`; }
  const side = (t, k) => { const sc = g.score ? g.score[k] : null, other = g.score ? g.score[k === "h" ? "a" : "h"] : null;
    return `<div class="mc-s ${k} ${g.state === "final" && sc < other ? "lose" : ""}"><span class="mc-lg">${pjLogo(t)}</span><b>${esc(t.name)}</b><i>${t.sub || (k === "h" ? "Home" : "Away")}</i>${pjStarChip(g, t)}</div>`; };
  const mid = pre ? `<div class="mc-mid"><span class="mc-vs">VS</span>${pjCountdown(g)}</div>`
    : `<div class="mc-mid sc"><b>${g.score ? g.score.a : 0}<i>–</i>${g.score ? g.score.h : 0}</b><span>${g.state === "live" ? `<b class="st-live">Live</b> ${esc(g.detail || "")}` : "Final"}</span></div>`;
  const mk = pjMarkets(g), info = PJA.info ? PJA.info(g.id) : [];
  return `<article class="gc mc ${g.state === "live" ? "islive" : ""}" data-gid="${esc(g.id)}" style="--ca:${esc(g.a.color || "#345")};--ch:${esc(g.h.color || "#543")}">
      <div class="mc-hero">${g.a.logo ? `<img class="mc-wm a" src="${esc(g.a.logo)}" alt="" onerror="this.remove()">` : ""}${g.h.logo ? `<img class="mc-wm h" src="${esc(g.h.logo)}" alt="" onerror="this.remove()">` : ""}
        <div class="mc-top"><span class="mc-lgu">${esc(PJA.sport)}</span><span class="mc-time">${pre ? esc(g.time || "") : ""}</span>${g.note ? `<span class="mc-note">${g.note}</span>` : ""}</div>
        <div class="mc-row">${side(g.a, "a")}${mid}${side(g.h, "h")}</div>
        ${info.length ? `<div class="mc-info">${info.map(x => `<span>${esc(x)}</span>`).join("")}</div>` : ""}</div>
      ${mk || (pre ? "" : `<div class="gc-lock">${g.state === "live" ? "Lines are closed while the game is on" : "Final · bets graded"}</div>`)}
    ${body}<button class="more" data-more="${esc(g.id)}">${open ? "Hide" : (pre ? "Alt lines · " : "") + "Player props" + (PJA.panels && PJA.panels(g).some(x => ["rink", "field", "court"].includes(x.k)) ? " · lineup" : "")}<span class="chev ${open ? "up" : ""}">›</span></button></article>`;
}
// Home: a game row with both moneylines
function pjGameRow(g) {
  const M = g.state === "pre" ? pjLines(g) : null;
  const side = (t, i, sc, other) => `<div class="gr-t" style="--tm:${esc(t.color || "transparent")}">${pjLogo(t)}<b>${esc(t.name)}</b>${M ? bkBtn(M.ml[i]) : g.state === "pre" ? "" : `<strong class="${g.state === "final" && sc < other ? "lose" : ""}">${sc ?? 0}</strong>`}</div>`;
  return `<div class="gr" data-gogame="${esc(g.id)}"><div class="gr-st">${pjStatus(g)}<span class="chev">›</span></div>
    ${side(g.a, 0, g.score && g.score.a, g.score && g.score.h)}${side(g.h, 1, g.score && g.score.h, g.score && g.score.a)}</div>`;
}
const pjEmpty = (t, s) => `<div class="empty"><div class="t">${esc(t)}</div><div class="note">${esc(s)}</div></div>`;

// ---- screens ----
// ---- Home pieces ----
const pjOpenGames = () => PJA.games().filter(g => g.state === "pre" && PJA.lines && PJA.lines(g.id));
function pjCountdown(g) {
  const C = pjCtx(g.id), t = C && C.start ? new Date(C.start) - Date.now() : null;
  if (t == null || t <= 0) return `<b class="cd soft">${esc(g.time || "")}</b>`;
  const h = Math.floor(t / 36e5), m = Math.floor(t % 36e5 / 6e4);
  return h >= 24 ? `<b class="cd soft">${esc(String(g.time || "").split(" ")[0])}</b>` : `<b class="cd">${h ? h + "h " : ""}${m}m</b>`;
}
// featured games: big matchup cards in team colours, moneylines and the total right on the card
function pjFeatured(G) {
  return `<div class="fgs">${G.slice(0, 6).map(g => { const M = pjLines(g), T = (M.total || [])[0];
    const tm = t => `<div class="fg-tm"><span class="fg-lg">${pjLogo(t)}</span><b>${esc(t.name)}</b></div>`;
    return `<article class="fg" style="--ca:${esc(g.a.color || "#345")};--ch:${esc(g.h.color || "#543")}">
      <div class="fg-top"><span class="fg-lg2">${esc(PJA.sport)}</span><span class="fg-cd">${g.time ? `<i>${esc(g.time)}</i>` : ""}${pjCountdown(g)}</span></div>
      <div class="fg-mid">${tm(g.a)}<span class="fg-at">@</span>${tm(g.h)}</div>
      <div class="fg-px">${bkBtn(M.ml[0], g.a.abbr)}${bkBtn(M.ml[1], g.h.abbr)}${T ? bkBtn(M.total[0], "O " + T.line) + bkBtn(M.total[1], "U " + T.line) : ""}</div>
      <button class="fg-all" data-gogame="${esc(g.id)}">All markets<span class="chev">›</span></button></article>`; }).join("")}</div>`;
}
// Pikt Boosts: three of tonight's prices with 25% more profit, refreshed every slate
const PJ_BOOST = 1.25;
function pjBoosts(G) {
  const out = [], boost = (s, why) => s && s.open && out.length < 3 && !out.some(x => x.gid === s.gid && x.kind === s.kind) &&
    out.push(bkSel(Object.assign({}, s, {boost: true, was: s.dec, dec: Math.round((1 + (s.dec - 1) * PJ_BOOST) * 100) / 100, mkt: "Pikt Boost · " + s.mkt, why})));
  const top = (PJA.top ? PJA.top() : []).map(({p, mk}) => pjProps(p, mk, 1)[0]).filter(Boolean);
  if (top[0]) boost(top[0].sel, "Most popular prop");
  const close = G.slice().sort((x, y) => Math.abs(x.ph - 0.5) - Math.abs(y.ph - 0.5))[0];
  if (close) { const M = pjLines(close); boost(close.ph < 0.5 ? M.ml[1] : M.ml[0], "Coin-flip game"); }
  const hi = G.slice().sort((x, y) => (y.total || 0) - (x.total || 0))[0];
  if (hi) { const M = pjLines(hi); boost((M.total || [])[0], "Highest-scoring matchup"); }
  if (top[1]) boost(top[1].sel, "Fan favourite");
  return out;
}
function pjBoostsHtml(B) {
  return `<div class="bst">${B.map(s => `<div class="bs"><span class="bs-k">⚡ Boost · ${esc(s.why)}</span><b class="bs-p">${esc(s.pick)}</b><i class="bs-g">${esc(s.game)}</i>
    <div class="bs-o"><s>${bkAm(s.was)}</s>${bkBtn(s)}</div></div>`).join("")}</div>`;
}
// parlays of the day: one tap fills the slip
const PJ_POD = {};
function pjParlays(G) {
  const fav = G.map(g => { const M = pjLines(g), s = g.ph >= 0.5 ? M.ml[1] : M.ml[0]; return s; }).filter(s => s && s.p >= 0.55 && s.p <= 0.75).sort((x, y) => y.p - x.p).slice(0, 3);
  const props = [], seen = new Set();
  for (const {p, mk} of (PJA.top ? PJA.top() : [])) { const x = pjProps(p, mk, 1)[0]; if (x && !seen.has(String(p.gid)) && x.sel.p >= 0.4) { seen.add(String(p.gid)); props.push(x.sel); } if (props.length >= 3) break; }
  const cards = [];
  if (fav.length >= 2) cards.push(["fav", "Chalk stack", "Tonight's strongest favourites", fav]);
  if (props.length >= 2) cards.push(["props", "Prop power", "The board's most popular props", props]);
  for (const c of cards) PJ_POD[c[0]] = c[3];
  return cards.length ? `<div class="pods">${cards.map(([k, t, sub, L]) => `<div class="pod"><div class="pod-h"><span><b>${t}</b><i>${sub}</i></span><em>${bkAm(L.reduce((d, x) => d * x.dec, 1))}</em></div>
    ${L.map((x, i) => `<div class="pod-l"><span class="pod-n">${i + 1}</span><span><b>${esc(x.pick)}</b><i>${esc(x.game)}</i></span><span class="pod-o">${bkAm(x.dec)}</span></div>`).join("")}
    <button class="pod-go" data-pod="${k}">Add ${L.length}-leg parlay</button></div>`).join("")}</div>` : "";
}
function pjWhy() {
  if (BKS.bets.length || BKS.why) return "";
  return `<section class="why"><button class="why-x" data-why="1" aria-label="Dismiss">✕</button><b class="why-t">Welcome to Pikt</b><span class="why-s">A sportsbook that's actually fun. No deposits. Ever.</span>
    <div class="why-g"><div><em>🪙</em><b>1,000 coins free</b><i>Plus a daily drop that grows with your streak</i></div><div><em>⚡</em><b>Daily boosts</b><i>Juiced prices on tonight's best spots</i></div>
      <div><em>🧩</em><b>One-tap parlays</b><i>Built for you every slate</i></div><div><em>🏆</em><b>Missions & levels</b><i>Earn coins just for playing</i></div></div></section>`;
}
function pjTicker(live) {
  if (!live.length) return "";
  return `<div class="tick">${live.map(g => `<button class="tk" data-gogame="${esc(g.id)}"><b class="st-live">Live</b><span>${esc(g.a.abbr)} <b>${g.score ? g.score.a : 0}</b></span><span>${esc(g.h.abbr)} <b>${g.score ? g.score.h : 0}</b></span><i>${esc(g.detail || "")}</i></button>`).join("")}</div>`;
}
function pjHome() {
  const G = PJA.games(), live = G.filter(g => g.state === "live"), O = pjOpenGames();
  const head = pjTicker(live) + bkWalletHtml() + pjWhy();
  if (!G.length) return head + pjEmpty("No games on the board", "Lines open once the next slate is set.");
  const top = (PJA.top ? PJA.top() : []).map(({p, mk}) => { const x = pjProps(p, mk, 1)[0]; return x ? {p, mk, x} : null; }).filter(Boolean).slice(0, 8);
  const cards = top.map(({p, mk, x}) => { const m = PJA.markets.find(y => y.k === mk);
    return `<div class="tp" style="--tc:${esc(p.color || "#556")}">${p.logo ? `<img class="tp-wm" src="${esc(p.logo)}" alt="" onerror="this.remove()">` : ""}${p.img ? `<img class="tp-cut" src="${esc(p.img)}" alt="" onerror="this.remove()">` : ""}
      <button class="tp-hit" data-player="${esc(p.id)}" aria-label="${esc(p.name)}"></button>
      <span class="tp-tag">${esc(m.label)}</span><b class="tp-n"><small>${esc(p.name.split(" ")[0])}</small>${esc(p.name.split(" ").slice(1).join(" ") || p.name)}</b><i class="tp-m">${esc(pjMeta(p))}</i>
      <span class="tp-v">${bkBtn(x.sel, x.top === "Anytime" ? (mk === "td" ? "Anytime TD" : "Anytime goal") : `${x.top} ${m.label.toLowerCase()}`)}</span></div>`; }).join("");
  const B = O.length ? pjBoosts(O) : [];
  return head
    + (O.length ? `<div class="hd"><b>Featured</b><button data-go="games">All games ›</button></div>${pjFeatured(O)}` : "")
    + (B.length ? `<div class="hd"><b>Pikt Boosts</b><span class="hd-s">+25% profit · today only</span></div>${pjBoostsHtml(B)}` : "")
    + (O.length ? (x => x ? `<div class="hd"><b>Quick parlays</b><span class="hd-s">One tap to load</span></div>${x}` : "")(pjParlays(O)) : "")
    + `<div class="hd"><b>Daily missions</b><button data-go="bets">Wallet ›</button></div>${bkMissionsHtml()}`
    + (cards ? `<div class="hd"><b>Popular props</b><button data-go="players">All props ›</button></div><div class="tps">${cards}</div>` : "")
    + `<div class="hd"><b>${O.length ? "Moneylines" : "Games"}</b><button data-go="games">All lines ›</button></div><div class="gl">${G.filter(g => g.state !== "live").map(pjGameRow).join("")}</div>`;
}
function pjGames() {
  const G = PJA.games();
  if (!G.length) return pjEmpty("No games on the board", "Check back on the next game day.");
  return (PJA.gamesHead ? PJA.gamesHead() : "") + G.map(pjGameCard).join("");
}
function pjPlayers() {
  const all = PJA.players();
  if (!PJ.mk || !PJA.markets.some(m => m.k === PJ.mk)) PJ.mk = PJA.markets[0].k;
  const m = PJA.markets.find(x => x.k === PJ.mk), q = PJ.q.trim().toLowerCase(), G = PJA.games();
  const L = all.filter(p => (PJ.game === "all" || String(p.gid) === PJ.game) && (!q || p.name.toLowerCase().includes(q) || String(p.team).toLowerCase() === q))
    .sort((x, y) => ((y.vals[m.k] || {}).v || 0) - ((x.vals[m.k] || {}).v || 0));
  const rows = []; for (const p of L) { if (rows.length >= PJ.n) break; const r = pjPropRow(p, m.k); if (r) rows.push(r); }
  const tabs = `<div class="strip pj-mk">${PJA.markets.map(x => `<button class="chip ${x.k === m.k ? "on" : ""}" data-pjmk="${x.k}">${x.label}</button>`).join("")}</div>`;
  const chips = `<div class="strip pj-strip"><button class="chip ${PJ.q ? "on" : ""}" data-pjsearch="1" aria-label="Search">${pjIc("search")}</button><button class="chip ${PJ.game === "all" ? "on" : ""}" data-pjg="all">All games</button>${G.filter(g => g.state === "pre").map(g => `<button class="chip ${PJ.game === String(g.id) ? "on" : ""}" data-pjg="${esc(g.id)}">${pjLogo(g.a)}${pjLogo(g.h)}${esc(g.a.abbr)} @ ${esc(g.h.abbr)}</button>`).join("")}</div>
    ${PJ.searching || PJ.q ? `<input class="search" id="pjq" placeholder="Search a player or team" value="${esc(PJ.q)}" autocomplete="off">` : ""}`;
  return tabs + chips + `<div class="list prs">${rows.join("") || `<div class="bk-empty">No ${esc(m.label.toLowerCase())} props open right now.</div>`}</div>
    ${rows.length >= PJ.n ? `<button class="gmore" data-pjmore="1">Show more</button>` : ""}`;
}
function pjOpenPlayer(id) {
  const p = PJA.players().find(x => String(x.id) === String(id)); if (!p) return;
  const groups = PJA.markets.map(m => { const L = pjProps(p, m.k, 6); return L.length ? `<div class="sec">${esc(m.label)}</div><div class="ps-px">${L.map(x => bkBtn(x.sel, x.top)).join("")}</div>` : ""; }).join("");
  pjSheet(`<div class="ps-h" style="--tc:${esc(p.color || "#556")}">${pjAv(p, "big")}
      <div><div class="sh-t">${esc(p.name)}</div><div class="sh-s">${esc(pjMeta(p))}</div></div>${p.logo ? `<img class="ps-lg" src="${esc(p.logo)}" alt="" onerror="this.remove()">` : ""}</div>
    ${groups || `<div class="bk-empty">No props open for ${esc(p.name)} right now.</div>`}`);
}
function pjRender() {
  if (!PJA) return;
  if (!PJ_TABS.some(t => t[0] === TAB)) TAB = "home";
  try { PJA.header && PJA.header(); PJA.strip && PJA.strip(); } catch (e) {}
  if (TAB === "bets" || TAB === "players") { const s = document.getElementById("strip"); if (s) s.style.display = "none"; }
  pjNav();
  const b = document.body;
  [...b.classList].filter(c => c.startsWith("tab-")).forEach(c => b.classList.remove(c)); b.classList.add("tab-" + TAB);
  const v = document.getElementById("view");
  const html = ({home: pjHome, games: pjGames, players: pjPlayers, bets: bkScreen}[TAB] || pjHome)();
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
  v.querySelectorAll("[data-pod]").forEach(x => x.onclick = () => bkAddParlay(PJ_POD[x.dataset.pod]));
  v.querySelectorAll("[data-why]").forEach(x => x.onclick = () => { BKS.why = 1; bkSave(); pjRender(); });
  bkWire(v);
  if (PJA.after) PJA.after(pjRender);
  const c = document.getElementById("coin"); if (c) { const h = bkPill(); if (c.dataset.h !== h) { c.dataset.h = h; c.innerHTML = h; } }
  bkBar();
  requestAnimationFrame(() => { const h = document.querySelector(".hdr"); if (h) { const hv = h.offsetHeight + "px"; if (window.PJ_HH !== hv) { window.PJ_HH = hv; document.documentElement.style.setProperty("--hdrh", hv); } } });
  const sp = document.getElementById("splash"); if (sp && !sp.classList.contains("out")) { sp.classList.add("out"); setTimeout(() => sp.remove(), 500); }
}
window.addEventListener("scroll", () => { const h = document.querySelector(".hdr"); if (h) h.classList.toggle("stuck", window.scrollY > 8); }, {passive: true});
setInterval(() => { if (TAB === "home" && !document.getElementById("sheet").classList.contains("open")) pjRender(); }, 60e3);   // countdowns
