// ---------- PIKT (shared by the NHL, NFL and NBA pages) ----------
// A play-coin sportsbook on the real market (consensus game lines from The Odds API, DraftKings props) with the
// model's read on every price: its chance for each side, and the prices where it sees an edge. Bets settle from
// ESPN finals (calib/web/book.js).
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
const PJ_TABS = [["home", "Home"], ["games", "Games"], ["players", "Props"], ["bets", "My bets"], ["model", "Model"]];
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
// market odds (calib/odds.py): consensus game lines across US books, DraftKings props; the page's own prices fill the gaps
let PJ_ODDS = {};
fetch("odds.json?v=" + Date.now()).then(r => r.json()).then(d => { PJ_ODDS = d || {}; if (PJA) pjRender(); }).catch(() => {});
const pjDec = a => a > 0 ? 1 + a / 100 : 1 + 100 / -a;
const pjNoVig = (a, b) => { const x = 1 / pjDec(a), y = 1 / pjDec(b); return x / (x + y); };
function pjMarket(g) {
  const RT = PJ_RT.g[g.id];
  if (RT && RT.odds && Date.now() - RT.at < (RT.state === "in" ? 120e3 : 15 * 60e3) && (RT.state === "pre" || RT.state === "in"))
    return Object.assign({}, RT.odds, {books: "DraftKings", rt: true, live: RT.state === "in", at: RT.at, was: RT.wasAt && Date.now() - RT.wasAt < 45e3 ? RT.was : null});
  const L = ((PJ_ODDS.lines || {})[PJA.sport] || {}).games || [], C = pjCtx(g.id), t = C && C.start ? new Date(C.start) : null;
  const is = (full, team) => { const a = bkNm(full), b = bkNm(team.name); return !!b && (a.endsWith(b) || a === bkNm(team.abbr)); };
  return L.find(x => x.gid && x.gid === String(g.id)) || L.find(x => !x.gid && is(x.home, g.h) && is(x.away, g.a) && (!t || !x.t || Math.abs(new Date(x.t) - t) < 36e5 * 18)) || null;
}
// ---------- real time: DraftKings odds and game state straight from ESPN, every 30 seconds ----------
// The scoreboard carries each game's current DraftKings moneyline, spread and total (cached by ESPN for seconds, open
// to browsers); once a game starts, ESPN's odds feed has DraftKings' live line. Player props come from ESPN's
// DraftKings prop feed every five minutes. All of it lands in the page without waiting for the server.
const PJ_RT = {g: {}, at: 0, busy: false, props: 0, names: {}};
const pjAm = v => { if (v == null) return null; if (typeof v === "object") return pjAm(v.american ?? v.alternateDisplayValue ?? v.value);
  const t = String(v).trim().toUpperCase(); if (t === "EVEN" || t === "EV") return 100; const n = parseFloat(t.replace(/[^0-9.+-]/g, "")); return isFinite(n) && Math.abs(n) >= 100 ? n : null; };
