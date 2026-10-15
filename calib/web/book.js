// ---------- 🪙 PIKT BOOK: virtual coins, priced by the model ----------
// Play money only. Every price carries a thin hold, like a real book. One wallet for the NHL, NFL and NBA pages (same origin, localStorage); bets are graded
// in the browser from ESPN's final scores and box scores, on whichever page is open.
// A selection (built by bkSel):
//   {key, sport, gid, kind: ml|spread|total|prop, side: home|away|over|under|yes, line, p, pick, mkt, game, start,
//    ev: {date: "YYYYMMDD", home, away, id}, pl: {name, id, team, stat, n}}
const BK = {key: "bz.book.v1", hold: 0.045, start: 1000, drop: 100, reload: 1000, legs: 8};
const BK_REG = {};   // key -> the latest selection drawn on screen (prices refresh with the model)
const bkDay = (t = Date.now()) => new Date(t).toLocaleDateString("en-CA", {timeZone: "America/New_York"});
const bkImp = p => Math.min(0.97, Math.max(0.03, p) * (1 + BK.hold));
const bkDec = p => Math.round(1e4 / bkImp(p)) / 1e4;
const bkAm = d => d >= 2 ? "+" + Math.round(100 * (d - 1)) : "−" + Math.round(100 / (d - 1));
const bkEvDate = s => bkDay(new Date(s).getTime()).replace(/-/g, "");
const bkHalf = x => Math.floor(x) + 0.5;   // the nearest hook below: lines never push
const bkN = n => Math.round(n).toLocaleString("en-US");
const BK_COIN = '<svg class="bk-c" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9.2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M9.6 16.9V7.3h3.5a2.75 2.75 0 0 1 0 5.5H9.6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>';

function bkLoad() {
  try { const s = JSON.parse(localStorage.getItem(BK.key)); if (s && typeof s.coins === "number" && Array.isArray(s.bets)) return Object.assign({slip: [], mode: "single", pstake: 0, drop: "", reload: "", view: "open"}, s); } catch (e) {}
  return {coins: BK.start, bets: [], slip: [], mode: "single", pstake: 0, drop: "", reload: "", view: "open"};
}
let BKS = bkLoad();
function bkSave() { try { localStorage.setItem(BK.key, JSON.stringify(BKS)); } catch (e) {} }
window.addEventListener("storage", e => { if (e.key === BK.key) { BKS = bkLoad(); bkPaint(); } });   // another league's tab placed or graded a bet

