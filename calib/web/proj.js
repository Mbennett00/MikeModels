// ---------- PIKT (shared by the NHL, NFL and NBA pages) ----------
// Projections and sims: the model's read on every game and player, shown next to the real market (DraftKings + FanDuel
// lines and props from SharpAPI, read-only) with its chance for each side and the prices where it sees an edge.
// Each page sets PJA (its adapter) and calls pjRender():
//   PJA.games()      -> [{id, state: pre|live|final, time, detail, a, h, ph, lph, sa, sh, score: {a, h}, stats: [[label, value]], note}]
//                       team = {abbr, name, color, logo, sub}
//   PJA.players()    -> [{id, gid, name, team, pos, img, logo, color, meta, vals: {mk: {v, txt, chance, chanceLab, live}}}]
//   PJA.markets      -> [{k, label}]                  (Props tab, in order; k is the prop's stat)
//   PJA.panels(g)    -> [{k, label, html()}]          (only the lineup view (rink / field / court) is kept)
//   PJA.playerLines(id) -> [[label, chance, {stat, n}]]  (player sheet)
//   PJA.ctx(gid)     -> {sport, game, start, open, ev: {date, home, away, id}}
//   PJA.lines(gid)   -> {spreadLab, spread: [a, h], total: [over, under], ml: [a, h]} of bkSel selections
//   PJA.top(), PJA.kicker(), PJA.after(render)
document.body.classList.add("pj");
let PJA = null;
const PJ = {mk: null, q: "", game: "all", open: new Set(), panel: {}, n: 40};
const PJ_TABS = [["home", "Home"], ["games", "Games"], ["players", "Players"], ["model", "Model"]];
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

// ---- shell: docked tab bar, sheet ----
(() => {
  const sub = document.getElementById("sub"), hb2 = document.querySelector(".hb2");
  if (sub && hb2) hb2.insertBefore(sub, hb2.querySelector(".iconbtn"));
})();
function pjNav() {
  const el = document.getElementById("nav"); if (!el) return;
  const html = PJ_TABS.map(([k, n]) => `<button class="${TAB === k ? "on" : ""}" data-k="${k}">${pjIc(k)}<span>${n}</span></button>`).join("");
  el.style.setProperty("--n", PJ_TABS.length);
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
}
function closeSheet() { document.getElementById("scrim").classList.remove("open"); document.getElementById("sheet").classList.remove("open"); }

// ---- pieces ----
function pjMeter(p, cls = "") { return `<span class="pj-meter ${cls}"><i style="width:${Math.max(2, Math.min(100, Math.round(100 * (p || 0))))}%"></i></span>`; }
function pjStatus(g) {
  return g.state === "live" ? `<b class="st-live">Live</b><span>${esc(g.detail || "")}</span>` : g.state === "final" ? `<b class="st-fin">Final</b>` : `<span class="st-time">${esc(g.time || "")}</span>`;
}
// market odds (calib/odds.py, from SharpAPI): DraftKings + FanDuel game lines and props; the page's own prices fill the gaps
let PJ_ODDS = {};
fetch("odds.json?v=" + Date.now()).then(r => r.json()).then(d => { PJ_ODDS = d || {}; if (PJA) pjRender(); }).catch(() => {});
const pjDec = a => a > 0 ? 1 + a / 100 : 1 + 100 / -a;
const pjNoVig = (a, b) => { const x = 1 / pjDec(a), y = 1 / pjDec(b); return x / (x + y); };
function pjMarket(g) {
  const L = ((PJ_ODDS.lines || {})[PJA.sport] || {}).games || [], C = pjCtx(g.id), t = C && C.start ? new Date(C.start) : null;
  const is = (full, team) => { const a = bkNm(full), b = bkNm(team.name); return !!b && (a.endsWith(b) || a === bkNm(team.abbr)); };
  return L.find(x => x.gid && x.gid === String(g.id)) || L.find(x => !x.gid && is(x.home, g.h) && is(x.away, g.a) && (!t || !x.t || Math.abs(new Date(x.t) - t) < 36e5 * 18)) || null;
}
// redraw unless the user is typing or has a sheet open
function pjRefresh() { const ae = document.activeElement, sh = document.getElementById("sheet");
  if ((ae && (ae.tagName === "INPUT" || ae.tagName === "SELECT")) || (sh && sh.classList.contains("open"))) return; pjRender(); }
