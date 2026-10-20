// ---------- 🪙 PIKT BOOK: virtual coins, priced by the model ----------
// Play money only. Every price carries a thin hold, like a real book. One wallet for the NHL, NFL and NBA pages (same origin, localStorage); bets are graded
// in the browser from ESPN's final scores and box scores, on whichever page is open.
// A selection (built by bkSel):
//   {key, sport, gid, kind: ml|spread|total|prop, side: home|away|over|under|yes, line, p, pick, mkt, game, start,
//    ev: {date: "YYYYMMDD", home, away, id}, pl: {name, id, team, stat, n}}
const BK = {key: "bz.book.v1", hold: 0.045, start: 10000, drop: 1000, reload: 10000, legs: 8};
const BK_REG = {};
const BK_LIVE_FRESH = 120e3;   // a live price older than this is pulled from the board and the slip   // key -> the latest selection drawn on screen (prices refresh with the model)
const bkDay = (t = Date.now()) => new Date(t).toLocaleDateString("en-CA", {timeZone: "America/New_York"});
const bkImp = p => Math.min(0.97, Math.max(0.03, p) * (1 + BK.hold));
const bkDec = p => Math.round(1e4 / bkImp(p)) / 1e4;
const bkAm = d => d >= 2 ? "+" + Math.round(100 * (d - 1)) : "−" + Math.round(100 / (d - 1));
const bkEvDate = s => bkDay(new Date(s).getTime()).replace(/-/g, "");
const bkHalf = x => Math.floor(x) + 0.5;   // the nearest hook below: lines never push
const bkN = n => Math.round(n).toLocaleString("en-US");
const BK_COIN = '<svg class="bk-c" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9.2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M9.6 16.9V7.3h3.5a2.75 2.75 0 0 1 0 5.5H9.6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>';

function bkLoad() {
  try { const s = JSON.parse(localStorage.getItem(BK.key)); if (s && typeof s.coins === "number" && Array.isArray(s.bets)) {
    if (!s.k10) { s.k10 = 1; s.coins += 9000; s.k10new = 1; }   // the bankroll went from 1,000 to 10,000: top up wallets made before that
    return Object.assign({slip: [], mode: "single", pstake: 0, drop: "", reload: "", view: "open"}, s); } } catch (e) {}
  return {coins: BK.start, bets: [], slip: [], mode: "single", pstake: 0, drop: "", reload: "", view: "open", k10: 1};
}
let BKS = bkLoad();
function bkSave() { try { localStorage.setItem(BK.key, JSON.stringify(BKS)); } catch (e) {} }
window.addEventListener("storage", e => { if (e.key === BK.key) { BKS = bkLoad(); bkPaint(); } });   // another league's tab placed or graded a bet

function bkSel(o) {
  const s = Object.assign({}, o);
  s.key = [s.sport, s.gid, s.kind, s.side, s.line ?? "", s.pl ? s.pl.id + ":" + s.pl.stat : "", s.boost ? "B" : "", s.live ? "L" : ""].join("|");
  s.open = s.open !== false && (s.live ? Date.now() - (s.at || 0) < BK_LIVE_FRESH : !s.start || new Date(s.start) > Date.now());   // live lines stay open while their price is fresh
  s.dec = o.dec || bkDec(s.p);   // a market price (or a boost) comes in as dec; otherwise price the chance
  BK_REG[s.key] = s;
  return s;
}
function bkArt(s, cls = "") {
  const im = (src, c = "") => src ? `<img class="${c}" src="${esc(src)}" alt="" loading="lazy" onerror="this.remove()">` : "";
  if (s.img) return `<span class="bk-art pl ${cls}" style="--tc:${esc(s.color || "#345")}"><span>${esc(String(s.pl ? s.pl.name : s.pick).split(" ").map(w => w[0]).slice(0, 2).join(""))}</span>${im(s.img, "hs")}${im(s.logo, "lg")}</span>`;
  if (s.logos) return `<span class="bk-art duo ${cls}">${im(s.logos[0])}${im(s.logos[1])}</span>`;
  return `<span class="bk-art ${cls}" style="--tc:${esc(s.color || "#345")}">${s.logo ? im(s.logo) : `<b>${esc(String(s.pick).slice(0, 3))}</b>`}</span>`;
}
const bkIn = key => BKS.slip.some(x => x.key === key);
// a price button: line on top (spread / total), odds below
function bkBtn(s, top = "") {
  if (!s || s.p == null || !isFinite(s.p)) return `<span class="bk-px off">–</span>`;
  if (!s.open) return `<span class="bk-px off">${top ? `<i>${esc(top)}</i>` : ""}<b>🔒</b></span>`;
  return `<button class="bk-px ${bkIn(s.key) ? "on" : ""} ${s.src === "fd" ? "fd" : ""}" data-bk="${esc(s.key)}">${top ? `<i>${esc(top)}</i>` : ""}<b>${bkAm(s.dec)}</b></button>`;
}
function bkToggle(key) {
  const s = BK_REG[key]; if (!s) return;
  if (bkIn(key)) BKS.slip = BKS.slip.filter(x => x.key !== key);
  else {
    if (!s.open) return bkToast("That game has started");
    // one side per market: picking the other side of a line swaps it
    BKS.slip = BKS.slip.filter(x => !(x.gid === s.gid && x.kind === s.kind && x.kind !== "prop" && x.sport === s.sport));
    if (BKS.slip.length >= 12) return bkToast("Slip is full");
    BKS.slip.push(Object.assign({stake: 0}, s));
  }
  bkSave(); bkPaint(); bkBump();
}
const bkCanParlay = () => !BKS.slip.some(x => x.live) && BKS.slip.length >= 2 && BKS.slip.length <= BK.legs && new Set(BKS.slip.map(x => x.sport + x.gid)).size === BKS.slip.length;
function bkParlayDec() { return Math.round(BKS.slip.reduce((d, x) => d * (BK_REG[x.key] || x).dec, 1) * 100) / 100; }

