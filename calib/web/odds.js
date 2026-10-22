// ---------- PIKT odds board + line movement (shared by the NHL, NFL and NBA pages) ----------
// The Odds tab: every upcoming game's spread, total or moneyline at DraftKings and FanDuel side by side, the opener,
// the better price marked, and the model's chance for each side. Tapping a game opens its line history: how the
// consensus line moved since it opened (calib/odds.py snapshots it every hour into odds_hist.json), against the
// model's own number.
let PJ_HIST = {};
fetch("odds_hist.json?v=" + Date.now()).then(r => r.json()).then(d => { PJ_HIST = d || {}; if (PJA) pjRender(); }).catch(() => {});
const OB = {m: "spread", sort: "time"};
const OB_M = [["spread", "Spread"], ["total", "Total"], ["ml", "Moneyline"]];
const obAm = a => a == null ? "–" : a > 0 ? "+" + a : "−" + Math.abs(a);
const obLn = x => x == null ? "–" : x === 0 ? "PK" : (x > 0 ? "+" : "−") + Math.abs(x);
const obTime = t => new Date(t * 6e4).toLocaleString("en-US", {weekday: "short", hour: "numeric", minute: "2-digit"});

// a page game's history: by game id, else by the two teams and a start within 18 hours
function obHist(g) {
  const H = Object.values((PJ_HIST || {})[PJA.sport] || {}), C = pjCtx(g.id), t = C && C.start ? new Date(C.start) : null;
  const is = (full, team) => { const a = bkNm(full), b = bkNm(team.name); return !!b && (a.endsWith(b) || a === bkNm(team.abbr)); };
  return H.find(e => e.gid && e.gid === String(g.id)) || H.find(e => is(e.home, g.h) && is(e.away, g.a) && (!t || !e.t || Math.abs(new Date(e.t) - t) < 36e5 * 18)) || null;
}
// one market's path: [[minute, value, priceA, priceB]]; value is the home spread, the total, or the home team's no-vig win chance
function obSeries(e, m) {
  if (!e) return [];
  const out = [];
  for (const s of e.s) {
    const v = m === "spread" ? [s[1], s[2], s[3]] : m === "total" ? [s[4], s[5], s[6]] : [s[7] != null && s[8] != null ? pjNoVig(s[7], s[8]) : null, s[7], s[8]];
    if (v[0] != null && (!out.length || out[out.length - 1][1] !== v[0] || out[out.length - 1][2] !== v[1])) out.push([s[0], ...v]);
  }
  return out;
}
function obMove(g, m) {
  const S = obSeries(obHist(g), m); if (S.length < 2) return null;
  const o = S[0][1], c = S[S.length - 1][1], d = c - o;
  return Math.abs(d) < (m === "ml" ? 0.01 : 0.25) ? null : {o, c, d, S};
}
function obMoveTxt(g, mv, m) {
  if (!mv) return "";
  if (m === "spread") { const t = mv.d < 0 ? g.h : g.a; return `${Math.abs(mv.d)} toward ${t.abbr}`; }   // the home line falling means money on the home side
  if (m === "total") return `${mv.d > 0 ? "Up" : "Down"} ${Math.abs(mv.d)}`;
  return `${g.h.abbr} ${pjPct(mv.o)} → ${pjPct(mv.c)}`;
}
// the model's own number: the spread and total where it sees an even chance (half points), its win chance on the moneyline
function obFair(g, m) {
  if (!PJA.price) return null;
  const solve = (f, lo, hi) => { const a = f(lo), b = f(hi); if (a == null || b == null || (a - 0.5) * (b - 0.5) > 0) return null;
    for (let i = 0; i < 40; i++) { const mid = (lo + hi) / 2, v = f(mid); if (v == null) return null; if ((v - 0.5) * (a - 0.5) > 0) lo = mid; else hi = mid; }
    return Math.round(2 * (lo + hi) / 2) / 2; };
  if (m === "spread") return PJA.sport === "NHL" ? null : solve(L => PJA.price(g.id, "spread", "home", L), -40, 40);
  if (m === "total") { const X = pjMarket(g), c = X && X.total ? X.total.line : 0; return c ? solve(L => PJA.price(g.id, "total", "over", L), c * 0.5, c * 1.5) : null; }
  return g.ph;
}
// a side of a market at one book: {line, price}
function obSide(b, m, side) {
  if (!b || !b[m]) return null;
  const x = b[m];
  if (m === "spread") return side === "home" ? {line: x.home, price: x.home_price} : {line: -x.home, price: x.away_price};
  if (m === "total") return {line: x.line, price: side === "over" ? x.over : x.under};
  return {line: null, price: side === "home" ? x.home : x.away};
}
// which of two quotes is better for the bettor: the friendlier line, then the longer price
function obBetter(a, b, m, side) {
  if (!a || a.price == null) return b; if (!b || b.price == null) return a;
  if (m !== "ml" && a.line !== b.line) { const k = m === "total" && side === "over" ? -1 : 1; return (a.line - b.line) * k > 0 ? a : b; }
  return pjDec(a.price) >= pjDec(b.price) ? a : b;
}
function obCell(q, m, cls = "") {
  if (!q || q.price == null) return `<span class="ob-c off">–</span>`;
  return `<span class="ob-c ${cls}">${m !== "ml" ? `<i>${m === "total" ? q.line : obLn(q.line)}</i>` : ""}<b>${obAm(q.price)}</b></span>`;
}
function obGame(g) {
  const X = pjMarket(g); if (!X) return "";
  const m = OB.m, by = X.by || {}, e = obHist(g), S = obSeries(e, m), mv = obMove(g, m), fair = obFair(g, m);
  const sides = m === "total" ? [["over", "Over", null], ["under", "Under", null]] : [["away", g.a.abbr, g.a], ["home", g.h.abbr, g.h]];
  const op = S.length ? e.s.find(s => (m === "spread" ? s[1] : m === "total" ? s[4] : s[7]) != null) : null;
  const opQ = side => op ? obSide(m === "spread" ? {spread: {home: op[1], home_price: op[2], away_price: op[3]}} : m === "total" ? {total: {line: op[4], over: op[5], under: op[6]}} : {ml: {home: op[7], away: op[8]}}, m, side) : null;
  const rows = sides.map(([side, lab, t]) => {
    const dk = obSide(by.DK, m, side), fd = obSide(by.FD, m, side), best = dk && fd ? obBetter(dk, fd, m, side) : null;
    const cons = obSide(X, m, side), other = obSide(X, m, side === "home" ? "away" : side === "away" ? "home" : side === "over" ? "under" : "over");
    const mp = cons ? pjModelP(g, {kind: m, side, line: cons.line}) : null, fairP = cons && other && cons.price != null && other.price != null ? pjNoVig(cons.price, other.price) : null;
    // the same guard rails as the edge reading (proj.js pjEV): a model far from the market is reading something it isn't
    const edge = mp != null && fairP != null && mp - fairP >= PJ_EDGE && mp - fairP <= PJ_GAP && Math.abs(pjLogit(mp) - pjLogit(fairP)) <= PJ_LGAP;
    return `<span class="ob-t">${t ? pjLogo(t) : `<i class="ob-ou">${side === "over" ? "O" : "U"}</i>`}<b>${esc(lab)}</b></span>${obCell(opQ(side), m, "op")}
      ${obCell(dk, m, best === dk ? "best" : "")}${obCell(fd, m, best === fd ? "best" : "")}<span class="ob-c pk ${edge ? "edge" : ""}"><b>${pjPct(mp)}</b><i>${mp != null ? pjFair(mp) : ""}</i></span>`;
  }).join("");
  const fairTxt = fair == null ? "" : m === "spread" ? `Pikt ${fair <= 0 ? g.h.abbr : g.a.abbr} ${obLn(-Math.abs(fair))}` : m === "total" ? `Pikt ${fair}` : `Pikt ${g.h.abbr} ${pjPct(fair)}`;
  return `<div class="ob-g" data-lm="${esc(g.id)}" style="--ca:${esc(g.a.color || "#3a4a44")};--ch:${esc(g.h.color || "#44503a")}">
    <div class="ob-h"><span class="ob-m">${pjLogo(g.a)}${pjLogo(g.h)}<b>${esc(g.a.abbr)} @ ${esc(g.h.abbr)}</b><i>${esc(g.time || "")}</i></span>
      ${mv ? `<span class="ob-mv ${m === "total" ? (mv.d > 0 ? "upm" : "dnm") : ""} ${mv.d < 0 && m !== "spread" ? "fall" : ""}">${pjIc("move")}${esc(obMoveTxt(g, mv, m))}</span>` : ""}</div>
    <div class="ob-grid"><i></i><i>Open</i><i>DK</i><i>FD</i><i>Pikt</i>${rows}</div>
    <div class="ob-f"><span>${esc(fairTxt)}</span><span>${S.length > 1 ? `${S.length - 1} move${S.length > 2 ? "s" : ""}` : S.length ? "No moves yet" : "History starts today"} · Line history ›</span></div></div>`;
}
function obBoard() {
  let G = PJA.games().filter(g => g.state === "pre" && pjMarket(g));
  const seg = `<div class="seg ob-seg">${OB_M.map(([k, l]) => `<button class="${OB.m === k ? "on" : ""}" data-obm="${k}">${l}</button>`).join("")}</div>`;
  const chips = `<div class="strip pj-strip"><button class="chip ${OB.sort === "time" ? "on" : ""}" data-obs="time">By start time</button><button class="chip ${OB.sort === "move" ? "on" : ""}" data-obs="move">Biggest moves</button></div>`;
  if (!G.length) return seg + pjEmpty("No lines posted yet", "DraftKings and FanDuel lines appear here as the books hang them.");
  if (OB.sort === "move") G = G.map(g => [g, Math.abs((obMove(g, OB.m) || {d: 0}).d)]).sort((a, b) => b[1] - a[1]).map(x => x[0]);
  return seg + chips + `<div class="pj-note2">DraftKings and FanDuel side by side, the better price marked · Open is the first line we saw · Pikt is the model's chance for each side</div>`
    + G.map(obGame).join("");
}
// Home: the games whose lines have moved most
function obMovesHome() {
  const L = PJA.games().filter(g => g.state === "pre").map(g => { const s = obMove(g, "spread"), t = obMove(g, "total");
    const k = s && (!t || Math.abs(s.d) >= Math.abs(t.d) / 2) ? "spread" : t ? "total" : null; return k ? {g, k, mv: k === "spread" ? s : t} : null; })
    .filter(Boolean).sort((a, b) => Math.abs(b.mv.d) / (b.k === "total" ? 2 : 1) - Math.abs(a.mv.d) / (a.k === "total" ? 2 : 1)).slice(0, 4);
  if (!L.length) return "";
  const txt = ({g, k, mv}) => k === "spread" ? `${g.h.abbr} ${obLn(mv.o)} → ${obLn(mv.c)}` : `Total ${mv.o} → ${mv.c}`;
  return `<div class="hd"><b>Line moves</b><button data-go="odds">Odds board</button></div><div class="list">${L.map(x => `<button class="ob-hm" data-lm="${esc(x.g.id)}">
    <span class="ob-m">${pjLogo(x.g.a)}${pjLogo(x.g.h)}<b>${esc(x.g.a.abbr)} @ ${esc(x.g.h.abbr)}</b></span><span class="ob-hv"><b>${esc(txt(x))}</b><i>${esc(obMoveTxt(x.g, x.mv, x.k))}</i></span><span class="chev">›</span></button>`).join("")}</div>`;
}
// ---- the line history sheet ----
function obChart(S, m, fair, seen) {
  const W = 340, H = 170, pl = 40, pr = 12, pt = 14, pb = 26;
  const t0 = S[0][0], t1 = Math.max(seen || 0, S[S.length - 1][0], t0 + 60);
  const vs = S.map(s => s[1]).concat(fair != null ? [fair] : []);
  let lo = Math.min(...vs), hi = Math.max(...vs); const padv = m === "ml" ? 0.03 : 0.5; lo -= padv; hi += padv;
  const X = t => pl + (W - pl - pr) * (t - t0) / (t1 - t0), Y = v => pt + (H - pt - pb) * (hi - v) / (hi - lo);
  let d = `M${X(S[0][0]).toFixed(1)},${Y(S[0][1]).toFixed(1)}`;
  for (let i = 1; i < S.length; i++) d += `H${X(S[i][0]).toFixed(1)}V${Y(S[i][1]).toFixed(1)}`;
  d += `H${X(t1).toFixed(1)}`;
  const lab = v => m === "ml" ? pjPct(v) : m === "spread" ? obLn(v) : String(Math.round(v * 2) / 2);
  const ticks = [hi - padv, lo + padv].filter((v, i, a) => i === 0 || Math.abs(v - a[0]) > 1e-9);
  const last = S[S.length - 1];
  return `<svg class="ob-ch" viewBox="0 0 ${W} ${H}" role="img" aria-label="Line history">
    ${ticks.map(v => `<line x1="${pl}" x2="${W - pr}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" class="gr"/><text x="${pl - 6}" y="${(Y(v) + 4).toFixed(1)}" class="yl">${esc(lab(v))}</text>`).join("")}
    ${fair != null ? `<line x1="${pl}" x2="${W - pr}" y1="${Y(fair).toFixed(1)}" y2="${Y(fair).toFixed(1)}" class="fair"/><text x="${W - pr}" y="${(Y(fair) - 5).toFixed(1)}" class="fl">Pikt ${esc(lab(fair))}</text>` : ""}
    <path d="${d}" class="ln"/><circle cx="${X(S[0][0]).toFixed(1)}" cy="${Y(S[0][1]).toFixed(1)}" r="4" class="o"/>
    <circle cx="${X(last[0]).toFixed(1)}" cy="${Y(last[1]).toFixed(1)}" r="5" class="c"/>
    <text x="${pl}" y="${H - 6}" class="xl">${esc(obTime(t0))}</text><text x="${W - pr}" y="${H - 6}" class="xl r">${seen && seen * 6e4 > Date.now() - 36e5 * 2 ? "Now" : esc(obTime(t1))}</text></svg>`;
}
function obOpen(gid) {
  const g = PJA.games().find(x => String(x.id) === String(gid)); if (!g) return;
  const m = OB.m, e = obHist(g), S = obSeries(e, m), X = pjMarket(g), fair = obFair(g, m), by = (X && X.by) || {};
  const fmt = s => m === "spread" ? `${g.h.abbr} ${obLn(s[1])} <i>${obAm(s[2])}</i>` : m === "total" ? `${s[1]} <i>o${obAm(s[2])}</i>` : `${g.h.abbr} ${obAm(s[2])} <i>${g.a.abbr} ${obAm(s[3])}</i>`;
  const seg = `<div class="seg ob-seg">${OB_M.map(([k, l]) => `<button class="${m === k ? "on" : ""}" data-obsm="${k}">${l}</button>`).join("")}</div>`;
  const book = (k, n) => { const b = by[k]; if (!b || !b[m]) return ""; const x = b[m];
    return `<div><span>${n}</span><b>${m === "spread" ? `${g.h.abbr} ${obLn(x.home)} <i>${obAm(x.home_price)}</i>` : m === "total" ? `${x.line} <i>o${obAm(x.over)} u${obAm(x.under)}</i>` : `${g.h.abbr} ${obAm(x.home)} <i>${g.a.abbr} ${obAm(x.away)}</i>`}</b></div>`; };
  const fairTxt = fair == null ? "–" : m === "spread" ? `${g.h.abbr} ${obLn(fair)}` : m === "total" ? String(fair) : `${g.h.abbr} ${pjPct(fair)}`;
  const body = S.length ? `${obChart(S, m, fair, e.seen)}
      <div class="ob-sum"><div><span>Open</span><b>${fmt(S[0])}</b></div><div><span>Now</span><b>${fmt(S[S.length - 1])}</b></div><div><span>Pikt</span><b>${esc(fairTxt)}</b></div></div>
      <div class="sec">Books now</div><div class="ob-bk">${book("DK", "DraftKings")}${book("FD", "FanDuel")}</div>
      <div class="sec">Every move</div><div class="ob-log">${S.slice().reverse().slice(0, 20).map((s, i, a) => { const prev = a[i + 1];
        const dir = prev ? Math.sign(s[1] - prev[1]) : 0;   // which way, not good or bad: arrows, no red / green
        return `<div><span>${esc(obTime(s[0]))}${i === a.length - 1 && S.length === a.length ? " · open" : ""}</span><b>${dir ? `<em class="ob-ar">${dir > 0 ? "▲" : "▼"}</em>` : ""}${fmt(s)}</b></div>`; }).join("")}</div>`
    : `<div class="bk-empty">No line history for this market yet. Snapshots are taken every hour from when the books post the game.</div>`;
  pjSheet(`<div class="ps-h ob-sh" style="--tc:${esc(g.h.color || "#556")}">${pjLogo(g.a, "ob-lg")}${pjLogo(g.h, "ob-lg")}<div><div class="sh-t">${esc(g.a.abbr)} @ ${esc(g.h.abbr)}</div><div class="sh-s">${esc(g.time || "")} · line history</div></div></div>
    ${seg}${body}<div class="hint">The line is the DraftKings + FanDuel consensus, checked every hour. A home spread falling (−3 to −4) means the market moved toward the home side. Pikt is the model's own number, drawn dashed.</div>`);
  document.querySelectorAll("#sheet [data-obsm]").forEach(b => b.onclick = () => { OB.m = b.dataset.obsm; obOpen(gid); });
}
function obWire(v) {
  v.querySelectorAll("[data-obm]").forEach(b => b.onclick = () => { OB.m = b.dataset.obm; pjRender(); });
  v.querySelectorAll("[data-obs]").forEach(b => b.onclick = () => { OB.sort = b.dataset.obs; pjRender(); });
  v.querySelectorAll("[data-lm]").forEach(b => b.onclick = e => { e.stopPropagation(); obOpen(b.dataset.lm); });
}