// game lines with their artwork: each side carries its team's logo and colour, totals carry both logos
function pjLines(g) {   // pre-game only: lines close at the start
  const X = pjMarket(g), M = PJA.lines && g.state === "pre" ? PJA.lines(g.id) : null;
  if (!M) return null;
  if (X) {   // swap in the market: its line and its price
    const R = (base, line, price, p, pick) => base && price != null ? bkSel(Object.assign({}, base, {line, p, dec: Math.round(pjDec(price) * 1e4) / 1e4, pick, src: "mkt"})) : base;
    if (M.ml && X.ml) M.ml = [R(M.ml[0], null, X.ml.away, pjNoVig(X.ml.away, X.ml.home), `${g.a.abbr} to win`), R(M.ml[1], null, X.ml.home, pjNoVig(X.ml.home, X.ml.away), `${g.h.abbr} to win`)];
    if (M.spread && X.spread) { const h = X.spread.home, ph = pjNoVig(X.spread.home_price, X.spread.away_price);
      M.spread = [R(M.spread[0], -h, X.spread.away_price, 1 - ph, `${g.a.abbr} ${pjSp(-h)}`), R(M.spread[1], h, X.spread.home_price, ph, `${g.h.abbr} ${pjSp(h)}`)]; }
    if (M.total && X.total) { const l = X.total.line, po = pjNoVig(X.total.over, X.total.under);
      M.total = [R(M.total[0], l, X.total.over, po, `Over ${l}`), R(M.total[1], l, X.total.under, 1 - po, `Under ${l}`)]; }
    M.books = "DraftKings + FanDuel";
  }
  const side = (x, t) => { if (x) Object.assign(x, {logo: t.logo, color: t.color}); };
  for (const k of ["spread", "ml"]) { side((M[k] || [])[0], g.a); side((M[k] || [])[1], g.h); }
  for (const x of M.total || []) if (x) x.logos = [g.a.logo, g.h.logo];
  return M;
}
const pjCtx = gid => PJA.ctx ? PJA.ctx(gid) : null;
// a player's bettable lines for one stat: [{sel, top}] nearest even money first, then shown low to high
const PJ_PLAB = {goals: "goals", sog: "shots", points: "points", assists: "assists", td: "TDs", pass_yds: "pass yds", rush_yds: "rush yds", rec_yds: "rec yds", rec: "catches",
  pts: "points", reb: "rebounds", ast: "assists", fg3: "threes", pra: "PRA"};
const PJ_YES = {goals: "Scores a goal", td: "Anytime TD", dd: "Double-double", trip: "Triple-double"};   // yes / no props
const pjPropLab = (stat, n) => PJ_YES[stat] && n === 1 ? PJ_YES[stat] : `${n}+ ${PJ_PLAB[stat] || stat}`;
const pjMktProps = () => { const P = ((PJ_ODDS.props || {})[PJA.sport] || {}).players; return P && Object.keys(P).length ? P : null; };
// The books and our pages don't always spell a player the same way ("Alex Wennberg" / "Alexander Wennberg", "Nick" /
// "Nicholas", "Yegor" / "Egor"). A player's props are found by his exact name first, then by a known first-name variant
// with the same last name, or without middle names. No fuzzy matching: "Josh Manson" must never find "Josh Anderson".
const PJ_FIRST = [["alex", "alexander", "alexandre", "aleksander", "alexandr"], ["nick", "nicholas", "nicolas", "nikolas"], ["mitch", "mitchell"],
  ["matt", "matthew", "mathew"], ["zach", "zachary", "zack", "zachery"], ["josh", "joshua"], ["jake", "jacob", "jakob"], ["mike", "michael"],
  ["chris", "christopher", "kristopher"], ["will", "william"], ["ben", "benjamin"], ["sam", "samuel"], ["tom", "thomas", "tommy"],
  ["dan", "daniel", "danny"], ["dave", "david"], ["jon", "jonathan"], ["tony", "anthony"], ["joe", "joseph", "joey"], ["nate", "nathan", "nathaniel"],
  ["pat", "patrick"], ["rob", "robert", "robbie", "bobby"], ["cam", "cameron"], ["max", "maxim", "maxime", "maximilian"], ["gabe", "gabriel"],
  ["ken", "kenny", "kenneth"], ["greg", "gregory"], ["jeff", "jeffrey"], ["steve", "steven", "stephen"], ["tim", "timothy"], ["andy", "andrew"],
  ["yegor", "egor"], ["evgeny", "evgeni", "evgenii", "yevgeni", "yevgeny"], ["nikolai", "nikolay", "nicolai"], ["dmitri", "dmitry", "dmitrii"],
  ["sergei", "sergey"], ["ilya", "ilia"], ["vlad", "vladislav", "vladimir"], ["fred", "frederick", "frederik"], ["ed", "edward", "eddie"],
  ["herb", "herbert"], ["cj", "c j"], ["tj", "t j"], ["jj", "j j"]];