function bkSel(o) {
  const s = Object.assign({}, o);
  s.key = [s.sport, s.gid, s.kind, s.side, s.line ?? "", s.pl ? s.pl.id + ":" + s.pl.stat : ""].join("|");
  s.open = s.open !== false && (!s.start || new Date(s.start) > Date.now());
  s.dec = bkDec(s.p);
  BK_REG[s.key] = s;
  return s;
}
const bkIn = key => BKS.slip.some(x => x.key === key);
// a price button: line on top (spread / total), odds below
function bkBtn(s, top = "") {
  if (!s || s.p == null || !isFinite(s.p)) return `<span class="bk-px off">–</span>`;
  if (!s.open) return `<span class="bk-px off">${top ? `<i>${esc(top)}</i>` : ""}<b>🔒</b></span>`;
  return `<button class="bk-px ${bkIn(s.key) ? "on" : ""}" data-bk="${esc(s.key)}">${top ? `<i>${esc(top)}</i>` : ""}<b>${bkAm(s.dec)}</b></button>`;
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
const bkCanParlay = () => BKS.slip.length >= 2 && BKS.slip.length <= BK.legs && new Set(BKS.slip.map(x => x.sport + x.gid)).size === BKS.slip.length;
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
    return `<div class="bk-leg ${lock ? "lock" : ""}"><button class="bk-x" data-bkx="${esc(x.key)}" aria-label="Remove">✕</button>
      <div class="bk-lt"><b>${esc(s.pick)}</b><i>${esc(s.mkt)} · ${esc(s.game)}</i>${lock ? `<em>Started · remove to place</em>` : ""}</div>
      <span class="bk-od">${bkAm(s.dec)}</span>
      ${P ? "" : `<label class="bk-st"><input inputmode="numeric" pattern="[0-9]*" data-bks="${esc(x.key)}" value="${x.stake || ""}" placeholder="0"><span id="bkw-${esc(x.key)}">${x.stake ? "wins " + bkN(x.stake * (s.dec - 1)) : ""}</span></label>`}</div>`; };
  return `<div class="bk-sh"><div class="sh-t">Bet slip</div><span class="bk-bal">${BK_COIN}${bkN(BKS.coins)}</span></div>
    ${L.length >= 2 ? `<div class="seg" style="--n:2"><button class="${P ? "" : "on"}" data-bkm="single">Singles</button><button class="${P ? "on" : ""} ${bkCanParlay() ? "" : "dis"}" data-bkm="parlay">Parlay</button></div>
      ${bkCanParlay() ? "" : `<div class="bk-why">Parlays need picks from different games.</div>`}` : ""}
    <div class="bk-legs">${L.map(leg).join("")}</div>
    ${P ? `<div class="bk-par"><span>Parlay odds</span><b>${bkAm(bkParlayDec())}</b></div>
      <label class="bk-st big"><input inputmode="numeric" pattern="[0-9]*" data-bks="parlay" value="${BKS.pstake || ""}" placeholder="Stake"><span></span></label>` : ""}
    <div class="bk-q">${[25, 50, 100, 250].map(v => `<button data-bkq="${v}">${v}</button>`).join("")}<button data-bkq="max">Max</button></div>
    <div class="bk-foot"><div><span>Stake</span><b id="bk-ts">0</b></div><div><span>To win</span><b id="bk-tw">0</b></div></div>
    <button class="bk-place" id="bk-place">Place bet</button><button class="bk-clear" data-bkclear="1">Clear slip</button>
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
  b.disabled = !t.stake || t.stake > BKS.coins || lock;
  b.textContent = t.stake > BKS.coins ? "Not enough coins" : lock ? "Remove started games" : !t.stake ? "Enter a stake" : P ? `Place parlay · win ${bkN(t.win)}` : `Place ${n > 1 ? n + " bets" : "bet"} · win ${bkN(t.win)}`;
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
  document.getElementById("bk-place").onclick = bkPlace;
  bkSlipRefresh();
}
function bkPlace() {
  const P = bkCanParlay() && BKS.mode === "parlay", t = bkTotals(), now = Date.now();
  const legs = BKS.slip.map(x => Object.assign({}, BK_REG[x.key] || x, {stake: undefined, r: null}));
  if (legs.some(l => l.start && new Date(l.start) <= now)) { legs.forEach(l => { if (BK_REG[l.key]) BK_REG[l.key].open = new Date(l.start) > now; }); bkSlipRefresh(); return bkToast("A game in your slip has started"); }
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
function bkClaim() { if (BKS.drop === bkDay()) return; BKS.drop = bkDay(); BKS.coins += BK.drop; bkSave(); bkPaint(); bkToast(`+${BK.drop} coins · see you tomorrow`, "ok"); bkCoinFx(); }
const bkBroke = () => BKS.coins < 10 && !BKS.bets.some(b => b.st === "open") && BKS.reload !== bkDay();
function bkReload() { if (!bkBroke()) return; BKS.reload = bkDay(); BKS.coins = BK.reload; bkSave(); bkPaint(); bkToast("Wallet reloaded · 1,000 coins", "ok"); }
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
function bkTicket(b) {
  const tag = b.st === "open" ? (b.legs.some(l => l.start && new Date(l.start) <= Date.now()) ? ["live", "Live"] : ["open", "Open"]) : b.st === "won" ? ["won", "Won"] : b.st === "lost" ? ["lost", "Lost"] : ["push", "Push"];
  const R = r => r === "win" ? "✓" : r === "loss" ? "✕" : r === "push" ? "–" : r === "void" ? "void" : "";
  const when = new Date(b.at).toLocaleString("en-US", {month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York"});
  return `<div class="bk-tk ${tag[0]}"><div class="bk-tkh"><span class="bk-tag">${tag[1]}</span><span>${b.legs.length > 1 ? b.legs.length + "-leg parlay" : esc(b.legs[0].sport)}</span><span class="bk-when">${esc(when)}</span></div>
    ${b.legs.map(l => `<div class="bk-tl ${l.r || ""}"><span class="bk-r">${R(l.r)}</span><div><b>${esc(l.pick)}</b><i>${esc(l.mkt)} · ${esc(l.game)}</i></div><span class="bk-od">${bkAm(l.dec)}</span></div>`).join("")}
    <div class="bk-tkf"><span>Stake <b>${bkN(b.stake)}</b></span><span>${b.st === "open" ? `To win <b>${bkN(b.stake * (b.dec - 1))}</b>` : b.st === "won" ? `Paid <b class="up">+${bkN(b.pay - b.stake)}</b>` : b.st === "push" ? `Returned <b>${bkN(b.pay)}</b>` : `<b class="dn">−${bkN(b.stake)}</b>`}</span></div></div>`;
}
function bkScreen() {
  const s = bkStats(), V = BKS.view === "settled" ? "settled" : "open";
  const L = BKS.bets.filter(b => V === "open" ? b.st === "open" : b.st !== "open");
  const sg = v => v > 0 ? "+" + bkN(v) : v < 0 ? "−" + bkN(-v) : "0";
  const hero = `<section class="bk-hero"><div class="bk-hk">Wallet</div><div class="bk-hb">${BK_COIN}<b>${bkN(BKS.coins)}</b></div>
      <div class="bk-hs"><div><i>Today</i><b class="${s.today > 0 ? "up" : s.today < 0 ? "dn" : ""}">${sg(s.today)}</b></div><div><i>All time</i><b class="${s.profit > 0 ? "up" : s.profit < 0 ? "dn" : ""}">${sg(s.profit)}</b></div>
        <div><i>Record</i><b>${s.w}-${s.l}${s.p ? "-" + s.p : ""}</b></div><div><i>In play</i><b>${bkN(s.risk)}</b></div></div>
      ${BKS.drop !== bkDay() ? `<button class="bk-drop" data-bkdrop="1">${BK_COIN}<span><b>Daily drop</b><i>Claim ${BK.drop} free coins</i></span><em>Claim</em></button>` : ""}
      ${bkBroke() ? `<button class="bk-drop" data-bkreload="1">${BK_COIN}<span><b>Out of coins</b><i>Reload to ${bkN(BK.reload)} (once a day)</i></span><em>Reload</em></button>` : ""}</section>`;
  const edge = s.roi == null ? "" : `<div class="bk-edge"><div><b>You vs the house</b><i>${s.w + s.l + s.p} settled · ${bkN(s.staked)} staked</i></div><span class="${s.roi >= 0 ? "up" : "dn"}">${s.roi >= 0 ? "+" : "−"}${Math.abs(100 * s.roi).toFixed(1)}%<i>ROI</i></span></div>`;
  const seg = `<div class="seg" style="--n:2"><button class="${V === "open" ? "on" : ""}" data-bkv="open">Open${s.open ? ` · ${s.open}` : ""}</button><button class="${V === "settled" ? "on" : ""}" data-bkv="settled">Settled</button></div>`;
  const list = L.length ? L.slice(0, 60).map(bkTicket).join("") : `<div class="bk-empty">${V === "open" ? "No open bets. Tap any price on a game card or player to start a slip." : "Nothing settled yet."}</div>`;
  return hero + edge + seg + `<div class="bk-list">${list}</div><div class="bk-fine">Play coins only: no deposits, no cash value, nothing to withdraw. Bets grade automatically from ESPN finals.</div>`;
}
function bkWire(root = document) {
  root.querySelectorAll("[data-bk]").forEach(b => b.onclick = e => { e.stopPropagation(); bkToggle(b.dataset.bk); });
  root.querySelectorAll("[data-bkv]").forEach(b => b.onclick = () => { BKS.view = b.dataset.bkv; bkSave(); pjRender(); });
  root.querySelectorAll("[data-bkdrop]").forEach(b => b.onclick = bkClaim);
  root.querySelectorAll("[data-bkreload]").forEach(b => b.onclick = bkReload);
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
setTimeout(bkSettle, 1500); setInterval(bkSettle, 120e3);