// ---------- slip ----------
function bkBar() {
  let el = document.getElementById("bkbar");
  if (!el) { el = document.createElement("button"); el.id = "bkbar"; el.className = "bk-bar"; el.onclick = bkOpenSlip; document.body.appendChild(el); }
  const n = BKS.slip.length;
  el.classList.toggle("show", n > 0 && TAB !== "bets");
  if (!n) return;
  const P = bkCanParlay() && BKS.mode === "parlay";
  el.innerHTML = `<span class="bk-n">${n}</span><span class="bk-bt"><b>Bet slip</b><i>${P ? `${n}-leg parlay · ${bkAm(bkParlayDec())}` : n === 1 ? esc(BKS.slip[0].pick) : `${n} picks`}</i></span><span class="bk-go">Review</span>`;
}
function bkBump() { const el = document.getElementById("bkbar"); if (!el) return; el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump"); }
function bkSlipHtml() {
  const L = BKS.slip, P = bkCanParlay() && BKS.mode === "parlay";
  if (!L.length) return `<div class="sh-t">Bet slip</div><div class="bk-empty">Tap any price to add it here.</div>`;
  const leg = x => { const s = BK_REG[x.key] || x, lock = !s.open;
    return `<div class="bk-leg ${lock ? "lock" : ""} ${s.boost ? "boost" : ""}">${bkArt(s)}
      <div class="bk-lt"><b>${esc(s.pick)}</b><i>${s.boost ? "⚡ " : ""}${esc(s.mkt)} · ${esc(s.game)}</i>${lock ? `<em>Started · remove to place</em>` : ""}</div>
      <span class="bk-od">${bkAm(s.dec)}</span><button class="bk-x" data-bkx="${esc(x.key)}" aria-label="Remove">✕</button>
      ${P ? "" : `<label class="bk-st"><input inputmode="numeric" pattern="[0-9]*" data-bks="${esc(x.key)}" value="${x.stake || ""}" placeholder="0"><span id="bkw-${esc(x.key)}">${x.stake ? "wins " + bkN(x.stake * (s.dec - 1)) : ""}</span></label>`}</div>`; };
  return `<div class="bk-sh"><div class="sh-t">Bet slip</div><span class="bk-bal">${BK_COIN}${bkN(BKS.coins)}</span></div>
    ${L.length >= 2 ? `<div class="seg" style="--n:2"><button class="${P ? "" : "on"}" data-bkm="single">Singles</button><button class="${P ? "on" : ""} ${bkCanParlay() ? "" : "dis"}" data-bkm="parlay">Parlay</button></div>
      ${bkCanParlay() ? "" : `<div class="bk-why">Parlays need picks from different games.</div>`}` : ""}
    <div class="bk-legs">${L.map(leg).join("")}</div>
    ${P ? `<div class="bk-par"><span>Parlay odds</span><b>${bkAm(bkParlayDec())}</b></div>
      <label class="bk-st big"><input inputmode="numeric" pattern="[0-9]*" data-bks="parlay" value="${BKS.pstake || ""}" placeholder="Stake"><span></span></label>` : ""}
    <div class="bk-q">${[100, 250, 500, 1000].map(v => `<button data-bkq="${v}">${bkN(v)}</button>`).join("")}<button data-bkq="max">Max</button></div>
    <div class="bk-foot"><div><span>Stake</span><b id="bk-ts">0</b></div><div><span>To win</span><b id="bk-tw">0</b></div></div>
    <div class="bk-slide" id="bk-place" role="button" aria-label="Slide to place"><span class="bk-sf"></span><span class="bk-stx" id="bk-stx">Enter a stake</span><span class="bk-th">${BK_COIN}</span></div>
    <button class="bk-clear" data-bkclear="1">Clear slip</button>
    <div class="bk-fine">Play coins only. No deposits, no cash value.</div>`;
}
function bkTotals() {
  const P = bkCanParlay() && BKS.mode === "parlay";
  if (P) { const st = BKS.pstake || 0; return {stake: st, win: st * (bkParlayDec() - 1)}; }
  return BKS.slip.reduce((o, x) => { const s = BK_REG[x.key] || x; o.stake += x.stake || 0; o.win += (x.stake || 0) * (s.dec - 1); return o; }, {stake: 0, win: 0});
}
function bkSlipRefresh() {
  const t = bkTotals(), ts = document.getElementById("bk-ts"), tw = document.getElementById("bk-tw"), b = document.getElementById("bk-place"); if (!ts) return;
  ts.textContent = bkN(t.stake); tw.textContent = bkN(t.win);
  const P = bkCanParlay() && BKS.mode === "parlay", lock = BKS.slip.some(x => !(BK_REG[x.key] || x).open);
  const n = P ? 1 : BKS.slip.filter(x => x.stake > 0).length;
  b.classList.toggle("dis", !t.stake || t.stake > BKS.coins || lock);
  document.getElementById("bk-stx").textContent = t.stake > BKS.coins ? "Not enough coins" : lock ? "Remove started games" : !t.stake ? "Enter a stake" : `Slide to bet · win ${bkN(t.win)}`;
  for (const x of BKS.slip) { const w = document.getElementById("bkw-" + x.key); if (w) w.textContent = x.stake ? "wins " + bkN(x.stake * ((BK_REG[x.key] || x).dec - 1)) : ""; }
}
function bkOpenSlip() {
  pjSheet(bkSlipHtml()); const sh = document.getElementById("sheet"); sh.classList.add("bk-sheet");
  const re = () => { bkOpenSlip(); };
  sh.querySelectorAll("[data-bkx]").forEach(b => b.onclick = () => { BKS.slip = BKS.slip.filter(x => x.key !== b.dataset.bkx); bkSave(); bkPaint(); BKS.slip.length ? re() : closeSheet(); });
  sh.querySelectorAll("[data-bkm]").forEach(b => b.onclick = () => { if (b.dataset.bkm === "parlay" && !bkCanParlay()) return; BKS.mode = b.dataset.bkm; bkSave(); bkPaint(); re(); });
  sh.querySelectorAll("[data-bks]").forEach(inp => inp.oninput = () => {
    const v = Math.max(0, Math.floor(Number(inp.value.replace(/[^0-9]/g, "")) || 0)); if (String(v || "") !== inp.value) inp.value = v || "";
    if (inp.dataset.bks === "parlay") BKS.pstake = v; else { const x = BKS.slip.find(y => y.key === inp.dataset.bks); if (x) x.stake = v; }
    bkSave(); bkSlipRefresh(); });
  sh.querySelectorAll("[data-bkq]").forEach(b => b.onclick = () => {
    const P = bkCanParlay() && BKS.mode === "parlay", n = P ? 1 : BKS.slip.length;
    const v = b.dataset.bkq === "max" ? Math.floor(BKS.coins / n) : Number(b.dataset.bkq);
    if (P) BKS.pstake = v; else BKS.slip.forEach(x => x.stake = v);
    bkSave(); re(); });
  sh.querySelector("[data-bkclear]").onclick = () => { BKS.slip = []; BKS.pstake = 0; bkSave(); bkPaint(); closeSheet(); };
  bkSlider(document.getElementById("bk-place"));
  bkSlipRefresh();
}
// slide to place: drag the coin to the end of the track
function bkSlider(el) {
  const th = el.querySelector(".bk-th"), fill = el.querySelector(".bk-sf"); let x0 = null, x = 0;
  const max = () => el.clientWidth - th.offsetWidth - 8;
  const set = v => { x = v; th.style.transform = `translateX(${v}px)`; fill.style.width = `${v + th.offsetWidth / 2 + 4}px`; };
  const back = () => { el.classList.add("snap"); set(0); setTimeout(() => el.classList.remove("snap"), 260); };
  th.onpointerdown = e => { if (el.classList.contains("dis")) { el.classList.remove("nope"); void el.offsetWidth; el.classList.add("nope"); return; } x0 = e.clientX - x; th.setPointerCapture(e.pointerId); el.classList.add("drag"); };
  th.onpointermove = e => { if (x0 == null) return; set(Math.max(0, Math.min(max(), e.clientX - x0))); };
  th.onpointerup = th.onpointercancel = () => { if (x0 == null) return; x0 = null; el.classList.remove("drag");
    if (x >= max() * 0.88) { set(max()); el.classList.add("done"); setTimeout(bkPlace, 180); } else back(); };
}
function bkPlace() {
  const P = bkCanParlay() && BKS.mode === "parlay", t = bkTotals(), now = Date.now();
  const legs = BKS.slip.map(x => Object.assign({}, BK_REG[x.key] || x, {stake: undefined, r: null}));
  const shut = l => l.live ? now - (l.at || 0) >= BK_LIVE_FRESH : l.start && new Date(l.start) <= now;   // pre-game lines close at the start, live ones when their price goes stale
  if (legs.some(shut)) { legs.forEach(l => { if (BK_REG[l.key]) BK_REG[l.key].open = !shut(l); }); bkSlipRefresh(); return bkToast(legs.some(l => l.live) ? "A live price changed: check your slip" : "A game in your slip has started"); }
  if (!t.stake || t.stake > BKS.coins) return;
  const id = () => now.toString(36) + Math.random().toString(36).slice(2, 6);
  const made = [];
  if (P) made.push({id: id(), at: now, legs, stake: t.stake, dec: bkParlayDec(), st: "open", pay: 0});
  else for (const x of BKS.slip) if (x.stake > 0) { const l = legs.find(y => y.key === x.key); made.push({id: id(), at: now, legs: [l], stake: x.stake, dec: l.dec, st: "open", pay: 0}); }
  BKS.coins -= made.reduce((s, b) => s + b.stake, 0);
  BKS.bets = made.concat(BKS.bets).slice(0, 400);
  BKS.slip = BKS.slip.filter(x => !P && !(x.stake > 0)); BKS.pstake = 0;
  bkSave(); closeSheet(); bkPaint();
  bkToast(`${made.length > 1 ? made.length + " bets" : P ? "Parlay" : "Bet"} placed · to win ${bkN(made.reduce((s, b) => s + b.stake * (b.dec - 1), 0))}`, "ok");
  bkCoinFx();
}

// ---------- wallet ----------
// ---------- daily drop streak, levels, missions ----------
const bkYday = () => bkDay(Date.now() - 864e5);
const bkStreakNow = () => BKS.drop === bkDay() || BKS.drop === bkYday() ? (BKS.streak || 1) : 0;
const bkDropAmt = () => BK.drop + 250 * Math.min(6, BKS.drop === bkYday() ? (BKS.streak || 1) : 0);   // 1,000 on day 1, up to 2,500 on a 7-day streak
function bkClaim() {
  if (BKS.drop === bkDay()) return; const amt = bkDropAmt();
  BKS.streak = BKS.drop === bkYday() ? (BKS.streak || 1) + 1 : 1; BKS.drop = bkDay(); BKS.coins += amt;
  bkSave(); bkPaint(); bkToast(`${bkN(amt)} coins added`, "ok"); bkCoinFx(); }
const BK_LV = [[1, "Rookie"], [3, "Starter"], [6, "Pro"], [10, "All-Star"], [15, "MVP"], [21, "Hall of Fame"]];
function bkLevel() {   // XP = every coin you've ever put in play
  const xp = BKS.bets.reduce((s, b) => s + b.stake, 0), n = Math.floor(Math.sqrt(xp / 100)) + 1;
  const lo = (n - 1) * (n - 1) * 100, hi = n * n * 100;
  return {n, xp, name: BK_LV.filter(x => n >= x[0]).pop()[1], prog: (xp - lo) / (hi - lo), need: hi - xp};
}
const BK_MIS = [
  {id: "three", ic: "", t: "Place 3 bets", r: 500, f: T => [Math.min(3, T.length), 3]},
  {id: "prop", ic: "", t: "Bet a player prop", r: 250, f: T => [T.some(b => b.legs.some(l => l.kind === "prop")) ? 1 : 0, 1]},
  {id: "parlay", ic: "", t: "Place a 3-leg parlay", r: 750, f: T => [T.some(b => b.legs.length >= 3) ? 1 : 0, 1]},
  {id: "multi", ic: "", t: "Bet two different leagues", r: 500, f: T => [Math.min(2, new Set(T.flatMap(b => b.legs.map(l => l.sport))).size), 2]},
];
function bkMissions() {
  const day = bkDay(), T = BKS.bets.filter(b => bkDay(b.at) === day), got = (BKS.mis && BKS.mis.day === day) ? BKS.mis.got : [];
  return BK_MIS.map(m => { const [a, n] = m.f(T); return Object.assign({}, m, {a, n, done: a >= n, got: got.includes(m.id)}); });
}
function bkClaimMission(id) {
  const m = bkMissions().find(x => x.id === id); if (!m || !m.done || m.got) return;
  if (!BKS.mis || BKS.mis.day !== bkDay()) BKS.mis = {day: bkDay(), got: []};
  BKS.mis.got.push(id); BKS.coins += m.r; bkSave(); bkPaint(); bkToast(`${bkN(m.r)} coins added`, "ok"); bkCoinFx();
}
function bkMissionsHtml() {
  return `<div class="ms">${bkMissions().map(m => `<div class="ms-r ${m.got ? "got" : m.done ? "done" : ""}"><span class="ms-ic">${m.got ? "✓" : `${m.a}/${m.n}`}</span>
    <div class="ms-t"><b>${esc(m.t)}</b><span class="ms-bar"><i style="width:${Math.round(100 * m.a / m.n)}%"></i></span></div>
    ${m.got ? `<span class="ms-rw">Claimed</span>` : m.done ? `<button class="ms-go" data-bkmis="${m.id}">Claim ${bkN(m.r)}</button>` : `<span class="ms-rw">${bkN(m.r)}</span>`}</div>`).join("")}</div>`;
}
function bkStripHtml() {
  const s = bkStats(), sg = v => v > 0 ? "+" + bkN(v) : v < 0 ? "−" + bkN(-v) : "0";
  return `<section class="mb-strip"><button class="mb-bal" data-go="bets"><i>Balance</i><span>${BK_COIN}<b>${bkN(BKS.coins)}</b></span></button>
      <div class="mb-st"><span><i>Today</i><b class="${s.today > 0 ? "up" : s.today < 0 ? "dn" : ""}">${sg(s.today)}</b></span><span><i>Open</i><b>${s.open}</b></span>
        <span><i>Record</i><b>${s.w}-${s.l}${s.p ? "-" + s.p : ""}</b></span></div></section>
    ${BKS.drop !== bkDay() ? `<button class="bk-drop" data-bkdrop="1"><span><b>Daily bonus</b><i>${bkStreakNow() ? `Day ${bkStreakNow() + 1} in a row` : "Free coins every day"}</i></span><em>Claim ${bkN(bkDropAmt())}</em></button>` : ""}
    ${bkBroke() ? `<button class="bk-drop" data-bkreload="1"><span><b>Out of coins</b><i>Reload once a day</i></span><em>Reload ${bkN(BK.reload)}</em></button>` : ""}`;
}
function bkAddParlay(legs) {
  if (!legs || legs.length < 2 || legs.some(l => !l.open)) return bkToast("Those games have started");
  BKS.slip = legs.map(s => Object.assign({stake: 0}, s)); BKS.mode = "parlay"; BKS.pstake = 0; bkSave(); bkPaint(); bkOpenSlip();
}
const bkBroke = () => BKS.coins < 10 && !BKS.bets.some(b => b.st === "open") && BKS.reload !== bkDay();
function bkReload() { if (!bkBroke()) return; BKS.reload = bkDay(); BKS.coins = BK.reload; bkSave(); bkPaint(); bkToast("Wallet reloaded · 10,000 coins", "ok"); }
function bkStats() {
  const S = BKS.bets.filter(b => b.st !== "open"), today = bkDay();
  const o = {w: 0, l: 0, p: 0, staked: 0, ret: 0, today: 0, open: 0, risk: 0};
  for (const b of S) { o[b.st === "won" ? "w" : b.st === "lost" ? "l" : "p"]++; o.staked += b.stake; o.ret += b.pay; if (bkDay(b.done || b.at) === today) o.today += b.pay - b.stake; }
  for (const b of BKS.bets) if (b.st === "open") { o.open++; o.risk += b.stake; }
  o.profit = o.ret - o.staked; o.roi = o.staked ? o.profit / o.staked : null;
  o.edge = o.roi == null ? null : o.roi - (1 / (1 + BK.hold) - 1);   // vs what blind betting into the model's prices returns
  return o;
}
function bkPill() { return `${BK_COIN}<b>${bkN(BKS.coins)}</b>`; }
function bkPaint() {
  const c = document.getElementById("coin"); if (c) c.innerHTML = bkPill();
  bkBar();
  if (typeof pjRender === "function" && PJA) pjRender();
}
function bkCoinFx() { const c = document.getElementById("coin"); if (!c) return; c.classList.remove("pop"); void c.offsetWidth; c.classList.add("pop"); }
let bkTT = null;
function bkToast(msg, kind = "") {
  let el = document.getElementById("bktoast"); if (!el) { el = document.createElement("div"); el.id = "bktoast"; el.className = "bk-toast"; document.body.appendChild(el); }
  el.className = "bk-toast show " + kind; el.textContent = msg; clearTimeout(bkTT); bkTT = setTimeout(() => el.classList.remove("show"), 2600);
}

// ---------- Bets tab ----------
// Live tracking: every 30 seconds, any open leg whose game has started gets its game's score and clock from ESPN's
// scoreboard, and a prop leg its player's stat so far from the box score. All three leagues, whichever page is open.
const BK_LIVE_EV = {};   // "sport|event id" -> {state, detail, h, a, ha, aa, box}
const bkLvKey = l => l.sport + "|" + ((l.ev || {}).id || (l.ev || {}).home + "@" + (l.ev || {}).away);
function bkEvInfo(ev, sport) {
  const c = (ev.competitions || [])[0] || {}, st = (ev.status || c.status || {}).type || {}, fix = (BK_ESPN[sport] || [])[1] || {}, o = {};
  for (const t of c.competitors || []) { o[t.homeAway] = Number(t.score) || 0; o[t.homeAway + "b"] = fix[(t.team || {}).abbreviation] || (t.team || {}).abbreviation; }
  return {state: st.state, detail: st.shortDetail || st.detail || "", h: o.home, a: o.away, ha: o.homeb, aa: o.awayb, id: ev.id};
}
let bkLvBusy = false, bkLvAt = 0;
async function bkLiveTick(force) {
  if (bkLvBusy || (document.hidden && !force)) return;
  const now = Date.now(), legs = [];
  for (const b of BKS.bets) if (b.st === "open") for (const l of b.legs) if (!l.r && l.start && new Date(l.start) <= now && BK_ESPN[l.sport] && l.ev) legs.push(l);
  if (!legs.length) return;
  bkLvBusy = true;
  try {
    const days = {};
    for (const l of legs) (days[l.sport + "|" + l.ev.date] = days[l.sport + "|" + l.ev.date] || []).push(l);
    await Promise.all(Object.entries(days).map(async ([k, L]) => {
      const [sport, date] = k.split("|"), base = "https://site.api.espn.com/apis/site/v2/sports/" + BK_ESPN[sport][0] + "/";
      let evs; try { evs = (await bkGet(base + "scoreboard?dates=" + date, 20e3)).events || []; } catch (e) { return; }
      const boxes = {};
      for (const l of L) {
        const ev = bkFind(evs, l); if (!ev) continue;
        const info = bkEvInfo(ev, sport), key = bkLvKey(l);
        if (l.kind === "prop" && info.state !== "pre") {
          if (!(ev.id in boxes)) { try { boxes[ev.id] = bkBox(sport, await bkGet(base + "summary?event=" + ev.id, 40e3)); } catch (e) { boxes[ev.id] = null; } }
          info.box = boxes[ev.id];
        } else if (BK_LIVE_EV[key] && BK_LIVE_EV[key].box) info.box = BK_LIVE_EV[key].box;
        BK_LIVE_EV[key] = info;
      }
    }));
    bkLvAt = Date.now();
    bkListRefresh();
  } finally { bkLvBusy = false; }
}
setInterval(bkLiveTick, 30e3); setTimeout(() => bkLiveTick(true), 800);
// a leg's state right now: {chip: [class, text], bar: [now, target] | null, sb: scoreboard text}
function bkLegNow(l) {
  const F = l.fin, I = l.r ? F : BK_LIVE_EV[bkLvKey(l)];
  if (!I) return null;
  const sb = I.ha ? `${I.aa} ${I.a} – ${I.h} ${I.ha}` : "", out = {sb, clock: l.r ? "Final" : I.state === "post" ? "Final" : I.state === "in" ? I.detail : ""};
  if (I.state === "pre" && !l.r) return null;
  const mine = l.side === "home" ? I.h - I.a : I.a - I.h, tot = I.h + I.a;
  if (l.kind === "ml") out.chip = mine > 0 ? ["ok", "Winning"] : mine < 0 ? ["bad", "Losing"] : ["mid", "Tied"];
  else if (l.kind === "spread") { const m = mine + l.line; out.chip = m > 0 ? ["ok", "Covering"] : m < 0 ? ["bad", "Not covering"] : ["mid", "Push"]; }
  else if (l.kind === "total") {
    out.bar = [tot, l.line]; out.barLab = `Total ${tot} of ${l.line}`;
    out.chip = l.side === "over" ? (tot > l.line ? ["ok", "Over hit"] : ["mid", `Needs ${Math.floor(l.line - tot) + 1}`]) : (tot > l.line ? ["bad", "Over the line"] : ["ok", `${Math.ceil(l.line - tot - 0.5)} to spare`]);
  } else if (l.kind === "prop") {
    const box = I.box || null, o = box && ((l.pl.espn && box["id:" + l.pl.id]) || box["nm:" + bkNm(l.pl.name)]);
    const v = l.r ? (F && F.v != null ? F.v : null) : o ? (o[l.pl.stat] || 0) : (I.state === "in" ? 0 : null);
    if (v != null) { out.bar = [v, l.pl.n]; out.barLab = `${v} of ${l.pl.n} ${BK_STAT[l.pl.stat] || l.pl.stat}`;
      out.chip = v >= l.pl.n ? ["ok", "Hit"] : l.r === "loss" || I.state === "post" ? ["bad", "Missed"] : ["mid", `Needs ${l.pl.n - v}`]; }
  }
  if (l.r) out.chip = l.r === "win" ? ["ok", "Won"] : l.r === "loss" ? ["bad", "Lost"] : l.r === "push" ? ["mid", "Push"] : ["mid", "Void"];
  return out;
}
const BK_STAT = {goals: "goals", sog: "shots", points: "points", assists: "assists", td: "TD", pass_yds: "pass yds", rush_yds: "rush yds",
  rec_yds: "rec yds", rec: "catches", pts: "pts", reb: "reb", ast: "ast", fg3: "threes", pra: "PRA"};
function bkLegHtml(l, multi) {
  const N = bkLegNow(l), d = l.start ? new Date(l.start) : null;
  const when = !N && d ? (d > Date.now() ? d.toLocaleString("en-US", {weekday: "short", hour: "numeric", minute: "2-digit", timeZone: "America/New_York"}) : "Starting…") : "";
  const R = l.r === "win" ? "✓" : l.r === "loss" ? "✕" : l.r === "push" ? "–" : l.r === "void" ? "↺" : "";
  const pct = N && N.bar ? Math.max(3, Math.min(100, Math.round(100 * N.bar[0] / Math.max(0.5, N.bar[1])))) : 0;
  return `<div class="bk-tl ${l.r || ""} ${N && !l.r ? "is-live" : ""}">${bkArt(l, "sm")}<div><b>${esc(l.pick)}</b>
      <i>${N && N.sb ? `<span class="lg-sb">${esc(N.sb)}</span>${N.clock ? ` · <span class="${l.r || N.clock === "Final" ? "lg-fin" : "lg-live"}">${esc(N.clock)}</span>` : ""}` : `${esc(l.game || "")}${when ? ` · <span class="lg-pre">${esc(when)}</span>` : ""}`}</i></div>
      ${multi ? `<span class="bk-od">${bkAm(l.dec)}</span>` : ""}${N && N.chip ? `<span class="lg-chip ${N.chip[0]}">${esc(N.chip[1])}</span>` : `<span class="bk-r">${R}</span>`}</div>
    ${N && N.bar ? `<div class="lg-bar ${N.chip ? N.chip[0] : ""}"><i style="width:${pct}%"></i><span>${esc(N.barLab)}</span></div>` : ""}`;
}
function bkTicket(b) {
  const started = b.legs.some(l => l.start && new Date(l.start) <= Date.now());
  const tag = b.st === "open" ? (started ? ["live", "Live"] : ["open", "Open"]) : b.st === "won" ? ["won", "Won"] : b.st === "lost" ? ["lost", "Lost"] : ["push", "Push"];
  const when = new Date(b.at).toLocaleString("en-US", {month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York"});
  const multi = b.legs.length > 1, title = multi ? `${b.legs.length}-leg parlay` : esc(b.legs[0].mkt);
  const win = b.stake * (b.dec - 1);
  let prog = "";
  if (b.st === "open" && multi) {
    const st = b.legs.map(l => l.r ? (l.r === "loss" ? "x" : "y") : ((bkLegNow(l) || {}).chip || [""])[0] === "ok" ? "o" : ((BK_LIVE_EV[bkLvKey(l)] || {}).state === "in" ? "l" : "p"));
    const n = k => st.filter(x => x === k).length;
    prog = `<div class="bk-legs">${st.map(x => `<i class="${x}"></i>`).join("")}<span>${[n("y") && `${n("y")} won`, n("o") && `${n("o")} on track`, n("l") && `${n("l")} live`, n("x") && `${n("x")} lost`, n("p") && `${n("p")} to start`].filter(Boolean).join(" · ")}</span></div>`;
  }
  return `<div class="bk-tk ${tag[0]}"><div class="bk-tkh"><span class="bk-tag">${tag[1]}</span><b class="bk-tt">${title}</b><span class="bk-tko">${bkAm(b.dec)}</span></div>
    ${b.legs.map(l => bkLegHtml(l, multi)).join("")}${prog}
    <div class="bk-tkf"><span class="bk-when">${esc(when)}</span><span>${bkN(b.stake)} ${b.st === "open" ? `<i>to win</i> <b class="up">${bkN(win)}</b>` : b.st === "won" ? `<i>paid</i> <b class="up">+${bkN(b.pay - b.stake)}</b>` : b.st === "push" ? `<i>returned</i> <b>${bkN(b.pay)}</b>` : `<i>lost</i> <b class="dn">−${bkN(b.stake)}</b>`}</span></div></div>`;
}
function bkListRefresh() {   // redraw just the tickets (live scores), leaving the rest of the screen and the scroll alone
  const el = document.querySelector(".bk-list"); if (!el) return;
  el.innerHTML = bkListHtml(BKS.view === "settled" ? "settled" : "open");
}
function bkListHtml(V) {
  const open = BKS.bets.filter(b => b.st === "open"), settled = BKS.bets.filter(b => b.st !== "open");
  const sg = v => v > 0 ? "+" + bkN(v) : v < 0 ? "−" + bkN(-v) : "0";
  if (V === "open") {
    const live = open.filter(b => b.legs.some(l => !l.r && l.start && new Date(l.start) <= Date.now())), up = open.filter(b => !live.includes(b));
    const pot = B => bkN(B.reduce((x, b) => x + b.stake * b.dec, 0));
    return open.length ? (live.length ? `<div class="mb-day"><b><span class="lv-dot"></span>Live now</b><span>${live.length} bet${live.length > 1 ? "s" : ""} · pays ${pot(live)}${bkLvAt ? ` · <em class="lv-at">updated ${new Date(bkLvAt).toLocaleTimeString("en-US", {hour: "numeric", minute: "2-digit"})}</em>` : ""}</span></div>${live.map(bkTicket).join("")}` : "")
        + (up.length ? `<div class="mb-day"><b>Upcoming</b><span>${bkN(up.reduce((x, b) => x + b.stake, 0))} in play · pays ${pot(up)}</span></div>${up.map(bkTicket).join("")}` : "")
      : `<div class="mb-empty"><b>No open bets</b><span>Tap a price on any game or player to add it to your bet slip.</span><div><button data-go="games">Games</button><button data-go="players">Props</button></div></div>`;
  }
  const days = {};
  for (const b of settled.slice(0, 80)) (days[bkDay(b.done || b.at)] = days[bkDay(b.done || b.at)] || []).push(b);
  const lab = d => d === bkDay() ? "Today" : d === bkYday() ? "Yesterday" : new Date(d + "T12:00:00").toLocaleDateString("en-US", {weekday: "short", month: "short", day: "numeric"});
  return settled.length ? Object.entries(days).map(([d, B]) => { const net = B.reduce((x, b) => x + b.pay - b.stake, 0), w = B.filter(b => b.st === "won").length;
      return `<div class="mb-day"><b>${lab(d)}</b><span>${w}-${B.filter(b => b.st === "lost").length} · <em class="${net > 0 ? "up" : net < 0 ? "dn" : ""}">${sg(net)}</em></span></div>${B.map(bkTicket).join("")}`; }).join("")
    : `<div class="mb-empty"><b>Nothing settled yet</b><span>Bets grade automatically from ESPN finals.</span></div>`;
}
function bkScreen() {
  const V = BKS.view === "settled" ? "settled" : "open";
  const open = BKS.bets.filter(b => b.st === "open"), settled = BKS.bets.filter(b => b.st !== "open");
  const seg = `<div class="seg mb-seg" style="--n:2"><button class="${V === "open" ? "on" : ""}" data-bkv="open">Open${open.length ? ` <em>${open.length}</em>` : ""}</button><button class="${V === "settled" ? "on" : ""}" data-bkv="settled">Settled${settled.length ? ` <em>${settled.length}</em>` : ""}</button></div>`;
  if (V === "open") setTimeout(() => bkLiveTick(true), 0);
  const L = bkLevel();
  const rewards = `<div class="hd"><b>Daily challenges</b><span class="hd-s">Level ${L.n} · ${bkN(L.need)} XP to next</span></div>${bkMissionsHtml()}`;
  return bkStripHtml() + seg + `<div class="bk-list">${bkListHtml(V)}</div>` + rewards + `<div class="bk-fine">Play coins only: no deposits, no cash value, nothing to withdraw.</div>`;
}
function bkWire(root = document) {
  root.querySelectorAll("[data-bk]").forEach(b => b.onclick = e => { e.stopPropagation(); bkToggle(b.dataset.bk); });
  root.querySelectorAll("[data-bkv]").forEach(b => b.onclick = () => { BKS.view = b.dataset.bkv; bkSave(); pjRender(); });
  root.querySelectorAll("[data-bkdrop]").forEach(b => b.onclick = bkClaim);
  root.querySelectorAll("[data-bkreload]").forEach(b => b.onclick = bkReload);
  root.querySelectorAll("[data-bkmis]").forEach(b => b.onclick = e => { e.stopPropagation(); bkClaimMission(b.dataset.bkmis); });
}

// ---------- grading (ESPN finals + box scores) ----------
const BK_ESPN = {NHL: ["hockey/nhl", {LA: "LAK", NJ: "NJD", SJ: "SJS", TB: "TBL", UTAH: "UTA", WAS: "WSH"}],
                 NFL: ["football/nfl", {LAR: "LA", WSH: "WAS"}], NBA: ["basketball/nba", {}]};
const bkNm = s => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\b(jr|sr|ii|iii|iv)\b/g, "").replace(/[^a-z]/g, "");
const BK_CACHE = {};
async function bkGet(url, ttl) {
  const c = BK_CACHE[url]; if (c && (c.keep || Date.now() - c.t < ttl)) return c.v;
  const v = await (await fetch(url)).json(); BK_CACHE[url] = {t: Date.now(), v}; return v;
}
function bkBox(sport, sm) {   // player -> stats, keyed by ESPN id and normalised name
  const box = {};
  for (const team of (sm.boxscore || {}).players || []) for (const grp of team.statistics || []) {
    const k = grp.keys || [], lab = (grp.labels || []).map(x => String(x).toUpperCase());
    for (const a of grp.athletes || []) {
      const v = a.stats || [], ath = a.athlete || {}; if (!v.length) continue;
      const o = box["id:" + ath.id] || (box["id:" + ath.id] = {});
      box["nm:" + bkNm(ath.displayName)] = o;
      const byKey = key => { const i = k.indexOf(key); return i < 0 ? 0 : Number(String(v[i]).split("/")[0]) || 0; };
      const byLab = key => { const i = lab.indexOf(key); return i < 0 ? 0 : Number(String(v[i]).split("-")[0]) || 0; };
      if (sport === "NHL" && k.includes("goals")) { o.goals = byKey("goals"); o.assists = byKey("assists"); o.sog = byKey("shotsTotal"); o.points = o.goals + o.assists; }
      if (sport === "NBA") { o.pts = byLab("PTS"); o.reb = byLab("REB"); o.ast = byLab("AST"); o.fg3 = byLab("3PT"); o.pra = o.pts + o.reb + o.ast; }
      if (sport === "NFL") {
        o.td = o.td || 0;
        if (grp.name === "passing") o.pass_yds = byKey("passingYards");
        if (grp.name === "rushing") { o.rush_yds = byKey("rushingYards"); o.td += byKey("rushingTouchdowns"); }
        if (grp.name === "receiving") { o.rec = byKey("receptions"); o.rec_yds = byKey("receivingYards"); o.td += byKey("receivingTouchdowns"); }
      }
    }
  }
  return box;
}
function bkGrade(l, ev, box) {   // -> win | loss | push | void | null (not decided)
  const c = (ev.competitions || [])[0] || {}, st = (ev.status || c.status || {}).type || {};
  if (st.state !== "post") return /postponed|canceled|cancelled/i.test(st.description || st.name || "") ? "void" : null;
  const side = {}; for (const t of c.competitors || []) side[t.homeAway] = Number(t.score) || 0;
  const h = side.home, a = side.away, cmp = x => x > 0 ? "win" : x < 0 ? "loss" : "push";
  if (l.kind === "ml") return cmp(l.side === "home" ? h - a : a - h);
  if (l.kind === "spread") return cmp((l.side === "home" ? h - a : a - h) + l.line);
  if (l.kind === "total") return cmp(l.side === "over" ? h + a - l.line : l.line - (h + a));
  if (l.kind === "prop") {
    if (!box) return null;
    const o = (l.pl.espn && box["id:" + l.pl.id]) || box["nm:" + bkNm(l.pl.name)];
    if (!o || o[l.pl.stat] == null) return "void";                 // didn't play: stake back
    return o[l.pl.stat] >= l.pl.n ? "win" : "loss";
  }
  return null;
}
function bkFind(evs, l) {
  const fix = (BK_ESPN[l.sport] || [])[1] || {};
  return evs.find(ev => String(ev.id) === String(l.ev.id)) || evs.find(ev => { const c = (ev.competitions || [])[0]; if (!c) return false;
    const t = {}; for (const x of c.competitors || []) t[x.homeAway] = fix[x.team.abbreviation] || x.team.abbreviation;
    return t.home === l.ev.home && t.away === l.ev.away; });
}
let bkBusy = false;
async function bkSettle() {
  if (bkBusy) return; bkBusy = true;
  try {
    const now = Date.now(), legs = [];
    for (const b of BKS.bets) if (b.st === "open") for (const l of b.legs) if (!l.r && l.start && new Date(l.start) < now - 20 * 60e3 && BK_ESPN[l.sport]) legs.push(l);
    if (!legs.length) return;
    const days = {};
    for (const l of legs) (days[l.sport + "|" + l.ev.date] = days[l.sport + "|" + l.ev.date] || []).push(l);
    for (const [k, L] of Object.entries(days)) {
      const [sport, date] = k.split("|"), base = "https://site.api.espn.com/apis/site/v2/sports/" + BK_ESPN[sport][0] + "/";
      let evs; try { evs = (await bkGet(base + "scoreboard?dates=" + date, 90e3)).events || []; } catch (e) { continue; }
      for (const l of L) {
        const ev = bkFind(evs, l); if (!ev) { if (now - new Date(l.start) > 4 * 864e5) l.r = "void"; continue; }
        let box = null;
        if (l.kind === "prop" && ((ev.status || {}).type || {}).state === "post") {
          try { const url = base + "summary?event=" + ev.id; box = bkBox(sport, await bkGet(url, 90e3)); BK_CACHE[url].keep = true; } catch (e) { continue; }
        }
        l.r = bkGrade(l, ev, box);
        if (l.r && l.r !== "void") { const I = bkEvInfo(ev, sport); l.fin = {state: "post", h: I.h, a: I.a, ha: I.ha, aa: I.aa};
          if (l.kind === "prop" && box) { const o = (l.pl.espn && box["id:" + l.pl.id]) || box["nm:" + bkNm(l.pl.name)]; if (o && o[l.pl.stat] != null) l.fin.v = o[l.pl.stat]; } }
      }
    }
    const news = [];
    for (const b of BKS.bets) {
      if (b.st !== "open" || b.legs.some(l => !l.r)) continue;
      if (b.legs.some(l => l.r === "loss")) { b.st = "lost"; b.pay = 0; }
      else { const d = b.legs.reduce((x, l) => x * (l.r === "win" ? l.dec : 1), 1); b.pay = Math.round(b.stake * d); b.st = b.legs.every(l => l.r !== "win") ? "push" : "won"; }
      b.done = Date.now(); BKS.coins += b.pay; news.push(b);
    }
    bkSave();
    if (news.length) {
      bkPaint();
      const won = news.filter(b => b.st === "won"), net = news.reduce((s, b) => s + b.pay - b.stake, 0);
      bkToast(won.length ? `${won.length === 1 ? won[0].legs.map(l => l.pick).join(" + ") + " cashed" : won.length + " bets cashed"} · ${net >= 0 ? "+" : "−"}${bkN(Math.abs(net))} net` : `${news.length} bet${news.length > 1 ? "s" : ""} settled`, won.length ? "ok" : "");
      if (won.length) bkCoinFx();
    }
  } finally { bkBusy = false; }
}
setTimeout(bkSettle, 1500); setInterval(bkSettle, 60e3);   // grade open bets from ESPN finals