const PJ_FIRST_OF = {}; for (const G of PJ_FIRST) for (const n of G) PJ_FIRST_OF[n.replace(/ /g, "")] = G.map(x => x.replace(/ /g, ""));
function pjPropKey(MP, name) {
  const k = bkNm(name); if (MP[k]) return k;
  const T = String(name || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/\b(jr|sr|ii|iii|iv)\b\.?/g, "").replace(/[^a-z\s-]/g, "").split(/\s+/).filter(Boolean);
  if (T.length < 2) return k;
  const last = T.slice(1).join(""), lastOnly = T[T.length - 1];
  for (const f of PJ_FIRST_OF[T[0]] || []) { if (MP[f + last]) return f + last; if (MP[f + lastOnly]) return f + lastOnly; }
  return MP[T[0] + lastOnly] ? T[0] + lastOnly : k;   // middle names dropped
}
// a ladder has to make sense: each higher rung ("3+" after "2+") is less likely, so its price is longer. A rung that
// breaks the order is a misread or stale price and is dropped rather than shown (or flagged as an edge).
function pjLadder(L) {   // walked out from the rung nearest even money, so one bad rung can't take the good ones with it
  L = L.filter(r => !(r[2].fair > 0 && r[2].fair < 1) || Math.abs(r[1] - r[2].fair) <= 0.12)   // price and its fair chance must agree
    .sort((x, y) => x[2].n - y[2].n);
  if (L.length < 2) return L;
  const c = r => r[1];   // the slope is judged on the prices, the thing actually bet
  let i = 0; L.forEach((r, j) => { if (Math.abs(c(r) - 0.5) < Math.abs(c(L[i]) - 0.5)) i = j; });
  const out = [L[i]]; let last = c(L[i]);
  for (const r of L.slice(i + 1)) if (c(r) < last - 0.005) { out.push(r); last = c(r); }
  last = c(L[i]);
  for (const r of L.slice(0, i).reverse()) if (c(r) > last + 0.005) { out.unshift(r); last = c(r); }
  return out;
}
// a player's bettable lines for one stat: [{sel, top}], nearest even money first, then shown low to high.
// A player is offered the books' own rungs at their prices (DraftKings, FanDuel where DraftKings has none); no made-up props.
function pjProps(p, stat, max = 3) {
  const C = pjCtx(p.gid); if (!C) return [];
  const MP = pjMktProps();
  let L;
  const PO = (PJ_ODDS.props || {})[PJA.sport] || {}, nk = MP ? pjPropKey(MP, p.name) : bkNm(p.name), BK = (PO.bk || {})[nk] || {}, FR = (PO.fair || {})[nk] || {};
  if (MP) L = pjLadder(Object.entries(MP[nk] || {}).filter(([k]) => k.split("|")[0] === stat)
    .map(([k, a]) => { const n = +k.split("|")[1] + 0.5; return [pjPropLab(stat, n), 1 / pjDec(a), {stat, n, fd: BK[k] === "FD", fair: FR[k]}, a]; }));
  else return [];   // no made-up props: a league's props open when the books post them
  L = L.filter(x => x[1] != null && x[1] >= 0.1 && x[1] <= 0.9);   // no lottery tickets, no −1000 locks
  return L.sort((x, y) => Math.abs(x[1] - 0.5) - Math.abs(y[1] - 0.5)).slice(0, max).sort((x, y) => x[2].n - y[2].n).map(([l, c, spec, a]) => ({
    top: (spec.n === 1 && (stat === "td" || stat === "goals") ? "Anytime" : spec.n === 1 && PJ_YES[stat] ? "Yes" : `${Math.ceil(spec.n)}+`),
    sel: bkSel({dec: a ? Math.round(pjDec(a) * 1e4) / 1e4 : undefined, src: a ? (spec.fd ? "fd" : "dk") : undefined, fair: spec.fair, book: spec.fd ? "FanDuel" : "DraftKings", img: p.img, logo: p.logo, color: p.color, sport: C.sport, gid: p.gid, kind: "prop", side: "yes", line: spec.n,
      p: c, pick: `${p.name} ${l}`, mkt: (PJA.markets.find(m => m.k === stat) || {}).label || "Player prop",
      game: C.game, start: C.start, open: C.open, ev: C.ev, pl: {name: p.name, id: String(p.id), espn: !!C.espnIds, team: p.team, stat, n: spec.n}})}));
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
// ---------- model vs market ----------
// Every market price (consensus game lines, DraftKings props) is shown with the model's chance for that side; when the
// model's chance beats the price by PJ_EDGE or more in expected value, the cell is marked as an edge.
const PJ_EDGE = 0.03;
const pjFair = p => p == null || !isFinite(p) ? "–" : bkAm(1 / Math.min(0.99, Math.max(0.01, p)));
const pjIsMkt = x => x && (x.src === "mkt" || x.src === "dk" || x.src === "fd");
function pjModelP(g, x) { if (!x) return null;
  if (x.live) return x.kind === "ml" && g.lph != null ? (x.side === "home" ? g.lph : 1 - g.lph) : null;   // in play the model only reads the winner
  if (x.kind === "ml") return x.side === "home" ? g.ph : 1 - g.ph; return PJA.price ? PJA.price(g.id, x.kind, x.side, x.line) : null; }
// The edge reading: the model's chance is blended half and half with the market's fair chance (two-sided lines have
// their vig removed; one-sided props lose a typical 6% hold), and a price only counts as an edge when that blended
// chance beats it by PJ_EDGE. A model that disagrees with the market by more than 25 points is reading something the
// market isn't (a misread price, late news): no edge is claimed there.
const PJ_W = 0.5, PJ_GAP = 0.25;
// a prop's fair chance: DraftKings + FanDuel with the vig out (SharpAPI, both sides where posted), else its own price less a typical hold
// (one-sided hold: ~5% near even money rising to ~25% on long shots, as calib/sharp.py hold1)
const pjHold1 = q => 1.05 + 0.2 * Math.max(0, 0.5 - q) / 0.5;
const pjMktFair = x => !x || x.p == null ? null : x.src === "dk" || x.src === "fd" ? (x.fair > 0 && x.fair < 1 ? x.fair : Math.min(0.99, (1 / x.dec) / pjHold1(1 / x.dec))) : x.p;
// Guard rails, so a misread price can never pass for an edge: the price has to agree with its own fair chance (a
// price's implied chance sits a little above fair, by the hold, never 12+ points away), and an expected return past
// PJ_EVMAX is a data error, not a bet.
// The model's disagreement is also judged in odds terms (PJ_LGAP, log-odds): 22% against a 12% market is the model
// nearly doubling the book's chance on a long shot, a model miss far more often than an edge.
const PJ_EVMAX = 0.3, PJ_LGAP = 0.6, pjLogit = q => Math.log(q / (1 - q));
function pjEV(x, mp) {
  if (!pjIsMkt(x) || mp == null || !isFinite(mp) || mp <= 0 || mp >= 1) return null;
  const pm = pjMktFair(x); if (pm == null || pm <= 0 || pm >= 1) return null;
  if (Math.abs(mp - pm) > PJ_GAP || Math.abs(pjLogit(mp) - pjLogit(pm)) > PJ_LGAP || Math.abs(1 / x.dec - pm) > 0.12) return null;
  const ev = (PJ_W * mp + (1 - PJ_W) * pm) * x.dec - 1;
  return ev > PJ_EVMAX ? null : ev;
}
const pjEvTxt = ev => `${ev >= 0 ? "+" : "−"}${Math.abs(100 * ev).toFixed(1)}%`;
// a bettable price: the market's odds (the model's own price where the market has none), with the model's chance under it
function pjCell(x, top, mp) {
  if (!x || x.p == null || !isFinite(x.dec)) return `<span class="px off">–</span>`;
  const ev = pjEV(x, mp), hot = !x.live && ev != null && ev >= PJ_EDGE, t = top ? `<i>${esc(top)}</i>` : "";   // edges are a pre-game read
  if (!x.open) return `<span class="px off">${t}<b>🔒</b></span>`;
  const mv = x.mv > 0 ? "mv-up" : x.mv < 0 ? "mv-dn" : "";   // the price just moved: longer odds flash green, shorter red
  return `<span class="px ${hot ? "edge" : ""} ${x.src === "fd" ? "fd" : ""} ${pjIsMkt(x) ? "" : "fair"}">${t}<b>${bkAm(x.dec)}</b><em>${hot ? pjEvTxt(ev) : mp != null ? "Model " + pjPct(mp) : ""}</em></span>`;
}
// a game's six market sides with the model's view of each
function pjGameEdges(g) {
  if (g.state !== "pre") return [];
  const M = pjLines(g); if (!M) return [];
  return [...(M.spread || []), ...(M.total || []), ...(M.ml || [])].filter(pjIsMkt).map(x => { const mp = pjModelP(g, x); return {x, mp, ev: pjEV(x, mp), g}; }).filter(e => e.ev != null);
}
// a player's DraftKings lines with the model's chance at each
function pjPropEdges(p, stat) {
  return pjProps(p, stat, 8).map(({sel, top}) => { const mp = PJA.propP ? PJA.propP(p.id, stat, sel.pl.n - 0.5) : null; return {x: sel, top, mp, ev: pjEV(sel, mp), p}; });
}
function pjAllEdges() {
  const out = [];
  for (const g of PJA.games()) out.push(...pjGameEdges(g));
  for (const p of PJA.players()) for (const m of PJA.markets) out.push(...pjPropEdges(p, m.k));
  return out.filter(e => e.ev != null && e.ev >= PJ_EDGE && e.mp > 0.05).sort((a, b) => b.ev - a.ev);
}
function pjEdgeRow(e) {
  const tap = e.p ? `data-player="${esc(e.p.id)}"` : `data-gogame="${esc(e.g.id)}"`;
  return `<div class="er" ${tap}>${bkArt(e.x, "sm")}<span class="er-t"><b>${esc(e.x.pick)}</b><i><em class="er-ev">${pjEvTxt(e.ev)}</em>${esc(e.x.game)}</i></span>${bkBtn(e.x)}</div>`;
}
function pjMarkets(g) {
  if (g.state !== "pre" && g.state !== "live") return "";
  const M = pjLines(g); if (!M) return "";
  const row = (t, i) => `<span class="mk-t">${pjLogo(t)}<b>${esc(t.abbr)}</b></span>
    ${pjCell((M.spread || [])[i], (M.spread || [])[i] ? pjSp(M.spread[i].line) : "", pjModelP(g, (M.spread || [])[i]))}
    ${pjCell((M.total || [])[i], (M.total || [])[i] ? `${i ? "U" : "O"} ${M.total[i].line}` : "", pjModelP(g, (M.total || [])[i]))}
    ${pjCell((M.ml || [])[i], "", pjModelP(g, (M.ml || [])[i]))}`;
  const src = M.books ? "DK + FD" : "Model";
  return `<div class="mk"><span class="mk-h">${src}</span><i>${esc(M.spreadLab || "Spread")}</i><i>Total</i><i>Money</i>${row(g.a, 0)}${row(g.h, 1)}</div>`;
}
// the game card: model win chances and projected score on top, the market underneath with the model's read
function pjGameCard(g) {
  const open = PJ.open.has(String(g.id)), pre = g.state === "pre";
  let body = "";
  if (open) { const P = PJA.panels ? PJA.panels(g) : [], k = PJ.panel[g.id] && P.some(x => x.k === PJ.panel[g.id]) ? PJ.panel[g.id] : (P[0] || {}).k;
    if (P.length) body = `<div class="xpanel"><div class="tabs">${P.map(x => `<button class="${x.k === k ? "on" : ""}" data-pv="${esc(g.id)}|${x.k}">${x.label}</button>`).join("")}</div>
      <div class="xbody">${P.find(x => x.k === k).html()}</div></div>`; }
  const p = g.state === "live" && g.lph != null ? g.lph : g.ph;
  const team = (t, k) => { const mine = k === "h" ? p : 1 - p, sc = g.score ? g.score[k] : null, other = g.score ? g.score[k === "h" ? "a" : "h"] : null;
    return `<div class="tr ${mine >= 0.5 ? "fav" : ""} ${g.state === "final" && sc < other ? "lose" : ""}">${pjLogo(t)}<span class="tm-n"><b>${esc(t.name)}</b>${t.sub ? `<i>${t.sub}</i>` : ""}</span>
      ${pre ? `<span class="tr-p"><b>${esc(k === "h" ? g.sh : g.sa)}</b><i>proj</i></span>` : `<strong>${sc ?? 0}</strong>`}<span class="tr-w"><b>${pjPct(mine)}</b><i>${g.state === "live" && g.lph != null ? "live" : g.state === "final" ? "model" : "win"}</i></span></div>`; };
  const pa = Math.round(100 * (1 - p)), best = pjGameEdges(g).filter(e => e.ev >= PJ_EDGE).sort((a, b) => b.ev - a.ev)[0];
  return `<article class="gc ${g.state === "live" ? "islive" : ""}" data-gid="${esc(g.id)}" style="--ca:${esc(g.a.color || "#3a4a44")};--ch:${esc(g.h.color || "#44503a")}">
      <div class="gc-h"><span class="gc-st">${pjStatus(g)}</span>${pre ? pjCountdown(g) : ""}${g.note ? `<span class="gc-note">${g.note}</span>` : ""}${PJA.simUrl ? `<a class="gc-sim" href="${esc(PJA.simUrl(g))}">Sim it ›</a>` : ""}</div>
      <div class="rows">${team(g.a, "a")}${team(g.h, "h")}</div>
      <div class="tug"><i style="width:${pa}%;background:${esc(g.a.color || "#556")}"></i><i style="width:${100 - pa}%;background:${esc(g.h.color || "#556")}"></i></div>
      ${g.stats && g.stats.length ? `<div class="gst">${g.stats.map(([l, v]) => `<div><i>${l}</i><b>${v}</b></div>`).join("")}</div>` : ""}
      ${pjMarkets(g)}
      ${best ? `<div class="gc-edge"><span>Model edge</span><b>${esc(best.x.pick)} ${bkAm(best.x.dec)}</b><em>${pjEvTxt(best.ev)} value</em></div>` : ""}
    ${body}<button class="more" data-more="${esc(g.id)}">${open ? "Show less" : "Matchup · players · details"}</button></article>`;
}
// Home: a game row with the model's win chance and the market moneyline
function pjGameRow(g) {
  const M = g.state === "pre" ? pjLines(g) : null;
  const side = (t, i, mine, sc, other) => `<div class="gr-t">${pjLogo(t)}<b>${esc(t.name)}</b>${g.state === "pre" ? `<em>${pjPct(mine)}</em>${M && M.ml && M.ml[i] ? bkBtn(M.ml[i]) : ""}` : `<strong class="${g.state === "final" && sc < other ? "lose" : ""}">${sc ?? 0}</strong>`}</div>`;
  return `<div class="gr" data-gogame="${esc(g.id)}"><div class="gr-st">${pjStatus(g)}${g.state === "pre" ? `<span>Model · Market</span>` : ""}</div>
    ${side(g.a, 0, 1 - g.ph, g.score && g.score.a, g.score && g.score.h)}${side(g.h, 1, g.ph, g.score && g.score.h, g.score && g.score.a)}</div>`;
}
const pjEmpty = (t, s) => `<div class="empty"><div class="t">${esc(t)}</div><div class="note">${esc(s)}</div></div>`;
const pjOpenGames = () => PJA.games().filter(g => g.state === "pre");
function pjCountdown(g) {
  const C = pjCtx(g.id), t = C && C.start ? new Date(C.start) - Date.now() : null;
  if (t == null || t <= 0) return "";
  const h = Math.floor(t / 36e5), m = Math.floor(t % 36e5 / 6e4);
  return h >= 24 ? "" : `<b class="cd">${h ? h + "h " : ""}${m}m</b>`;
}
function pjTicker(live) {
  if (!live.length) return "";
  return `<div class="tick">${live.map(g => `<button class="tk" data-gogame="${esc(g.id)}"><b class="st-live">Live</b><span>${esc(g.a.abbr)} <b>${g.score ? g.score.a : 0}</b></span><span>${esc(g.h.abbr)} <b>${g.score ? g.score.h : 0}</b></span><i>${esc(g.detail || "")}</i></button>`).join("")}</div>`;
}
// ---- screens ----
function pjHome() {
  const G = PJA.games(), live = G.filter(g => g.state === "live"), pre = pjOpenGames();
  if (!G.length) return pjEmpty("No games on the board", "Projections appear once the next slate is set.");
  const E = pjAllEdges(), mkt = pre.filter(g => { const M = pjLines(g); return M && M.books; }).length;
  const hero = `<section class="hero"><span class="hero-k">${esc(PJA.kicker())}</span>
      <div class="hero-n"><div><b>${G.length}</b><i>games</i></div><div><b>${mkt}</b><i>with market lines</i></div><div><b class="${E.length ? "up" : ""}">${E.length}</b><i>model edges</i></div></div>
      <span class="hero-s">An edge is a price where the model's chance, blended with the market's, beats it by ${Math.round(100 * PJ_EDGE)}% or more.</span></section>`;
  const top = (PJA.top ? PJA.top() : []).slice(0, 6);
  return hero + pjTicker(live)
    + (E.length ? `<div class="hd"><b>Top edges</b><span class="hd-s">Model vs market</span></div><div class="list">${E.slice(0, 8).map(pjEdgeRow).join("")}</div>` : "")
    + `<div class="hd"><b>${esc(PJA.gamesLabel || "Tonight's games")}</b><button data-go="games">All games</button></div><div class="gl">${G.filter(g => g.state !== "live").map(pjGameRow).join("")}</div>`
    + (top.length ? `<div class="hd"><b>${esc(PJA.topLabel || "Top projections")}</b><button data-go="players">All players</button></div><div class="list">${top.map(({p, mk}) => pjProjRow(p, mk)).join("")}</div>` : "")
    + (PJA.record ? PJA.record() : "");
}
function pjGames() {
  const G = PJA.games();
  if (!G.length) return pjEmpty("No games on the board", "Check back on the next game day.");
  return (PJA.gamesHead ? PJA.gamesHead() : "") + G.map(pjGameCard).join("");
}
// a player row: the projection, then DraftKings' lines with the model's chance at each
function pjProjRow(p, mk) {
  const m = PJA.markets.find(x => x.k === mk) || PJA.markets[0], v = p.vals[m.k] || {}, E = pjPropEdges(p, m.k).slice(0, 3);
  return `<div class="pr" style="--tc:${esc(p.color || "#556")}"><button class="pr-who" data-player="${esc(p.id)}">${pjAv(p)}<span><b>${esc(p.name)}</b><i>${esc(pjMeta(p))}</i></span></button>
    <span class="pr-pj"><b>${esc(v.txt ?? "–")}</b><i>${esc(m.unit || "")}</i></span>
    ${E.length ? `<div class="pr-px" style="--n:${E.length}">${E.map(e => pjCell(e.x, e.top, e.mp)).join("")}</div>` : ""}</div>`;
}
const pjPlayerRow = (p, mk) => pjProjRow(p, mk);
function pjPlayers() {
  const all = PJA.players();
  if (!all.length) return pjEmpty("No player projections yet", "They appear once lineups are in.");
  if (!PJ.mk || !PJA.markets.some(m => m.k === PJ.mk)) PJ.mk = PJA.markets[0].k;
  const m = PJA.markets.find(x => x.k === PJ.mk), q = PJ.q.trim().toLowerCase(), G = PJA.games(), byEdge = PJ.sort === "edge";
  let L = all.filter(p => p.vals[m.k] && p.vals[m.k].v != null && (PJ.game === "all" || String(p.gid) === PJ.game) && (!q || p.name.toLowerCase().includes(q) || String(p.team).toLowerCase() === q));
  const best = p => Math.max(-1, ...pjPropEdges(p, m.k).map(e => e.ev ?? -1));
  if (byEdge) L = L.map(p => [p, best(p)]).filter(x => x[1] > -1).sort((a, b) => b[1] - a[1]).map(x => x[0]); else L.sort((x, y) => y.vals[m.k].v - x.vals[m.k].v);
  const tabs = `<div class="tabs pj-mk">${PJA.markets.map(x => `<button class="${x.k === m.k ? "on" : ""}" data-pjmk="${x.k}">${x.label}</button>`).join("")}</div>`;
  const chips = `<div class="strip pj-strip"><button class="chip ${byEdge ? "" : "on"}" data-pjsort="proj">Projections</button><button class="chip ${byEdge ? "on" : ""}" data-pjsort="edge">Best edges</button>
    <button class="chip ${PJ.q ? "on" : ""}" data-pjsearch="1" aria-label="Search">${pjIc("search")}</button><button class="chip ${PJ.game === "all" ? "on" : ""}" data-pjg="all">All games</button>${G.map(g => `<button class="chip ${PJ.game === String(g.id) ? "on" : ""}" data-pjg="${esc(g.id)}">${pjLogo(g.a)}${pjLogo(g.h)}${esc(g.a.abbr)} @ ${esc(g.h.abbr)}</button>`).join("")}</div>
    ${PJ.searching || PJ.q ? `<input class="search" id="pjq" placeholder="Search a player or team" value="${esc(PJ.q)}" autocomplete="off">` : ""}`;
  const note = `<div class="pj-note2">${esc(m.note || "")}${pjMktProps() ? " · DraftKings + FanDuel lines with the model's chance" : ""}</div>`;
  return tabs + chips + note + `<div class="list prs">${L.slice(0, PJ.n).map(p => pjProjRow(p, m.k)).join("") || `<div class="bk-empty">${byEdge ? "No DraftKings lines posted for this market yet." : "No players match."}</div>`}</div>
    ${L.length > PJ.n ? `<button class="gmore" data-pjmore="1">Show more (${L.length - PJ.n})</button>` : ""}`;
}
function pjOpenPlayer(id) {
  const p = PJA.players().find(x => String(x.id) === String(id)); if (!p) return;
  const tiles = PJA.markets.filter(m => p.vals[m.k] && p.vals[m.k].v != null).map(m => { const v = p.vals[m.k];
    return `<div class="ps-tile"><b>${esc(v.txt)}</b><span>${esc(m.label)}</span>${v.live != null ? `<em class="pj-live">${esc(v.live)} now</em>` : ""}</div>`; }).join("");
  const mk = PJA.markets.map(m => { const E = pjPropEdges(p, m.k); return E.length ? `<div class="sec">${esc(m.label)} · DK + FD</div><div class="ps-px">${E.map(e => pjCell(e.x, e.top, e.mp)).join("")}</div>` : ""; }).join("");
  const lines = !mk && PJA.playerLines ? PJA.playerLines(p.id) : [];
  pjSheet(`<div class="ps-h" style="--tc:${esc(p.color || "#556")}">${pjAv(p, "big")}<div><div class="sh-t">${esc(p.name)}</div><div class="sh-s">${esc(pjMeta(p))}</div></div>${p.logo ? `<img class="ps-lg" src="${esc(p.logo)}" alt="" onerror="this.remove()">` : ""}</div>
    <div class="ps-tiles">${tiles}</div>${mk}
    ${lines.length ? `<div class="sec">Model chances</div><div class="ps-lines">${lines.map(([l, c]) => `<div class="ps-ln"><span>${esc(l)}</span>${pjMeter(c)}<b>${pjPct(c)}</b><i>${pjFair(c)}</i></div>`).join("")}</div>` : ""}
    <div class="hint">${esc(PJA.sheetNote || "")}</div>`);
}
function pjRender() {
  if (!PJA) return;
  if (!PJ_TABS.some(t => t[0] === TAB)) TAB = "home";
  try { PJA.header && PJA.header(); PJA.strip && PJA.strip(); } catch (e) {}
  { const s = document.getElementById("strip");   // only real controls stay up there (NHL: Tonight / Last night)
    if (s) { s.querySelectorAll("span.chip").forEach(x => x.remove()); s.style.display = s.children.length && TAB !== "model" && TAB !== "players" ? "" : "none"; } }
  pjNav();
  const b = document.body;
  [...b.classList].filter(c => c.startsWith("tab-")).forEach(c => b.classList.remove(c)); b.classList.add("tab-" + TAB);
  const v = document.getElementById("view");
  const html = ({home: pjHome, games: pjGames, players: pjPlayers, model: () => PJA.modelHtml ? PJA.modelHtml() : ""}[TAB] || pjHome)();
  if (html !== window.PJ_HTML || v.dataset.tab !== TAB) { window.PJ_HTML = html; v.dataset.tab = TAB; v.innerHTML = html; }
  v.querySelectorAll("[data-go]").forEach(x => x.onclick = () => pjGo(x.dataset.go));
  v.querySelectorAll("[data-gogame]").forEach(x => x.onclick = () => { PJ.open.add(String(x.dataset.gogame)); TAB = "games"; pjRender();
    const c = document.querySelector(`.gc[data-gid="${CSS.escape(String(x.dataset.gogame))}"]`); if (c) window.scrollTo({top: c.getBoundingClientRect().top + scrollY - (parseInt(getComputedStyle(document.documentElement).getPropertyValue("--hdrh")) || 120) - 8}); });
  v.querySelectorAll("[data-more]").forEach(x => x.onclick = () => { const k = String(x.dataset.more); PJ.open.has(k) ? PJ.open.delete(k) : PJ.open.add(k); pjRender(); });
  v.querySelectorAll("[data-pv]").forEach(x => x.onclick = () => { const [id, k] = x.dataset.pv.split("|"); PJ.panel[id] = k; pjRender(); });
  v.querySelectorAll("[data-player]").forEach(x => x.onclick = e => { e.stopPropagation(); pjOpenPlayer(x.dataset.player); });
  v.querySelectorAll("[data-pjmk]").forEach(x => x.onclick = () => { PJ.mk = x.dataset.pjmk; PJ.n = 40; pjRender(); });
  v.querySelectorAll("[data-pjsort]").forEach(x => x.onclick = () => { PJ.sort = x.dataset.pjsort; PJ.n = 40; pjRender(); });
  v.querySelectorAll("[data-pjg]").forEach(x => x.onclick = () => { PJ.game = x.dataset.pjg; PJ.n = 40; pjRender(); });
  v.querySelectorAll("[data-pjmore]").forEach(x => x.onclick = () => { PJ.n += 40; pjRender(); });
  v.querySelectorAll("[data-pjsearch]").forEach(x => x.onclick = () => { PJ.searching = !PJ.searching; if (!PJ.searching) PJ.q = ""; pjRender(); const i = document.getElementById("pjq"); if (i) i.focus(); });
  const q = document.getElementById("pjq");
  if (q) q.oninput = () => { PJ.q = q.value; const pos = q.selectionStart; pjRender(); const n = document.getElementById("pjq"); if (n) { n.focus(); n.setSelectionRange(pos, pos); } };
  if (TAB === "model" && PJA.modelWire) PJA.modelWire(pjRender);
  if (PJA.after) PJA.after(pjRender);
  requestAnimationFrame(() => { const h = document.querySelector(".hdr"); if (h) { const hv = h.offsetHeight + "px"; if (window.PJ_HH !== hv) { window.PJ_HH = hv; document.documentElement.style.setProperty("--hdrh", hv); } } });
  const sp = document.getElementById("splash"); if (sp && !sp.classList.contains("out")) { sp.classList.add("out"); setTimeout(() => sp.remove(), 400); }
}
window.addEventListener("scroll", () => { const h = document.querySelector(".hdr"); if (h) h.classList.toggle("stuck", window.scrollY > 8); }, {passive: true});
setInterval(() => { if (TAB === "home" && !document.getElementById("sheet").classList.contains("open")) pjRender(); }, 60e3);   // countdowns
