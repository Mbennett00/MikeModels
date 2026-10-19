// Game simulator shell shared by the NFL and NHL sims: the matchup picker, a sportsbook priced from simulated games, the
// live game as a cartoon battle, the final with its tabs and settled bets, and the 1,000-game mode. Each page defines
// SIMX: its data, its engine and how its own pieces (field or rink, box score, props) look.
"use strict";
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const R = Math.random;
const pick = (arr, w) => { let t = 0; for (const x of w) t += x; let r = R() * t; for (let i = 0; i < arr.length; i++) { r -= w[i]; if (r <= 0) return arr[i]; } return arr[arr.length - 1]; };
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const expo = () => -Math.log(1 - R());
const norm = () => { let u = 0, v = 0; while (!u) u = R(); while (!v) v = R(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
const lastName = n => { const w = String(n).split(" "); return w.length > 1 && /^(jr\.?|sr\.?|ii|iii|iv)$/i.test(w[w.length - 1]) ? w[w.length - 2] : w[w.length - 1]; };
const sxPct = p => `${Math.round(100 * p)}%`;
// a team colour that reads on the light background: too-light colours give way to the second colour or get darker
function sxVis(c, alt) {
  const lum = h => { const m = /^#?([0-9a-f]{6})$/i.exec(h || ""); if (!m) return -1; const n = parseInt(m[1], 16); return (.2126 * (n >> 16) + .7152 * (n >> 8 & 255) + .0722 * (n & 255)) / 255; };
  if (lum(c) < 0) return "#7a8aa0"; if (lum(c) <= .78) return c; if (lum(alt) >= 0 && lum(alt) <= .78) return alt;
  const n = parseInt(c.replace("#", ""), 16), mix = v => Math.round(v * .55);
  return `rgb(${mix(n >> 16)},${mix(n >> 8 & 255)},${mix(n & 255)})`;
}
const SX = {mode: "live", sim: null, n: 0, speed: 1, playing: true, tab: "sum", timer: null, multi: null, book: null, settled: null};
const ICON = {
  back: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>`,
  pause: `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>`,
  play: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L8.5 4.64A1 1 0 0 0 7 5.5z"/></svg>`,
  skip: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 6.2v11.6a.8.8 0 0 0 1.2.7l8.3-5.8a.8.8 0 0 0 0-1.4L5.2 5.5a.8.8 0 0 0-1.2.7zM13 6.2v11.6a.8.8 0 0 0 1.2.7l8.3-5.8a.8.8 0 0 0 0-1.4l-8.3-5.8a.8.8 0 0 0-1.2.7z"/></svg>`,
};

// ---------- small shared pieces ----------
function sxNoLogo(img) { const s = document.createElement("span"); s.className = "sx-code " + img.className.replace("sx-logo", ""); s.textContent = img.dataset.ab || ""; img.replaceWith(s); }
const sxLogo = t => t.logo ? `<img class="sx-logo" src="${esc(t.logo)}" alt="" data-ab="${esc(t.ab)}" onerror="sxNoLogo(this)">` : `<span class="sx-code sx-logo">${esc(t.ab)}</span>`;
// team stat comparison: [label, away value, home value, higher is better (true), lower is better (false) or neither (null), shown away, shown home]
function sxCompare(sim, rows) {
  const {T} = sim;
  return `<div class="sx-card sx-cmp">${rows.map(([l, va, vh, hib, sa, sh]) => {
    const tot = Math.abs(va) + Math.abs(vh), wa = hib == null || va === vh ? "" : (va > vh) === hib ? "w" : "l", wh = wa === "w" ? "l" : wa === "l" ? "w" : "";
    return `<div class="sx-cr"><div><b class="${wa}">${sa ?? va}</b><span>${l}</span><b class="${wh}">${sh ?? vh}</b></div>
      <div class="sx-bar"><i style="flex:${tot ? Math.abs(va) / tot : .5};background:${esc(T.a.color)}"></i><i style="flex:${tot ? Math.abs(vh) / tot : .5};background:${esc(T.h.color)}"></i></div></div>`; }).join("")}</div>`;
}
// line score: columns are periods, then the total
function sxLineScore(sim, heads, cols) {
  return `<div class="sx-card"><table class="sx-ls"><tr><th></th>${heads.map(h => `<th>${h}</th>`).join("")}<th>T</th></tr>${["a", "h"].map(k => `<tr><td>${sxLogo(sim.T[k])}${esc(sim.T[k].ab)}</td>${cols[k].map(v => `<td>${v}</td>`).join("")}<td class="t">${sim.final[k]}</td></tr>`).join("")}</table></div>`;
}
const sxTable = (head, rows) => rows.length ? `<table class="sx-tb"><tr>${head.map(h => `<th>${h}</th>`).join("")}</tr>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</table>` : "";
const sxHead = t => `<div class="sx-bh">${sxLogo(t)}${esc(t.full || t.name)}</div>`;
function sxTops(cards) {   // three spotlight players: {label, name, img, team, line}
  return `<div class="sx-tops">${cards.map(c => `<div class="sx-top3" style="--c:${esc(c.team.color)}"><i>${esc(c.label)}</i>${c.img ? `<img class="hs" src="${esc(c.img)}" alt="" onerror="this.src='${esc(c.team.logo)}'">` : `<img class="hs" src="${esc(c.team.logo)}" alt="">`}<b>${esc(c.name)}</b><span>${esc(c.team.ab)} · ${c.line}</span></div>`).join("")}</div>`;
}
const sxSec = (text, t) => `<div class="sx-sec">${t ? sxLogo(t) : ""}${esc(text)}</div>`;
function sxRow(e, sim) {
  if (e.kind === "sec") return sxSec(e.text, e.side && sim.T[e.side]);
  return `<div class="sx-r ${e.sc ? "sc" : ""} ${e.to ? "to" : ""}"><i>${esc(e.pl)} ${esc(e.t)}</i><span>${e.dd ? `<span class="sx-dd">${esc(e.dd)}</span>` : ""}${e.text}</span>${e.sc ? `<em>${e.score.a}–${e.score.h}</em>` : ""}</div>`;
}

// ---------- the wallet: virtual coins, kept on this device ----------
const START_COINS = 10000;
const BK = (() => { try { const v = JSON.parse(localStorage.getItem("pikt-simbook") || "null"); if (v && typeof v.coins === "number") return v; } catch (e) {} return {coins: START_COINS, bets: []}; })();
const bkSave = () => { try { localStorage.setItem("pikt-simbook", JSON.stringify(BK)); } catch (e) {} };
// a bet left open by a game that was never finished (page closed mid-game) is voided and its stake returned
for (const b of BK.bets) if (b.st === "open") { b.st = "void"; BK.coins += b.stake; }
BK.bets = BK.bets.slice(-60); bkSave();
const fmtC = n => Math.round(n).toLocaleString();
const am = d => d >= 2 ? `+${Math.round((d - 1) * 100)}` : `${Math.round(-100 / (d - 1))}`;
const VIG = 1.045;   // the house edge on every price
const priceOf = (p, legs = 1) => Math.max(1.02, 1 / (clamp(p, .005, .995) * VIG * Math.pow(1.03, legs - 1)));
function coinsPill(pop) { const el = $("#coins"); if (el) { el.innerHTML = `<i class="coin"></i>${fmtC(BK.coins)}`; if (pop) { el.classList.remove("pop"); void el.offsetWidth; el.classList.add("pop"); } } }

// ---------- the book: 2,000 simulated games price the matchup; the game you then watch is a fresh one ----------
const median = a => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : 0; };
const half = v => Math.floor(v) + .5;
// the half-point line that splits the simulated values closest to 50/50
const fairLine = vals => { const m = Math.floor(median(vals)); let best = m + .5, gap = 9;
  for (const L of [m - 1.5, m - .5, m + .5, m + 1.5]) { if (L < 0) continue; const p = vals.filter(v => v > L).length / vals.length; if (Math.abs(p - .5) < gap) { gap = Math.abs(p - .5); best = L; } }
  return best; };
function bkMarkets(B) {
  const D = B.res, T = B.T, n = D.length, sel = {}, groups = [];
  const add = (g, s) => { sel[s.id] = s; g.items.push(s); };
  const price = s => { let w = 0, l = 0; for (const d of D) { const r = s.test(d); if (r === 1) w++; else if (r === 0) l++; } s.p = w / Math.max(1, w + l); s.dec = priceOf(s.p); return s; };
  // moneyline (a tie pushes), spread, total
  const ml = {name: "Moneyline", items: []}; groups.push(ml);
  for (const k of ["a", "h"]) add(ml, price({id: `ml_${k}`, mk: "ml", lab: `${T[k].ab} to win`, top: T[k].ab, test: d => d.s.a === d.s.h ? null : (d.s[k] > d.s[k === "a" ? "h" : "a"] ? 1 : 0)}));
  const marg = D.map(d => d.s.h - d.s.a), sp = SIMX.spreadLine ? SIMX.spreadLine(B) : -fairLine(marg.map(v => v + 100)) + 100, spg = {name: SIMX.spreadName || "Spread", items: []}; groups.push(spg);
  const fmtS = v => v > 0 ? `+${v}` : `${v}`;
  add(spg, price({id: "sp_h", mk: "sp", lab: `${T.h.ab} ${fmtS(sp)}`, top: `${T.h.ab} ${fmtS(sp)}`, test: d => d.s.h - d.s.a + sp > 0 ? 1 : 0}));
  add(spg, price({id: "sp_a", mk: "sp", lab: `${T.a.ab} ${fmtS(-sp)}`, top: `${T.a.ab} ${fmtS(-sp)}`, test: d => d.s.a - d.s.h - sp > 0 ? 1 : 0}));
  spg.items.reverse();
  const tl = fairLine(D.map(d => d.s.a + d.s.h)), tg = {name: "Total", items: []}; groups.push(tg);
  add(tg, price({id: "to_o", mk: "to", lab: `Over ${tl}`, top: `Over ${tl}`, test: d => d.s.a + d.s.h > tl ? 1 : 0}));
  add(tg, price({id: "to_u", mk: "to", lab: `Under ${tl}`, top: `Under ${tl}`, test: d => d.s.a + d.s.h < tl ? 1 : 0}));
  // player props from the page: over/under at the simulated median, or yes-only (anytime scorer)
  const pg = {name: "Player props", items: [], props: true}; groups.push(pg);
  for (const pr of SIMX.props(B)) {
    const vals = D.map(pr.get);
    if (pr.kind === "yes") { const s = price({id: pr.id, mk: pr.id, lab: `${pr.who} ${pr.stat}`, top: "Yes", who: pr.who, team: pr.team, stat: pr.stat, kind: "yes", test: d => pr.get(d) >= 1 ? 1 : 0});
      if (s.p > .02 && s.p < .95) add(pg, s); continue; }
    const ln = fairLine(vals);
    for (const [side, sign] of [["o", 1], ["u", -1]]) add(pg, price({id: `${pr.id}_${side}`, mk: pr.id, lab: `${pr.who} ${side === "o" ? "over" : "under"} ${ln} ${pr.stat}`, top: `${side === "o" ? "O" : "U"} ${ln}`, who: pr.who, team: pr.team, stat: pr.stat, kind: "ou", side, ln,
      test: d => (pr.get(d) - ln) * sign > 0 ? 1 : 0}));
  }
  return {sel, groups};
}
// a same-game parlay is priced from how often all its legs won together in the 2,000 games
function bkParlayP(B, ids) {
  const legs = ids.map(id => B.mk.sel[id]); let w = 0, n = 0;
  for (const d of B.res) { const r = legs.map(s => s.test(d)); if (r.includes(null)) continue; n++; if (r.every(v => v === 1)) w++; }
  return w / Math.max(1, n);
}
function openBook(a, h) {
  clearTimeout(SX.timer); SX.multi = null; SX.sim = null; SX.settled = null;
  const T = {a: SIMX.team(a), h: SIMX.team(h)}, gid = `${a}|${h}|${Date.now()}`;
  SX.book = {a, h, T, gid, N: SIMX.bookN || 2000, done: 0, res: [], mk: null, slip: [], parlay: false, stake: 100, msg: ""};
  history.replaceState(null, "", `?away=${a}&home=${h}`); render(); window.scrollTo(0, 0);
  const B = SX.book;
  setTimeout(() => { SIMX.prepare(a, h);
    const step = () => { if (SX.book !== B) return; const end = Math.min(B.N, B.done + SIMX.multiChunk * 2);
      for (; B.done < end; B.done++) B.res.push(SIMX.digest(SIMX.simulate(a, h, true)));
      if (B.done >= B.N) B.mk = bkMarkets(B);
      render(); if (B.done < B.N) SX.timer = setTimeout(step, 0); };
    step(); }, 30);
}
const myBets = gid => BK.bets.filter(b => b.gid === gid);
function sxBook() {
  const B = SX.book, T = B.T, orb = k => `<div class="orb" style="--c:${esc(T[k].color)}">${sxLogo(T[k])}</div>`;
  const vs = `<div class="bk-vs"><div class="t">${orb("a")}<b>${esc(T.a.name)}</b><span>${esc(SIMX.teamSub({T}, null, "a", false))}</span></div><div class="vs">VS</div><div class="t">${orb("h")}<b>${esc(T.h.name)}</b><span>${esc(SIMX.teamSub({T}, null, "h", false))}</span></div></div>`;
  if (!B.mk) return `<section class="sx-card">${vs}<div style="padding:14px"><div class="sx-note" style="margin:0">${B.done ? `The house is simulating ${B.N.toLocaleString()} games to set the odds… ${B.done.toLocaleString()}` : "Getting the teams ready…"}</div><div class="sx-prog"><i style="width:${(100 * B.done / B.N).toFixed(1)}%"></i></div></div></section>`;
  const on = id => B.slip.includes(id) ? "on" : "";
  const btn = s => `<button class="bk-px ${on(s.id)}" data-bet="${s.id}"><small>${esc(s.top)}</small><b>${am(s.dec)}</b></button>`;
  const groups = B.mk.groups.map(g => {
    if (!g.props) return `<div class="bk-mk"><h4>${esc(g.name)}</h4><div class="bk-row">${g.items.map(btn).join("")}</div></div>`;
    const by = {}; for (const s of g.items) (by[s.mk] = by[s.mk] || []).push(s);
    const rows = Object.values(by).map(L => L[0].kind === "yes"
      ? `<div class="bk-row y"><span>${esc(L[0].who)} <i>${esc(T[L[0].team].ab)} · ${esc(L[0].stat)}</i></span>${btn(L[0])}</div>`
      : `<div class="bk-row p"><span>${esc(L[0].who)} <i>${esc(L[0].stat)}</i></span>${L.map(btn).join("")}</div>`).join("");
    return rows ? `<div class="bk-mk"><h4>${esc(g.name)} <span class="bk-tag">SIM-PRICED</span></h4>${rows}</div>` : "";
  }).join("");
  const mine = myBets(B.gid);
  return `<section class="sx-card">${vs}<div class="bk-intro">A wild <b>${esc(T.a.name)}</b> team appears! The house simulated <b>${B.N.toLocaleString()} games</b> of this matchup to set every price. Your game will be a brand-new one.</div></section>
    <div class="sx-h"><b>Odds board</b><span>Tap a price to add it</span></div>
    <section class="sx-card">${groups}</section>
    ${mine.length ? `<div class="sx-h"><b>Your bets on this game</b><span>${mine.length} placed</span></div><section class="sx-card bk-bets">${mine.map(betRow).join("")}</section>` : ""}
    <p class="sx-note">Coins are play money and stay on this device. Prices include a small house edge. Same-game parlays are priced from how often the legs hit together in the simulated games.</p>
    ${B.slip.length ? slipHtml(B) : `<div class="sx-act"><button class="sx-btn go" data-start>Play ball!${mine.length ? ` (${mine.length} bet${mine.length > 1 ? "s" : ""})` : ""}</button><button class="sx-btn ghost" data-new>Back</button></div>`}`;
}
function slipHtml(B) {
  const legs = B.slip.map(id => B.mk.sel[id]), par = B.parlay && legs.length > 1;
  const dec = par ? priceOf(bkParlayP(B, B.slip), legs.length) : null;
  const stake = Math.min(B.stake, BK.coins), total = par ? stake : stake * legs.length;
  const win = par ? stake * (dec - 1) : legs.reduce((s, x) => s + stake * (x.dec - 1), 0);
  return `<div class="bk-slip"><div><div class="bk-sh"><span class="n">${legs.length}</span>Bet slip<button data-clear>Clear</button></div>
    <div class="bk-legs">${legs.map(s => `<div class="bk-leg"><span>${esc(s.lab)}</span><b>${par ? "" : am(s.dec)}</b><button data-rm="${s.id}">×</button></div>`).join("")}</div>
    <div class="bk-ctl"><div class="bk-modes"><button class="${par ? "" : "on"}" data-par="0">${legs.length > 1 ? "Singles" : "Single"}</button><button class="${par ? "on" : ""}" data-par="1" ${legs.length < 2 ? "disabled" : ""}>Parlay${par ? ` ${am(dec)}` : ""}</button></div>
      <div class="bk-stakes">${[50, 100, 250, 500, 1000].map(v => `<button class="${B.stake === v ? "on" : ""}" data-stake="${v}">${v >= 1000 ? v / 1000 + "k" : v}</button>`).join("")}<button class="${B.stake === -1 ? "on" : ""}" data-stake="-1">Max</button></div>
      <div class="bk-sum"><span>Stake <i class="coin"></i> ${fmtC(total)}</span><span>To win <b>${fmtC(win)}</b></span></div>
      ${B.msg ? `<div class="bk-sum" style="color:var(--berry)">${esc(B.msg)}</div>` : ""}
      <button class="sx-btn" data-place ${total > BK.coins || total <= 0 ? "disabled" : ""}>Place bet${!par && legs.length > 1 ? "s" : ""}</button></div></div></div>`;
}
function placeBets() {
  const B = SX.book, legs = B.slip.map(id => B.mk.sel[id]); if (!legs.length) return;
  const stake = B.stake === -1 ? Math.floor(BK.coins / (B.parlay && legs.length > 1 ? 1 : legs.length)) : Math.min(B.stake, BK.coins);
  const mk = (L, dec) => ({id: Math.random().toString(36).slice(2), gid: B.gid, game: `${B.T.a.ab} @ ${B.T.h.ab}`, legs: L.map(s => ({id: s.id, lab: s.lab})), stake, dec, st: "open", at: Date.now()});
  const bets = B.parlay && legs.length > 1 ? [mk(legs, priceOf(bkParlayP(B, B.slip), legs.length))] : legs.map(s => mk([s], s.dec));
  const total = bets.reduce((s, b) => s + b.stake, 0);
  if (!stake || total > BK.coins) { B.msg = "Not enough coins for that"; render(); return; }
  BK.coins -= total; BK.bets.push(...bets); bkSave(); B.slip = []; B.msg = ""; coinsPill(true); render();
}
const betRow = b => { const icon = {won: "✓", lost: "✗", push: "↺", void: "↺", open: "★"}[b.st] || "★", pay = b.st === "won" ? `+${fmtC(b.pay - b.stake)}` : b.st === "lost" ? fmtC(b.stake) : b.st === "push" || b.st === "void" ? "refund" : `${fmtC(b.stake)} → ${fmtC(b.stake * b.dec)}`;
  return `<div class="bk-bet ${b.st === "open" ? "live" : b.st}"><span class="ic">${icon}</span><div><b>${b.legs.length > 1 ? `${b.legs.length}-leg parlay ${am(b.dec)}` : `${esc(b.legs[0].lab)} ${am(b.dec)}`}</b><span>${b.legs.length > 1 ? b.legs.map(l => esc(l.lab)).join(" · ") : `Stake ${fmtC(b.stake)}`}</span></div><em>${pay}</em></div>`; };
// settle this game's bets against the game that was just played
function settle() {
  const B = SX.book; if (!B || !B.mk || SX.settled === B.gid) return;
  SX.settled = B.gid;
  const d = SIMX.digest(SX.sim); let net = 0, won = 0;
  for (const b of myBets(B.gid)) {
    if (b.st !== "open") continue;
    const r = b.legs.map(l => B.mk.sel[l.id] ? B.mk.sel[l.id].test(d) : null);
    if (r.includes(0)) { b.st = "lost"; b.pay = 0; net -= b.stake; }
    else if (r.every(v => v === null)) { b.st = "push"; b.pay = b.stake; BK.coins += b.stake; }
    else { const live = b.legs.filter((l, i) => r[i] === 1); const dec = r.includes(null) && b.legs.length > 1 ? live.reduce((s, l) => s * B.mk.sel[l.id].dec, 1) : b.dec;
      b.st = "won"; b.pay = Math.round(b.stake * dec); BK.coins += b.pay; net += b.pay - b.stake; won++; }
  }
  if (BK.coins < 50 && !BK.bets.some(b => b.st === "open")) BK.refill = true;
  bkSave(); coinsPill(true);
  if (won) confetti();
}
function confetti() {
  const c = document.createElement("div"); c.className = "conf";
  const col = ["#ffd23f", "#ff5a6e", "#3b82f6", "#22c55e", "#8b5cf6"];
  c.innerHTML = Array.from({length: 46}, () => `<i style="left:${Math.random() * 100}%;background:${col[Math.floor(Math.random() * 5)]};animation-delay:${(Math.random() * .6).toFixed(2)}s;animation-duration:${(1.4 + Math.random()).toFixed(2)}s"></i>`).join("");
  document.body.appendChild(c); setTimeout(() => c.remove(), 3200);
}
// how each of this game's bets stands right now (game lines only; props settle at the final)
function liveChips(sim, e) {
  const B = SX.book; if (!B || B.gid !== sim.gid) return "";
  const bets = myBets(B.gid); if (!bets.length) return "";
  const s = e ? e.score : {a: 0, h: 0}, d = {s, ot: false, p: {}};
  return `<div class="bk-strip">${bets.map(b => { const L = b.legs.map(l => B.mk.sel[l.id]), gameOnly = L.every(x => ["ml", "sp", "to"].includes(x.mk));
    const st = gameOnly ? (L.every(x => x.test(d) === 1) ? "up" : "dn") : "";
    return `<span class="bk-chip ${st}"><i></i>${b.legs.length > 1 ? `Parlay ${am(b.dec)}` : esc(b.legs[0].lab)}</span>`; }).join("")}</div>`;
}

// ---------- picker ----------
function sxPicker() {
  const T = SIMX.teams(), G = SIMX.slate(), u = new URLSearchParams(location.search), g0 = G[0];
  const a = T.some(t => t.ab === u.get("away")) ? u.get("away") : g0 ? g0.a.ab : T[0].ab, h = T.some(t => t.ab === u.get("home")) ? u.get("home") : g0 ? g0.h.ab : T[1].ab;
  const opt = sel => T.map(t => `<option value="${t.ab}" ${t.ab === sel ? "selected" : ""}>${esc(t.full || t.name)}</option>`).join("");
  const rows = G.map(g => `<button class="sx-g" data-go="${g.a.ab}|${g.h.ab}">
      <span class="sx-gt">${sxLogo(g.a)}<b>${esc(g.a.ab)}</b><i>${SIMX.fmt(g.pa)}</i></span>
      <span class="sx-gm"><em>${esc(g.when || "")}</em><span class="sx-wp"><i style="width:${Math.round(84 * (1 - g.pHome))}px;background:${esc(g.a.color)}"></i><i style="background:${esc(g.h.color)}"></i></span><small>${sxPct(1 - g.pHome)} · ${sxPct(g.pHome)}</small></span>
      <span class="sx-gt r"><i>${SIMX.fmt(g.ph)}</i><b>${esc(g.h.ab)}</b>${sxLogo(g.h)}</span></button>`).join("");
  const settled = BK.bets.filter(b => b.st !== "open").slice(-6).reverse();
  return `${BK.refill ? `<section class="sx-card" style="margin-top:16px;padding:14px"><b>Out of coins!</b><div class="sx-note" style="margin:6px 0 0">Here's a fresh stack to keep playing.</div><button class="sx-btn" data-refill>Get 5,000 coins</button></section>` : ""}
    <div class="sx-seg sx-mode">${[["live", "Bet & play"], ["multi", "Sim 1,000 games"]].map(([k, l]) => `<button class="${SX.mode === k ? "on" : ""}" data-mode="${k}">${l}</button>`).join("")}</div>
    ${G.length ? `<div class="sx-h"><b>${esc(SIMX.slateLabel())}</b><span>Model projection · win chance</span></div><div class="sx-list">${rows}</div>` : ""}
    <div class="sx-h"><b>Any matchup</b></div>
    <div class="sx-card sx-custom"><div class="sx-sel"><label>Away<select id="sa">${opt(a)}</select></label><span>VS</span><label>Home<select id="sh">${opt(h)}</select></label></div>
      <button class="sx-btn" id="go">${SX.mode === "multi" ? "Sim 1,000 games" : "Open the odds"}</button></div>
    ${settled.length ? `<div class="sx-h"><b>Recent bets</b><span><i class="coin"></i> ${fmtC(BK.coins)}</span></div><section class="sx-card bk-bets">${settled.map(b => betRow(b).replace("<div><b>", `<div><b>${esc(b.game || "")} · `)).join("")}</section>` : ""}
    <p class="sx-note">${SIMX.note}</p>`;
}

// ---------- live: the battle ----------
function hpColor(p) { return p > .5 ? "#22c55e" : p > .2 ? "#f5b400" : "#ff5a6e"; }
function sxBattle(sim, e, n) {
  const T = sim.T, sc = e ? e.score : {a: 0, h: 0}, pH = e && SIMX.liveP ? SIMX.liveP(sim, e) : sim.pH ?? .5;
  const last = [...sim.ev.slice(0, n)].reverse().find(x => x.kind !== "sec");
  const cur = sim.ev[n - 1] || {}, hitK = cur.sc ? cur.side : null, hurtK = cur.sc ? (cur.side === "a" ? "h" : "a") : cur.to ? cur.side : null;
  const card = k => { const p = k === "h" ? pH : 1 - pH, ty = SIMX.type ? SIMX.type(T[k]) : null;
    return `<div class="bt-card ${k}"><div class="bt-nm"><b>${esc(T[k].ab)}</b>${ty ? `<span class="ty" style="background:${ty.c}">${esc(ty.n)}</span>` : ""}<i>${esc(SIMX.teamSub(sim, e, k, false))}</i></div>
      <div class="bt-hp"><span>WIN</span><div><i style="width:${(100 * p).toFixed(1)}%;background:${hpColor(p)}"></i></div></div>
      <div class="bt-sc"><em>${sxPct(p)} to win</em><strong>${sc[k]}</strong></div></div>`; };
  const mon = k => `<div class="bt-mon ${k} ${hitK === k ? "hit" : ""} ${hurtK === k ? "hurt" : ""}" style="--c:${esc(T[k].color)}"><div class="orb">${sxLogo(T[k])}</div>${last && last.side === k && !last.sc ? '<span class="bt-poss">★</span>' : ""}</div>`;
  const mv = last && SIMX.move ? SIMX.move(last, sim) : null;
  const text = last ? `<div class="bt-text ${last.sc ? "big" : ""}">${mv ? `<span class="mv">${esc(mv.mv)}</span>` : ""}<p>${last.text}</p>${mv && mv.eff ? `<span class="eff">${esc(mv.eff)}</span>` : ""}</div>`
    : `<div class="bt-text"><span class="mv">A WILD ${esc(T.a.name.toUpperCase())} TEAM APPEARS!</span><p>${esc(SIMX.kickText)}…</p></div>`;
  return `<div class="bt"><span class="bt-clock">${esc(e ? `${e.pl} ${e.t}` : `${SIMX.startPl} ${SIMX.startClock}`)}</span>${card("a")}${mon("a")}${mon("h")}${card("h")}</div>${text}`;
}
function sxLive() {
  const sim = SX.sim, shown = sim.ev.slice(0, SX.n), cur = shown[shown.length - 1];
  const sp = [[1, "1×"], [3, "3×"], [10, "10×"]].map(([s, l]) => `<button class="${SX.speed === s ? "on" : ""}" data-sp="${s}">${l}</button>`).join("");
  return `<section class="sx-card">${sxBattle(sim, cur, SX.n)}${SIMX.stage(sim, cur, SX.n)}</section>
    ${liveChips(sim, cur)}
    <div class="sx-ctl"><div class="sx-seg">${sp}</div><button class="sx-ib" data-play aria-label="${SX.playing ? "Pause" : "Play"}">${SX.playing ? ICON.pause : ICON.play}</button><button class="sx-ib" data-skip>Final ${ICON.skip}</button></div>
    <div class="sx-card sx-feed">${shown.slice(-50).reverse().map(e => sxRow(e, sim)).join("")}</div>`;
}

// ---------- final ----------
function sxFinal() {
  const sim = SX.sim, T = sim.T, f = sim.final, w = f.a === f.h ? null : f.a > f.h ? "a" : "h", tabs = [["sum", "Summary"], ["box", "Box score"], ["pbp", "Plays"]];
  settle();
  const body = SX.tab === "box" ? SIMX.box(sim) : SX.tab === "pbp" ? `<div class="sx-card sx-feed">${sim.ev.map(e => sxRow(e, sim)).join("")}</div>` : SIMX.summary(sim);
  const team = k => `<div class="t ${k} ${w && w !== k ? "l" : ""}">${sxLogo(T[k])}<b>${esc(T[k].ab)}</b><strong>${f[k]}</strong></div>`;
  const bets = SX.book && SX.book.gid === sim.gid ? myBets(sim.gid) : [];
  const net = bets.reduce((s, b) => s + (b.st === "won" ? b.pay - b.stake : b.st === "lost" ? -b.stake : 0), 0);
  return `<section class="sx-card"><div class="sx-win"><div class="tro">${w ? "🏆" : "🤝"}</div><b>${w ? `${esc(T[w].name)} win!` : "It's a draw!"}</b><span>${esc(SIMX.finalLab(sim))}</span></div>
      <div class="sx-fsc">${team("a")}<span class="m">FINAL</span>${team("h")}</div></section>
    ${bets.length ? `<div class="sx-h"><b>Your bets</b><span style="color:${net >= 0 ? "var(--leaf)" : "var(--berry)"};font-weight:700">${net >= 0 ? "+" : ""}${fmtC(net)} coins</span></div><section class="sx-card bk-bets">${bets.map(betRow).join("")}</section>` : ""}
    <div class="sx-seg sx-tabs">${tabs.map(([k, l]) => `<button class="${SX.tab === k ? "on" : ""}" data-tab="${k}">${l}</button>`).join("")}</div>
    ${body}
    <div class="sx-act"><button class="sx-btn" data-rebook>Bet a rematch</button><button class="sx-btn ghost" data-new>New matchup</button></div>`;
}

// ---------- 1,000 games ----------
function sxMultiView() {
  const M = SX.multi, T = M.T;
  if (M.done < M.N) return `<section class="sx-card" style="padding:18px 14px"><div class="sx-fsc" style="padding:0">${["a", "h"].map(k => `<div class="t ${k}">${sxLogo(T[k])}<b>${esc(T[k].ab)}</b></div>`).join('<span class="m">VS</span>')}</div>
      <div class="sx-prog"><i style="width:${(100 * M.done / M.N).toFixed(1)}%"></i></div><div class="sx-note" style="margin:0">${M.done ? `Simulated ${M.done.toLocaleString()} of ${M.N.toLocaleString()} games…` : "Tuning the sim to the model's projection for this matchup…"}</div></section>`;
  const D = M.res, n = D.length, wa = D.filter(d => d.s.a > d.s.h).length / n, wh = D.filter(d => d.s.h > d.s.a).length / n, tie = 1 - wa - wh;
  const avg = k => D.reduce((x, d) => x + (d.r || d.s)[k], 0) / n, ex = M.exp;   // NHL compares regulation goals, as the model does
  const sc = {}; for (const d of D) { const k = `${d.s.a}–${d.s.h}`; sc[k] = (sc[k] || 0) + 1; }
  const top = Object.entries(sc).sort((x, y) => y[1] - x[1]).slice(0, 8);
  const bins = SIMX.marginBins, hist = bins.map(([lo, hi]) => D.filter(d => { const m = d.s.h - d.s.a; return m >= lo && m <= hi; }).length), hmax = Math.max(...hist, 1);
  const ot = D.filter(d => d.ot).length / n;
  return `<section class="sx-card"><div class="sx-mw">${["a", "h"].map(k => `<div class="${k}"><span class="tn">${sxLogo(T[k])}${esc(T[k].ab)}</span><strong>${sxPct(k === "a" ? wa : wh)}</strong><span>${M.pModel != null ? `Model ${sxPct(k === "a" ? 1 - M.pModel : M.pModel)}` : "win"}</span></div>`).join("")}</div>
      <div class="sx-mbar"><i style="flex:${wa};background:${esc(T.a.color)}"></i>${tie > .001 ? `<i style="flex:${tie};background:#c3c8d8"></i>` : ""}<i style="flex:${wh};background:${esc(T.h.color)}"></i></div>
      <div class="sx-kv"><div><i>${esc(SIMX.avgLabel || "Avg score")}</i><b>${SIMX.fmt(avg("a"))} – ${SIMX.fmt(avg("h"))}</b><span>Model ${SIMX.fmt(ex[0])} – ${SIMX.fmt(ex[1])}</span></div>
        <div><i>Avg total</i><b>${SIMX.fmt(avg("a") + avg("h"))}</b><span>Model ${SIMX.fmt(ex[0] + ex[1])}</span></div>
        <div><i>${esc(SIMX.otLabel)}</i><b>${sxPct(ot)}</b><span>${tie > .001 ? `Ties ${sxPct(tie)}` : `${n.toLocaleString()} games`}</span></div></div></section>
    <div class="sx-h"><b>Most common finals</b><span>${esc(T.a.ab)}–${esc(T.h.ab)}</span></div>
    <div class="sx-chips">${top.map(([s, c]) => `<span>${s}<i>${(100 * c / n).toFixed(1)}%</i></span>`).join("")}</div>
    <div class="sx-h"><b>Winning margin</b><span>How often each result came up</span></div>
    <div class="sx-card"><div class="sx-hist">${hist.map((c, i) => { const [lo, hi] = bins[i], mid = (lo + hi) / 2; return `<i title="${c}" style="height:${(100 * c / hmax).toFixed(1)}%;background:${esc(mid < 0 ? T.a.color : mid > 0 ? T.h.color : "#c3c8d8")}"></i>`; }).join("")}</div>
      <div class="sx-hx"><span>${esc(T.a.ab)} by ${SIMX.marginEdge}+</span><span>${esc(SIMX.marginMid)}</span><span>${esc(T.h.ab)} by ${SIMX.marginEdge}+</span></div></div>
    ${SIMX.multiPlayers(M)}
    <div class="sx-act"><button class="sx-btn" data-bookm>Bet this game</button><button class="sx-btn ghost" data-new>New matchup</button></div>`;
}
function sxRunMulti(a, h) {
  clearTimeout(SX.timer); SX.sim = null; SX.book = null;
  const T = {a: SIMX.team(a), h: SIMX.team(h)};
  SX.multi = {a, h, T, N: SIMX.multiN, done: 0, res: [], exp: SIMX.expected(a, h), pModel: SIMX.pModel(a, h)};
  history.replaceState(null, "", `?away=${a}&home=${h}&mode=multi`); render(); window.scrollTo(0, 0);
  const M = SX.multi;
  setTimeout(() => { SIMX.prepare(a, h);
    const step = () => { if (SX.multi !== M) return; const end = Math.min(M.N, M.done + SIMX.multiChunk);
      for (; M.done < end; M.done++) M.res.push(SIMX.digest(SIMX.simulate(a, h, true)));
      render(); if (M.done < M.N) SX.timer = setTimeout(step, 0); };
    step(); }, 30);
}

// ---------- flow ----------
function render() {
  const v = $("#view");
  v.innerHTML = SX.multi ? sxMultiView() : SX.sim ? (SX.n >= SX.sim.ev.length ? sxFinal() : sxLive()) : SX.book ? sxBook() : sxPicker();
  coinsPill();
  const on = (sel, f) => v.querySelectorAll(sel).forEach(b => b.onclick = () => f(b));
  on("[data-mode]", b => { SX.mode = b.dataset.mode; render(); });
  on("[data-go]", b => { const [a, h] = b.dataset.go.split("|"); go(a, h); });
  on("#go", () => go($("#sa").value, $("#sh").value));
  on("[data-refill]", () => { BK.coins += 5000; BK.refill = false; bkSave(); coinsPill(true); render(); });
  on("[data-bet]", b => { const B = SX.book, id = b.dataset.bet, s = B.mk.sel[id];
    if (B.slip.includes(id)) B.slip = B.slip.filter(x => x !== id);
    else { B.slip = B.slip.filter(x => B.mk.sel[x].mk !== s.mk); B.slip.push(id); }   // one side of each market
    if (B.slip.length < 2) B.parlay = false; B.msg = ""; render(); });
  on("[data-rm]", b => { SX.book.slip = SX.book.slip.filter(x => x !== b.dataset.rm); if (SX.book.slip.length < 2) SX.book.parlay = false; render(); });
  on("[data-clear]", () => { SX.book.slip = []; SX.book.parlay = false; render(); });
  on("[data-par]", b => { SX.book.parlay = b.dataset.par === "1"; render(); });
  on("[data-stake]", b => { SX.book.stake = +b.dataset.stake; render(); });
  on("[data-place]", () => placeBets());
  on("[data-start]", () => watch(SX.book.a, SX.book.h));
  on("[data-sp]", b => { SX.speed = +b.dataset.sp; SX.playing = true; play(); render(); });
  on("[data-play]", () => { SX.playing = !SX.playing; SX.playing ? play() : clearTimeout(SX.timer); render(); });
  on("[data-skip]", () => { clearTimeout(SX.timer); SX.n = SX.sim.ev.length; SX.tab = "sum"; render(); window.scrollTo(0, 0); });
  on("[data-tab]", b => { SX.tab = b.dataset.tab; render(); });
  on("[data-rebook]", () => openBook(SX.sim.a, SX.sim.h));
  on("[data-bookm]", () => openBook(SX.multi.a, SX.multi.h));
  on("[data-new]", () => { clearTimeout(SX.timer); SX.sim = null; SX.multi = null; SX.book = null; history.replaceState(null, "", location.pathname); render(); window.scrollTo(0, 0); });
}
function play() {
  clearTimeout(SX.timer);
  const step = () => { if (!SX.sim || !SX.playing) return; SX.n++; if (SX.n >= SX.sim.ev.length) SX.tab = "sum"; render(); if (SX.n >= SX.sim.ev.length) { window.scrollTo(0, 0); return; } SX.timer = setTimeout(step, 1000 / SX.speed); };
  SX.timer = setTimeout(step, 1000 / SX.speed);
}
function watch(a, h) {
  clearTimeout(SX.timer); SX.multi = null; SX.sim = null;
  history.replaceState(null, "", `?away=${a}&home=${h}`);
  $("#view").innerHTML = `<section class="sx-card" style="padding:18px 14px"><div class="sx-note" style="margin:0">${esc(SIMX.team(a).name)} and ${esc(SIMX.team(h).name)} take the field…</div><div class="sx-prog"><i style="width:60%"></i></div></section>`;
  window.scrollTo(0, 0);
  setTimeout(() => { SIMX.prepare(a, h); SX.sim = SIMX.simulate(a, h, false); SX.sim.gid = SX.book ? SX.book.gid : null; SX.sim.pH = SIMX.pModel(a, h);
    SX.n = 1; SX.playing = true; SX.tab = "sum"; render(); play(); }, 30);
}
// each matchup's tuning is kept per data release, so a matchup tunes once
function sxCalGet(sport, ver, key) { try { const v = JSON.parse(localStorage.getItem(`pikt-sim-${sport}`) || "{}"); return v.ver === String(ver) ? v.k[key] : null; } catch (e) { return null; } }
function sxCalPut(sport, ver, key, k) { try { const id = `pikt-sim-${sport}`, v = JSON.parse(localStorage.getItem(id) || "{}"), o = v.ver === String(ver) ? v : {ver: String(ver), k: {}}; o.k[key] = k; localStorage.setItem(id, JSON.stringify(o)); } catch (e) {} }
const go = (a, h) => { if (a === h) return; SX.mode === "multi" ? sxRunMulti(a, h) : openBook(a, h); };
function sxBoot() {
  const top = document.querySelector(".sx-top"); if (top && !$("#coins")) top.insertAdjacentHTML("beforeend", `<span class="sx-coins" id="coins"></span>`);
  coinsPill();
  const extra = SIMX.extraUrl ? fetch(SIMX.extraUrl + "?v=" + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null) : Promise.resolve(null);   // the sim's league, team and player profiles
  Promise.all([fetch(SIMX.dataUrl + "?v=" + Date.now()).then(r => r.json()), extra]).then(([d, x]) => {
    SIMX.init(d, x);
    if (!SIMX.teams().length) { $("#view").innerHTML = `<div class="empty"><div class="t">${esc(SIMX.emptyText)}</div></div>`; return; }
    const u = new URLSearchParams(location.search);
    if (u.get("mode") === "multi") SX.mode = "multi";
    render();
  }).catch(e => { console.error(e); $("#view").innerHTML = `<div class="empty"><div class="t">Couldn't load the data</div></div>`; });
}