const pjLn = v => { if (v == null) return null; if (typeof v === "object") return pjLn(v.american ?? v.alternateDisplayValue ?? v.value); const n = parseFloat(String(v).replace(/^[ou]/i, "")); return isFinite(n) ? n : null; };
// the scoreboard's DraftKings block -> {ml: {home, away}, spread: {home (line), home_price, away_price}, total: {line, over, under}}
function pjParseSite(o) {
  if (!o) return null;
  const cur = x => x ? (x.live || x.current || x.close || x.open || {}) : {}, M = o.moneyline || {}, P = o.pointSpread || {}, T = o.total || {};
  const X = {};
  const mh = pjAm(cur(M.home).odds) ?? pjAm((o.homeTeamOdds || {}).moneyLine), ma = pjAm(cur(M.away).odds) ?? pjAm((o.awayTeamOdds || {}).moneyLine);
  if (mh != null && ma != null) X.ml = {home: mh, away: ma};
  const sl = pjLn(cur(P.home).line) ?? (o.spread != null ? Number(o.spread) : null), sh = pjAm(cur(P.home).odds) ?? pjAm((o.homeTeamOdds || {}).spreadOdds), sa = pjAm(cur(P.away).odds) ?? pjAm((o.awayTeamOdds || {}).spreadOdds);
  if (sl != null && sh != null && sa != null) X.spread = {home: sl, home_price: sh, away_price: sa};
  const tl = pjLn(cur(T.over).line) ?? (o.overUnder != null ? Number(o.overUnder) : null), to = pjAm(cur(T.over).odds) ?? pjAm(o.overOdds), tu = pjAm(cur(T.under).odds) ?? pjAm(o.underOdds);
  if (tl != null && to != null && tu != null) X.total = {line: tl, over: to, under: tu};
  return X.ml || X.spread || X.total ? X : null;
}
// ESPN's odds feed item (provider 100 = DraftKings): its live block in a game, else the current one
function pjParseCore(it) {
  if (!it) return null;
  const H = it.homeTeamOdds || {}, A = it.awayTeamOdds || {}, L = it.live && typeof it.live === "object" ? it.live : null;
  const side = (S, k) => (L && L[k] && L[k] === S ? L[k] : null) || S.live || S.current || {};
  const hc = side(H, "homeTeamOdds"), ac = side(A, "awayTeamOdds"), tc = (L && (L.over || L.total) ? L : null) || it.current || {};
  const X = {};
  const mh = pjAm(hc.moneyLine) ?? pjAm(H.moneyLine), ma = pjAm(ac.moneyLine) ?? pjAm(A.moneyLine);
  if (mh != null && ma != null) X.ml = {home: mh, away: ma};
  const sl = pjLn(hc.pointSpread) ?? (it.spread != null ? Number(it.spread) : null), sh = pjAm(hc.spread) ?? pjAm(H.spreadOdds), sa = pjAm(ac.spread) ?? pjAm(A.spreadOdds);
  if (sl != null && sh != null && sa != null) X.spread = {home: sl, home_price: sh, away_price: sa};
  const tl = pjLn(tc.total) ?? (it.overUnder != null ? Number(it.overUnder) : null), to = pjAm(tc.over), tu = pjAm(tc.under);
  if (tl != null && to != null && tu != null) X.total = {line: tl, over: to, under: tu};
  return X.ml || X.spread || X.total ? X : null;
}
const pjEspnPath = () => (BK_ESPN[PJA.sport] || [])[0];
async function pjPoll() {
  if (!PJA || PJ_RT.busy || document.hidden || !pjEspnPath()) return; PJ_RT.busy = true;
  try {
    const sp = pjEspnPath(), fix = BK_ESPN[PJA.sport][1] || {}, G = PJA.games();
    const dates = [...new Set(G.filter(g => g.state !== "final").map(g => ((pjCtx(g.id) || {}).ev || {}).date).filter(Boolean))].slice(0, 4);
    if (!dates.length) return;
    const evs = (await Promise.all(dates.map(d => fetch(`https://site.api.espn.com/apis/site/v2/sports/${sp}/scoreboard?dates=${d}`).then(r => r.json()).catch(() => ({}))))).flatMap(j => j.events || []);
    const now = Date.now();
    for (const g of G) {
      const C = pjCtx(g.id); if (!C || !C.ev) continue;
      const ev = evs.find(e => String(e.id) === String(C.ev.id)) || evs.find(e => { const c = (e.competitions || [])[0]; if (!c) return false;
        const t = {}; for (const x of c.competitors || []) t[x.homeAway] = fix[x.team.abbreviation] || x.team.abbreviation; return t.home === C.ev.home && t.away === C.ev.away; });
      if (!ev) continue;
      const st = ev.status.type.state, c = ev.competitions[0];
      let O = st === "pre" ? pjParseSite((c.odds || []).find(o => String((o.provider || {}).id) === "100") || (c.odds || [])[0]) : null;
      if (st === "in") {   // in play: DraftKings' live line from the odds feed
        try { const j = await (await fetch(`https://sports.core.api.espn.com/v2/sports/${sp.replace("/", "/leagues/")}/events/${ev.id}/competitions/${ev.id}/odds`)).json();
          O = pjParseCore((j.items || []).find(i => String((i.provider || {}).id) === "100")); } catch (e) { O = null; }
      }
      const prev = PJ_RT.g[g.id] || {};
      PJ_RT.g[g.id] = {espn: ev.id, state: st, odds: O, at: O ? now : prev.at, was: prev.odds && JSON.stringify(prev.odds) !== JSON.stringify(O) ? prev.odds : prev.was, wasAt: prev.odds && JSON.stringify(prev.odds) !== JSON.stringify(O) ? now : prev.wasAt};
    }
    PJ_RT.at = now;
    if (now - PJ_RT.props > 5 * 60e3) { PJ_RT.props = now; pjPollProps(evs).catch(() => {}); }
    pjRefresh();
  } finally { PJ_RT.busy = false; }
}
// redraw unless the user is typing or has a sheet open (the slip reads fresh prices from the registry when it reopens)
function pjRefresh() { const ae = document.activeElement, sh = document.getElementById("sheet");
  if ((ae && (ae.tagName === "INPUT" || ae.tagName === "SELECT")) || (sh && sh.classList.contains("open"))) return; pjRender(); }
// DraftKings player props from ESPN (same reading as calib/odds.py): milestones "N+", anytime scorers, 2+ scorers
const PJ_RULES = {NBA: [["points + rebounds + assists", "pra"], ["pts + reb + ast", "pra"], ["points, rebounds", "pra"], ["rebounds + assists", null], ["+", null], ["three", "fg3"], ["3-point", "fg3"], ["3pt", "fg3"], ["rebound", "reb"], ["assist", "ast"], ["point", "pts"]],
  NFL: [["+", null], ["passing yards", "pass_yds"], ["rushing yards", "rush_yds"], ["receiving yards", "rec_yds"], ["reception", "rec"]],
  NHL: [["+", null], ["shots", "sog"], ["assist", "assists"], ["point", "points"], ["goal", "goals"]]};
function pjPropKind(lg, name) {
  const n = String(name || "").toLowerCase();
  if (/1st|2nd|3rd|half|quarter|period|first |last /.test(n)) return null;
  if (/power ?play|short|blocked|save|team|hit|faceoff|penalt|takeaway|giveaway|longest|interception|attempt|completion/.test(n)) return null;   // share a keyword with our stats
  if (lg === "NFL" && n.includes("2 or more touchdowns")) return ["td", 1.5];
  if (lg === "NHL" && n.includes("score 2+ goals")) return ["goals", 1.5];
  if (n.includes("anytime")) return lg === "NFL" && (n.includes("touchdown") || n.includes(" td")) ? ["td", true] : lg === "NHL" && n.includes("goal") ? ["goals", true] : null;
  if (!n.includes("milestone")) return null;
  for (const [kw, st] of PJ_RULES[lg] || []) if (n.includes(kw)) return st ? [st, false] : null;
  return null;
}
function pjPropPrice(it) {   // the item's American price wherever ESPN put it
  const stack = [it.odds, it.current, Object.fromEntries(Object.entries(it).filter(([k]) => !["athlete", "type", "links", "odds", "current"].includes(k)))];
  while (stack.length) { const x = stack.shift();
    if (Array.isArray(x)) stack.push(...x);
    else if (x && typeof x === "object") {
      if ("american" in x && pjAm(x.american) != null) return pjAm(x.american);
      if ("decimal" in x) { const d = parseFloat(typeof x.decimal === "object" ? x.decimal.value : x.decimal); if (d > 1) return d >= 2 ? Math.round((d - 1) * 100) : Math.round(-100 / (d - 1)); }
      stack.push(...Object.values(x).filter(v => v && typeof v === "object")); } }
  return null;
}
async function pjPollProps(evs) {
  const lg = PJA.sport, sp = pjEspnPath(), now = Date.now();
  const soon = evs.filter(e => e.status.type.state === "pre" && new Date(e.date) - now < 12 * 36e5);
  if (!soon.length) return;
  const J = u => fetch(u).then(r => r.json()).catch(() => ({}));
  for (const e of soon) for (const c of e.competitions[0].competitors || []) {   // who's who: the two rosters, once per visit
    const tid = (c.team || {}).id; if (!tid || PJ_RT.names["t" + tid]) continue; PJ_RT.names["t" + tid] = 1;
    const r = await J(`https://site.api.espn.com/apis/site/v2/sports/${sp}/teams/${tid}/roster`);
    for (const grp of r.athletes || []) for (const a of (grp.items || [grp])) if (a.id && (a.fullName || a.displayName)) PJ_RT.names[String(a.id)] = bkNm(a.fullName || a.displayName);
  }
  const out = {};
  await Promise.all(soon.map(async e => {
    for (let page = 1, pages = 1; page <= pages && page <= 4; page++) {
      const pb = await J(`https://sports.core.api.espn.com/v2/sports/${sp.replace("/", "/leagues/")}/events/${e.id}/competitions/${e.id}/odds/100/propBets?limit=1000&page=${page}`);
      pages = Number(pb.pageCount) || 1;
      for (const it of pb.items || []) {
        const k = pjPropKind(lg, (it.type || {}).name), m = /\/athletes\/(\d+)/.exec((it.athlete || {}).$ref || ""); if (!k || !m) continue;
        const who = PJ_RT.names[m[1]], price = pjPropPrice(it); if (!who || price == null) continue;
        let line; if (typeof k[1] === "number") line = k[1]; else if (k[1]) line = .5; else { const t = ((it.current || {}).target || {}).value; if (t == null) continue; line = Number(t) - .5; }
        (out[who] = out[who] || {})[`${k[0]}|${line}`] = price;
      }
    }
  }));
  if (Object.keys(out).length) { PJ_ODDS.props = PJ_ODDS.props || {};
    const O = PJ_ODDS.props[lg] || {}, P = {}, B = JSON.parse(JSON.stringify(O.bk || {}));
    for (const [w, q] of Object.entries(O.players || {})) if (B[w]) P[w] = Object.fromEntries(Object.entries(q).filter(([k]) => B[w][k]));   // FanDuel-only rungs stay
    for (const [w, q] of Object.entries(out)) { P[w] = Object.assign(P[w] || {}, q); if (B[w]) for (const k in q) delete B[w][k]; }   // DraftKings wins where it hangs the rung
    PJ_ODDS.props[lg] = Object.assign({}, O, {fetched_at: new Date().toISOString(), live: true, players: P, bk: B}); pjRefresh(); }
}
setTimeout(() => pjPoll(), 1200); setInterval(() => pjPoll(), 30e3);
document.addEventListener("visibilitychange", () => { if (!document.hidden) pjPoll(); });
const pjAgo = t => { const s = Math.max(0, Math.round((Date.now() - t) / 1000)); return s < 60 ? `${s}s ago` : `${Math.round(s / 60)}m ago`; };
// a live game's bettable sides, built from the page's game context (pre-game lines close at the start)
function pjLiveBase(g) {
  const C = pjCtx(g.id); if (!C) return null;
  const S = (kind, side, mkt) => Object.assign({kind, side, mkt, gid: String(g.id)}, C, {live: true, open: true});
  return {spreadLab: PJA.sport === "NHL" ? "Puck line" : "Spread", spread: [S("spread", "away", "Live spread"), S("spread", "home", "Live spread")],
    total: [S("total", "over", "Live total"), S("total", "under", "Live total")], ml: [S("ml", "away", "Live moneyline"), S("ml", "home", "Live moneyline")]};
}
// game lines with their artwork: each side carries its team's logo and colour, totals carry both logos
function pjLines(g) {
  const X = pjMarket(g), live = !!(X && X.live);
  let M = PJA.lines && g.state === "pre" ? PJA.lines(g.id) : null;
  if (!M && live) M = pjLiveBase(g);
  if (!M) return null;
  if (X) {   // swap in the market: its line and its price
    const W = X.was || {}, tag = live ? " (live)" : "";
    const R = (base, line, price, p, pick, old) => base && price != null ? bkSel(Object.assign({}, base, {line, p, dec: Math.round(pjDec(price) * 1e4) / 1e4, pick: pick + tag, src: "mkt", at: X.at,
      mv: old != null && old !== price ? (pjDec(price) > pjDec(old) ? 1 : -1) : 0})) : (live ? null : base);
    const wm = W.ml || {}, ws = W.spread || {}, wt = W.total || {};
    if (M.ml) M.ml = X.ml ? [R(M.ml[0], null, X.ml.away, pjNoVig(X.ml.away, X.ml.home), `${g.a.abbr} to win`, wm.away), R(M.ml[1], null, X.ml.home, pjNoVig(X.ml.home, X.ml.away), `${g.h.abbr} to win`, wm.home)] : live ? [null, null] : M.ml;
    if (M.spread) { if (X.spread) { const h = X.spread.home, ph = pjNoVig(X.spread.home_price, X.spread.away_price), same = ws.home === h;
      M.spread = [R(M.spread[0], -h, X.spread.away_price, 1 - ph, `${g.a.abbr} ${pjSp(-h)}`, same ? ws.away_price : null), R(M.spread[1], h, X.spread.home_price, ph, `${g.h.abbr} ${pjSp(h)}`, same ? ws.home_price : null)]; } else if (live) M.spread = [null, null]; }
    if (M.total) { if (X.total) { const l = X.total.line, po = pjNoVig(X.total.over, X.total.under), same = wt.line === l;
      M.total = [R(M.total[0], l, X.total.over, po, `Over ${l}`, same ? wt.over : null), R(M.total[1], l, X.total.under, 1 - po, `Under ${l}`, same ? wt.under : null)]; } else if (live) M.total = [null, null]; }
    Object.assign(M, {books: X.books, rt: X.rt, live, at: X.at});
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
const pjPropLab = (stat, n) => stat === "goals" && n === 1 ? "Scores a goal" : stat === "td" && n === 1 ? "Anytime TD" : `${n}+ ${PJ_PLAB[stat] || stat}`;
const pjMktProps = () => { const P = ((PJ_ODDS.props || {})[PJA.sport] || {}).players; return P && Object.keys(P).length ? P : null; };
// a ladder has to make sense: each higher rung ("3+" after "2+") is less likely, so its price is longer. A rung that
// breaks the order is a misread or stale price and is dropped rather than shown (or flagged as an edge).
function pjLadder(L) {   // walked out from the rung nearest even money, so one bad rung can't take the good ones with it
  L = L.sort((x, y) => x[2].n - y[2].n); if (L.length < 2) return L;
  const c = r => r[2].fair > 0 && r[2].fair < 1 ? r[2].fair : r[1];
  let i = 0; L.forEach((r, j) => { if (Math.abs(c(r) - 0.5) < Math.abs(c(L[i]) - 0.5)) i = j; });
  const out = [L[i]]; let last = c(L[i]);
  for (const r of L.slice(i + 1)) if (c(r) < last - 0.005) { out.push(r); last = c(r); }
  last = c(L[i]);
  for (const r of L.slice(0, i).reverse()) if (c(r) > last + 0.005) { out.unshift(r); last = c(r); }
  return out;
}
// a player's bettable lines for one stat: [{sel, top}], nearest even money first, then shown low to high.
// A player is offered exactly DraftKings' lines at DraftKings' prices; with no DraftKings props for the league, none.
function pjProps(p, stat, max = 3) {
  const C = pjCtx(p.gid); if (!C) return [];
  const MP = pjMktProps();
  let L;
  const PO = (PJ_ODDS.props || {})[PJA.sport] || {}, nk = bkNm(p.name), BK = (PO.bk || {})[nk] || {}, FR = (PO.fair || {})[nk] || {};
  if (MP) L = pjLadder(Object.entries(MP[nk] || {}).filter(([k]) => k.split("|")[0] === stat)
    .map(([k, a]) => { const n = +k.split("|")[1] + 0.5; return [pjPropLab(stat, n), 1 / pjDec(a), {stat, n, fd: BK[k] === "FD", fair: FR[k]}, a]; }));
  else return [];   // no made-up props: a league's props open when DraftKings posts them
  L = L.filter(x => x[1] != null && x[1] >= 0.1 && x[1] <= 0.9);   // no lottery tickets, no −1000 locks
  return L.sort((x, y) => Math.abs(x[1] - 0.5) - Math.abs(y[1] - 0.5)).slice(0, max).sort((x, y) => x[2].n - y[2].n).map(([l, c, spec, a]) => ({
    top: ((stat === "td" || stat === "goals") && spec.n === 1 ? "Anytime" : `${Math.ceil(spec.n)}+`) + (spec.fd ? " · FD" : ""),
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
// a prop's fair chance: DraftKings + FanDuel with the vig out (SharpAPI, both sides where posted), else its own price less a typical 6% hold
const pjMktFair = x => !x || x.p == null ? null : x.src === "dk" || x.src === "fd" ? (x.fair > 0 && x.fair < 1 ? x.fair : Math.min(0.99, (1 / x.dec) / 1.06)) : x.p;
function pjEV(x, mp) {
  if (!pjIsMkt(x) || mp == null || !isFinite(mp)) return null;
  const pm = pjMktFair(x); if (pm == null) return null;
  if (Math.abs(mp - pm) > PJ_GAP) return null;
  return (PJ_W * mp + (1 - PJ_W) * pm) * x.dec - 1;
}
const pjEvTxt = ev => `${ev >= 0 ? "+" : "−"}${Math.abs(100 * ev).toFixed(1)}%`;
// a bettable price: the market's odds (the model's own price where the market has none), with the model's chance under it
function pjCell(x, top, mp) {
  if (!x || x.p == null || !isFinite(x.dec)) return `<span class="px off">–</span>`;
  const ev = pjEV(x, mp), hot = !x.live && ev != null && ev >= PJ_EDGE, t = top ? `<i>${esc(top)}</i>` : "";   // edges are a pre-game read
  if (!x.open) return `<span class="px off">${t}<b>🔒</b></span>`;
  const mv = x.mv > 0 ? "mv-up" : x.mv < 0 ? "mv-dn" : "";   // the price just moved: longer odds flash green, shorter red
  return `<button class="px ${hot ? "edge" : ""} ${pjIsMkt(x) ? "" : "fair"} ${bkIn(x.key) ? "on" : ""} ${mv}" data-bk="${esc(x.key)}">${t}<b>${bkAm(x.dec)}${mv ? `<s>${x.mv > 0 ? "▲" : "▼"}</s>` : ""}</b><em>${hot ? pjEvTxt(ev) : mp != null ? "Model " + pjPct(mp) : x.live ? "Live" : ""}</em></button>`;
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
  return `<div class="er" ${tap}>${bkArt(e.x, "sm")}<span class="er-t"><b>${esc(e.x.pick)}</b><i>${esc(e.x.game)} · Model ${pjPct(e.mp)}</i></span>
    <span class="er-ev">${pjEvTxt(e.ev)}</span>${bkBtn(e.x)}</div>`;
}
function pjMarkets(g) {
  if (g.state !== "pre" && g.state !== "live") return "";
  const M = pjLines(g); if (!M || (g.state === "live" && !M.live)) return "";
  const row = (t, i) => `<span class="mk-t">${pjLogo(t)}<b>${esc(t.abbr)}</b></span>
    ${pjCell((M.spread || [])[i], (M.spread || [])[i] ? pjSp(M.spread[i].line) : "", pjModelP(g, (M.spread || [])[i]))}
    ${pjCell((M.total || [])[i], (M.total || [])[i] ? `${i ? "U" : "O"} ${M.total[i].line}` : "", pjModelP(g, (M.total || [])[i]))}
    ${pjCell((M.ml || [])[i], "", pjModelP(g, (M.ml || [])[i]))}`;
  const src = M.live ? `<span class="rt-dot"></span><b>Live</b> DraftKings · ${pjAgo(M.at)}` : M.rt ? `<span class="rt-dot"></span>DraftKings · ${pjAgo(M.at)}` : M.books ? `Market · ${M.books} books` : "Model lines";
  return `<div class="mk ${M.live ? "mk-live" : ""}"><span class="mk-h">${src}</span><i>${esc(M.spreadLab || "Spread")}</i><i>Total</i><i>Money</i>${row(g.a, 0)}${row(g.h, 1)}</div>`;
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
      <div class="gc-h"><span class="gc-st">${pjStatus(g)}</span>${pre ? pjCountdown(g) : ""}${g.note ? `<span class="gc-note">${g.note}</span>` : ""}${PJA.simUrl ? `<a class="gc-sim" href="${esc(PJA.simUrl(g))}">Sim &amp; bet ›</a>` : ""}</div>
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
  return bkStripHtml() + hero + pjTicker(live)
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
  const note = `<div class="pj-note2">${esc(m.note || "")}${pjMktProps() ? " · DraftKings lines with the model's chance" : ""}</div>`;
  return tabs + chips + note + `<div class="list prs">${L.slice(0, PJ.n).map(p => pjProjRow(p, m.k)).join("") || `<div class="bk-empty">${byEdge ? "No DraftKings lines posted for this market yet." : "No players match."}</div>`}</div>
    ${L.length > PJ.n ? `<button class="gmore" data-pjmore="1">Show more (${L.length - PJ.n})</button>` : ""}`;
}
function pjOpenPlayer(id) {
  const p = PJA.players().find(x => String(x.id) === String(id)); if (!p) return;
  const tiles = PJA.markets.filter(m => p.vals[m.k] && p.vals[m.k].v != null).map(m => { const v = p.vals[m.k];
    return `<div class="ps-tile"><b>${esc(v.txt)}</b><span>${esc(m.label)}</span>${v.live != null ? `<em class="pj-live">${esc(v.live)} now</em>` : ""}</div>`; }).join("");
  const mk = PJA.markets.map(m => { const E = pjPropEdges(p, m.k); return E.length ? `<div class="sec">${esc(m.label)} · DraftKings</div><div class="ps-px">${E.map(e => pjCell(e.x, e.top, e.mp)).join("")}</div>` : ""; }).join("");
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
  const html = ({home: pjHome, games: pjGames, players: pjPlayers, bets: bkScreen, model: () => PJA.modelHtml ? PJA.modelHtml() : ""}[TAB] || pjHome)();
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
  bkWire(v);
  if (TAB === "model" && PJA.modelWire) PJA.modelWire(pjRender);
  if (PJA.after) PJA.after(pjRender);
  const c = document.getElementById("coin"); if (c) { const h = bkPill(); if (c.dataset.h !== h) { c.dataset.h = h; c.innerHTML = h; } }
  bkBar();
  requestAnimationFrame(() => { const h = document.querySelector(".hdr"); if (h) { const hv = h.offsetHeight + "px"; if (window.PJ_HH !== hv) { window.PJ_HH = hv; document.documentElement.style.setProperty("--hdrh", hv); } } });
  const sp = document.getElementById("splash"); if (sp && !sp.classList.contains("out")) { sp.classList.add("out"); setTimeout(() => sp.remove(), 400); }
}
window.addEventListener("scroll", () => { const h = document.querySelector(".hdr"); if (h) h.classList.toggle("stuck", window.scrollY > 8); }, {passive: true});
setInterval(() => { if (TAB === "home" && !document.getElementById("sheet").classList.contains("open")) pjRender(); }, 60e3);   // countdowns
// My bets: live status for a leg in this page's league
function pjLegStatus(l) {
  if (!PJA || l.sport !== PJA.sport) return null;
  const g = PJA.games().find(x => String(x.id) === String(l.gid)); if (!g) return null;
  if (g.state === "live" && g.score) return `<span class="lg-live">Live ${esc(g.detail || "")} · ${esc(g.a.abbr)} ${g.score.a}–${g.score.h} ${esc(g.h.abbr)}</span>`;
  if (g.state === "final" && g.score) return `<span class="lg-fin">Final ${esc(g.a.abbr)} ${g.score.a}–${g.score.h} ${esc(g.h.abbr)}</span>`;
  return g.time ? `<span class="lg-pre">${esc(g.time)}</span>` : null;
}
