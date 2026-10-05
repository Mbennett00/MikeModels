// ---------- 🧾 PAPER SPORTSBOOK (shared by the NHL and NFL pages) ----------
// Everything lives in this browser (localStorage; both sports share the origin, so one wallet and one slip).
// A bet: {id, ts, sport, kind: "single"|"parlay", label, odds (American), stake, legs: [{label, sub, gid, start, key, p, odds}],
//         status: "open"|"won"|"lost"|"push", result_ts, manual, seen}
// leg.key tells the page how to grade it: {t: "game", m, s, l} or {t: "prop", pid, name, team, mk, l, dir}.
const MB_KEY = "mm_paper_v1", SLIP_KEY = "mm_slip_v1";
let MB_VIEW = "bets", MB_SPORT = "all", MB_MSG = "", SLIP_MODE = "single", SLIP_STAKE = null, MB_RENDER = null;
function mbLoad() {
  try { const s = JSON.parse(localStorage.getItem(MB_KEY) || "null"); if (s && Array.isArray(s.bets)) return Object.assign({start: 1000, unit: 10, badges: []}, s); } catch (e) {}
  return {start: 1000, unit: 10, bets: [], badges: []};
}
// pick art: player headshot with a team-logo badge, or the two team logos for a game line
function mbPic(l) {
  if (!l.img && !l.logos && typeof mbArtFor === "function") { try { l = Object.assign({}, l, mbArtFor(l) || {}); } catch (e) {} }
  const ini = String(l.name || l.label || "").split(" ").filter(Boolean).slice(0, 2).map(w => w[0]).join("");
  if (l.img || (l.key && l.key.t === "prop")) return `<span class="lpic">${l.img ? `<img class="hs" src="${esc(l.img)}" alt="" loading="lazy" onerror="this.outerHTML='<span class=&quot;ini&quot;>${esc(ini)}</span>'">` : `<span class="ini">${esc(ini)}</span>`}${l.logo ? `<img class="tb" src="${esc(l.logo)}" alt="" onerror="this.remove()">` : ""}</span>`;
  if (l.logos && l.logos.length) return `<span class="lpic duo"><img class="l1" src="${esc(l.logos[0])}" alt="" onerror="this.remove()"><img class="l2" src="${esc(l.logos[1])}" alt="" onerror="this.remove()"></span>`;
  return `<span class="lpic"><span class="ini">${esc(ini || "?")}</span></span>`;
}
const legArt = x => ({img: x.img, logo: x.logo, logos: x.logos, name: x.name});
function mbSave(s) { try { localStorage.setItem(MB_KEY, JSON.stringify(s)); return true; } catch (e) { return false; } }
function slipLoad() { try { const v = JSON.parse(localStorage.getItem(SLIP_KEY) || "[]"); return Array.isArray(v) ? v : []; } catch (e) { return []; } }
function slipSave(v) { try { localStorage.setItem(SLIP_KEY, JSON.stringify(v)); } catch (e) {} }
const mbDec = a => a > 0 ? 1 + a / 100 : 1 + 100 / -a;
const mbAm = d => d >= 2 ? Math.round(100 * (d - 1)) : Math.round(-100 / (d - 1));
const mbSign = a => (a > 0 ? "+" : "") + Math.round(a);
const mbMoney = x => (x < 0 ? "−$" : "$") + Math.abs(x).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
const mbShort = x => "$" + Math.round(x).toLocaleString("en-US");
function mbProfit(b) { return b.status === "won" ? b.stake * (mbDec(b.odds) - 1) : b.status === "lost" ? -b.stake : 0; }
function mbWallet(s = mbLoad()) {
  const pl = s.bets.reduce((a, b) => a + mbProfit(b), 0), risk = s.bets.filter(b => b.status === "open").reduce((a, b) => a + b.stake, 0);
  const bonus = s.bonus || 0;
  return {bankroll: s.start + bonus + pl, available: s.start + bonus + pl - risk, risk, pl, bonus};
}
function mbAdd(bet) {
  const s = mbLoad();
  bet.id = Date.now().toString(36).toUpperCase() + Math.random().toString(36).slice(2, 5).toUpperCase();
  bet.ts = new Date().toISOString(); bet.status = "open";
  s.bets.push(bet); s.unit = bet.stake;
  return mbSave(s) ? bet : null;
}
function mbUpdate(id, f) { const s = mbLoad(), b = s.bets.find(x => x.id === id); if (b) { f(b, s); mbSave(s); } }
const mbStarted = l => l.start && new Date(l.start).getTime() <= Date.now();

// ---- the bet slip ----
function slipKey(x) { return x.gid + "|" + JSON.stringify(x.key || x.label); }
function slipAdd(sel) {
  const v = slipLoad(), k = slipKey(sel), i = v.findIndex(x => slipKey(x) === k);
  if (i >= 0) v[i] = sel; else v.push(sel);
  slipSave(v); mbFab(true);
}
function slipRemove(k) { slipSave(slipLoad().filter(x => slipKey(x) !== k)); }
// inside a bet sheet: the odds come from the sheet's odds box (or the market / fair price)
function mbTrackHtml(defOdds) {
  return `<div class="mbt"><button class="addslip" id="mbadd">＋ Add to bet slip <b id="mbodds">${isFinite(defOdds) ? mbSign(defOdds) : "–"}</b></button>
    <div class="hint" id="mbmsg">Odds from the box above, or the ${isFinite(defOdds) ? "market / fair" : ""} price if blank. Paper money.</div></div>`;
}
function mbWireTrack(getOdds, defOdds, getBet) {
  const add = document.getElementById("mbadd"); if (!add) return;
  const bk = (() => { try { return mbBookOdds(getBet().legs[0]); } catch (e) { return null; } })();
  const cur = () => { const o = getOdds(); return isFinite(o) && Math.abs(o) >= 100 ? o : bk ? bk.odds : defOdds; };
  const msg = document.getElementById("mbmsg");
  if (msg) msg.innerHTML = bk ? `<span class="bookline">● ${esc(bk.book)} live price</span> · type other odds above to override` : "No live book price for this line: uses the fair price unless you type odds above.";
  const show = () => setTimeout(() => { const o = cur(), el = document.getElementById("mbodds"); if (el) el.textContent = isFinite(o) ? mbSign(o) : "–"; }, 0);
  const odds = document.getElementById("odds"); if (odds) odds.addEventListener("input", show);
  document.querySelectorAll("#sheet [data-s], #sheet [data-ms]").forEach(x => x.addEventListener("click", show));
  show();
  add.onclick = () => {
    const o = cur(), bet = getBet(), leg = bet.legs[0];
    if (!isFinite(o)) { document.getElementById("mbmsg").textContent = "Enter the odds first."; return; }
    if (mbStarted(leg)) { document.getElementById("mbmsg").textContent = "That game has started: betting is closed."; return; }
    const typed = getOdds(); slipAdd(Object.assign({}, leg, {sport: bet.sport, label: bet.label, odds: Math.round(o), book: !(isFinite(typed) && Math.abs(typed) >= 100) && bk ? bk.book : null})); mbHaptic();
    add.classList.add("added"); add.innerHTML = `✓ On your slip · ${slipLoad().length} pick${slipLoad().length > 1 ? "s" : ""}`;
    document.getElementById("mbmsg").innerHTML = `<button class="linkbtn" id="mbopen">Open bet slip →</button>`;
    document.getElementById("mbopen").onclick = () => mbOpenSlip();
  };
}
// a parlay card's legs straight onto the slip, in parlay mode
function mbSlipParlay(legs, sport) {
  slipSave([]);
  legs.forEach(l => slipAdd(Object.assign({}, l, {sport})));
  SLIP_MODE = "parlay"; mbOpenSlip();
}
function slipParlayOk(v) { return v.length >= 2 && new Set(v.map(x => x.sport + x.gid)).size === v.length; }
function mbOpenSlip() {
  const sh = document.getElementById("sheet"), s = mbLoad(), W = mbWallet(s), v = slipLoad();
  let moved = 0;
  v.forEach(x => { if (!x.book) return; const b = mbBookOdds(x); if (b && b.odds !== x.odds) { x.was = x.odds; x.odds = b.odds; moved++; } });
  if (moved) slipSave(v);
  if (SLIP_STAKE == null) SLIP_STAKE = s.unit || 10;
  if (SLIP_MODE === "parlay" && !slipParlayOk(v)) SLIP_MODE = "single";
  const dec = v.reduce((a, x) => a * mbDec(x.odds), 1), stake = Number(SLIP_STAKE) || 0;
  const tot = SLIP_MODE === "parlay" ? stake : stake * v.length, win = SLIP_MODE === "parlay" ? stake * (dec - 1) : v.reduce((a, x) => a + stake * (mbDec(x.odds) - 1), 0);
  const closed = v.filter(mbStarted).length, short = tot > W.available + 1e-9;
  const payout = SLIP_MODE === "parlay" ? stake * dec : tot + win;
  const label = closed ? "Remove started games" : short ? "Not enough balance" : !(stake > 0) ? "Enter a stake" : `Place ${mbMoney(tot)}`;
  sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>
    <div class="slhead"><div class="sh-t">Bet slip</div><span class="slcount">${v.length}</span>${v.length ? `<button class="slclr" id="slipclr">Clear</button>` : ""}</div>
    ${v.length ? `<div class="gseg c"><button class="${SLIP_MODE === "single" ? "on" : ""}" data-sm2="single">Singles</button>
      <button class="${SLIP_MODE === "parlay" ? "on" : ""} ${slipParlayOk(v) ? "" : "dis"}" data-sm2="parlay">Parlay${v.length >= 2 ? `<em>${mbSign(mbAm(dec))}</em>` : ""}</button></div>
    <div class="slipl c">${v.map(x => `<div class="slipi c ${mbStarted(x) ? "closed" : ""}">${mbPic(x)}
      <div class="slipt"><b>${esc(x.label)}</b><i>${esc(x.sub || x.sport)}${x.book ? ` · ${esc(x.book.replace("DraftKings", "DK"))}` : ""}${mbStarted(x) ? " · started" : ""}</i></div>
      <span class="slipo ${x.was != null ? "moved" : ""}">${x.was != null ? `<s>${mbSign(x.was)}</s>` : ""}${mbSign(x.odds)}</span><button class="slipx" data-sx="${esc(slipKey(x))}" aria-label="Remove">×</button></div>`).join("")}</div>
    <div class="stkrow"><div class="stkin c"><em>$</em><input id="slipstake" inputmode="decimal" value="${stake || ""}" aria-label="Stake"></div>
      <div class="qchips c">${[5, 10, 25, 50].map(a => `<button class="${stake === a ? "on" : ""}" data-qs="${a}">$${a}</button>`).join("")}</div></div>
    <div class="slsum c"><span>${SLIP_MODE === "parlay" ? "Stake" : `${v.length} × ${mbMoney(stake)}`}</span><span>To win <b>${mbMoney(win)}</b></span></div>
    <button class="placebet c" id="slipgo" ${!v.length || closed || short || !(stake > 0) ? "disabled" : ""}><span>${label}</span>${!closed && !short && stake > 0 ? `<em>Payout ${mbMoney(payout)}</em>` : ""}</button>
    <div class="slfoot">${mbMoney(W.available)} available · paper money</div>`
      : `<div class="slipempty"><div class="slicon">🧾</div><b>Your bet slip is empty</b><span>Tap any price or prop, then add it to your slip.</span></div>`}`;
  document.getElementById("shx").onclick = () => closeSheet();
  const re = () => mbOpenSlip();
  sh.querySelectorAll("[data-sm2]").forEach(b => b.onclick = () => { if (b.classList.contains("dis")) return; mbHaptic(); SLIP_MODE = b.dataset.sm2; re(); });
  sh.querySelectorAll("[data-sx]").forEach(b => b.onclick = () => { mbHaptic(); slipRemove(b.dataset.sx); mbFab(); re(); });
  sh.querySelectorAll("[data-qs]").forEach(b => b.onclick = () => { mbHaptic(); SLIP_STAKE = Number(b.dataset.qs); re(); });
  const si = document.getElementById("slipstake");
  if (si) si.onchange = () => { SLIP_STAKE = Number(si.value.replace(/[^0-9.]/g, "")); re(); };
  const clr = document.getElementById("slipclr"); if (clr) clr.onclick = () => { slipSave([]); mbFab(); re(); };
  const go = document.getElementById("slipgo");
  if (go) go.onclick = () => {
    const placed = [];
    if (SLIP_MODE === "parlay") placed.push(mbAdd({sport: v[0].sport, kind: "parlay", label: `${v.length}-leg parlay`, odds: mbAm(dec), stake,
      legs: v.map(x => Object.assign({label: x.label, sub: x.sub, gid: x.gid, start: x.start, key: x.key, p: x.p, odds: x.odds, dec: mbDec(x.odds), sport: x.sport}, legArt(x)))}));
    else v.forEach(x => placed.push(mbAdd({sport: x.sport, kind: "single", label: x.label, odds: x.odds, stake,
      legs: [Object.assign({label: x.label, sub: x.sub, gid: x.gid, start: x.start, key: x.key, p: x.p, odds: x.odds}, legArt(x))]})));
    if (placed.some(b => !b)) { go.textContent = "Couldn't save (private browsing?)"; return; }
    mbHaptic("success"); slipSave([]); mbFab(); mbConfirm(placed);
  };
  document.getElementById("scrim").classList.add("open"); sh.classList.add("open");
}
function mbConfirm(placed) {
  const sh = document.getElementById("sheet"), tot = placed.reduce((a, b) => a + b.stake, 0), win = placed.reduce((a, b) => a + b.stake * (mbDec(b.odds) - 1), 0);
  sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>
    <div class="okhead"><div class="okring">✓</div><div class="sh-t">Bet placed!</div><div class="sh-s">${placed.length > 1 ? placed.length + " bets" : "Ticket #" + placed[0].id}</div></div>
    ${placed.map(mbTicket).join("")}
    <div class="pl-sum"><div><span>Risk</span><b>${mbMoney(tot)}</b></div><div><span>To win</span><b>${mbMoney(win)}</b></div><div><span>Payout</span><b>${mbMoney(tot + win)}</b></div></div>
    <div class="mbx"><button id="okmore">Keep betting</button><button id="okbets">My bets</button></div>`;
  document.getElementById("shx").onclick = document.getElementById("okmore").onclick = () => { closeSheet(); MB_RENDER && MB_RENDER(); };
  document.getElementById("okbets").onclick = () => { closeSheet(); MB_VIEW = "bets"; if (typeof TAB !== "undefined") TAB = "check"; MB_RENDER && MB_RENDER(); window.scrollTo(0, 0); };
  mbBurst(18, ["🎟️", "✨"]);
}
// floating slip button + wallet in the nav
function mbFab(pop) {
  let f = document.getElementById("slipfab");
  if (!f) { f = document.createElement("button"); f.id = "slipfab"; f.className = "slipfab"; f.onclick = () => mbOpenSlip(); document.body.appendChild(f); }
  const n = slipLoad().length; f.style.display = n ? "flex" : "none";
  f.innerHTML = `🧾 Bet slip <b>${n}</b>`;
  if (pop) { f.classList.remove("pop"); void f.offsetWidth; f.classList.add("pop"); }
  const nb = document.querySelector('#nav [data-k="check"]');
  if (nb) nb.innerHTML = `🎟️ ${mbShort(mbWallet().bankroll)}${mbDaily().claimed ? "" : `<span class="navdot"></span>`}`;
}

// ---- grading + celebrations ----
function mbAutoSettle(sport, gradeLeg) {
  const s = mbLoad(); let changed = false;
  for (const b of s.bets) {
    if (b.status !== "open" || b.sport !== sport || b.manual) continue;
    const r = b.legs.map(l => { try { return gradeLeg(l); } catch (e) { return undefined; } });
    b.legs.forEach((l, i) => { if (r[i] !== undefined) l.res = r[i]; });
    let st;
    if (r.some(x => x === false)) st = "lost";
    else if (r.every(x => x !== undefined)) {
      if (r.every(x => x === "push")) st = "push";
      else { st = "won"; if (b.kind === "parlay" && r.some(x => x === "push")) {   // pushed legs drop out of the parlay
        const keep = b.legs.filter((l, i) => r[i] !== "push"); const d = keep.reduce((a, l) => a * (l.dec || mbDec(l.odds || -110)), 1);
        if (keep.every(l => l.dec || l.odds)) b.odds = mbAm(d); } }
    }
    if (st) { b.status = st; b.result_ts = new Date().toISOString(); b.seen = false; changed = true; }
  }
  if (changed) mbSave(s);
  mbCelebrate();
}
function mbBurst(n, set) {
  const box = document.createElement("div"); box.className = "burst";
  for (let i = 0; i < n; i++) { const e = document.createElement("i"); e.textContent = set[i % set.length];
    e.style.left = (5 + Math.random() * 90) + "%"; e.style.animationDelay = (Math.random() * 0.5) + "s"; e.style.fontSize = (16 + Math.random() * 18) + "px"; box.appendChild(e); }
  document.body.appendChild(box); setTimeout(() => box.remove(), 2600);
}
function mbToast(html, cls) {
  const t = document.createElement("div"); t.className = "mbtoast " + (cls || ""); t.innerHTML = html;
  document.body.appendChild(t); requestAnimationFrame(() => t.classList.add("in"));
  setTimeout(() => { t.classList.remove("in"); setTimeout(() => t.remove(), 400); }, 3800);
}
function mbCelebrate() {
  const s = mbLoad(), fresh = s.bets.filter(b => b.status !== "open" && b.seen === false);
  if (!fresh.length) { mbBadgesCheck(s); return; }
  const won = fresh.filter(b => b.status === "won"), lost = fresh.filter(b => b.status === "lost");
  fresh.forEach(b => b.seen = true); mbSave(s);
  if (won.length) {
    const amt = won.reduce((a, b) => a + mbProfit(b), 0), big = won.some(b => b.kind === "parlay");
    mbToast(`<div class="tbig">${big ? "🎰 PARLAY CASHED!" : "💰 CASHED!"}</div><div class="tamt">+${mbMoney(amt)}</div><div class="tsub">${esc(won.map(b => b.label).join(" · "))}</div>`, "win");
    mbBurst(big ? 60 : 36, ["💵", "🎉", "💰", "✨"]);
  } else if (lost.length) mbToast(`<div class="tsub">❌ ${esc(lost.map(b => b.label).join(" · "))}</div><div class="tsub">On to the next one.</div>`, "loss");
  mbBadgesCheck(mbLoad());
}
const BADGES = [
  ["first", "🥇", "First win", "Cash your first bet"],
  ["heater", "🔥", "Heater", "Win 3 in a row"],
  ["parlay", "🎰", "Parlay hitter", "Cash a parlay"],
  ["green", "📈", "In the green", "Be up overall after 10 bets"],
  ["century", "💯", "Century", "Up $100 or more"],
  ["sharp", "🎯", "Sharp", "+5% ROI over 25+ bets"],
  ["grinder", "🧾", "Grinder", "Settle 50 bets"],
  ["longshot", "🚀", "Longshot", "Cash a bet at +500 or longer"],
];
function mbStats(bets) {
  const done = bets.filter(b => b.status !== "open").sort((a, b) => (a.result_ts || a.ts).localeCompare(b.result_ts || b.ts));
  let streak = 0, best = 0, cur = 0;
  for (const b of done) { if (b.status === "won") { cur++; best = Math.max(best, cur); } else if (b.status === "lost") cur = 0; }
  for (let i = done.length - 1; i >= 0; i--) { if (done[i].status === "won") streak++; else if (done[i].status === "lost") break; }
  const pl = done.reduce((a, b) => a + mbProfit(b), 0), staked = done.filter(b => b.status !== "push").reduce((a, b) => a + b.stake, 0);
  const wins = done.filter(b => b.status === "won");
  return {streak, best, pl, n: done.length, roi: staked ? pl / staked : 0, bigWin: wins.reduce((m, b) => Math.max(m, mbProfit(b)), 0),
    has: {first: wins.length > 0, heater: best >= 3, parlay: wins.some(b => b.kind === "parlay"), green: done.length >= 10 && pl > 0,
          century: pl >= 100, sharp: done.length >= 25 && staked && pl / staked >= 0.05, grinder: done.length >= 50, longshot: wins.some(b => b.odds >= 500)}};
}
function mbBadgesCheck(s) {
  const st = mbStats(s.bets), got = new Set(s.badges || []), fresh = BADGES.filter(([k]) => st.has[k] && !got.has(k));
  if (!fresh.length) return;
  s.badges = [...got, ...fresh.map(b => b[0])]; mbSave(s);
  setTimeout(() => mbToast(`<div class="tbig">🏅 Badge unlocked</div><div class="tsub">${fresh.map(b => b[1] + " " + b[2]).join(" · ")}</div>`, "badge"), 1200);
}

// ---- My bets ----
function mbTicket(b) {
  const dot = l => `<span class="tkdot ${l.res === true ? "w" : l.res === false ? "l" : l.res === "push" ? "p" : ""}"></span>`;
  const toWin = b.stake * (mbDec(b.odds) - 1), when = new Date(b.ts).toLocaleString("en-US", {month: "short", day: "numeric", hour: "numeric", minute: "2-digit"});
  const sw = l => b.status === "open" ? mbSweatHtml(l) : "";
  const lc = l => l.res === true ? "w" : l.res === false ? "l" : "";
  const body = b.kind === "parlay" ? `<div class="tksel" style="margin-top:4px">${b.legs.length}-leg parlay</div>` + b.legs.map(l => `<div class="tkleg ${lc(l)}">${mbPic(l)}<b>${esc(l.label)}</b><i>${l.odds ? mbSign(l.odds) : ""}</i></div>${sw(l)}`).join("")
    : `<div class="tkone">${mbPic(b.legs[0] || {})}<div><div class="tksel">${esc(b.label)}</div><div class="tksub">${esc((b.legs[0] || {}).sub || "")}</div></div></div>${sw(b.legs[0] || {})}`;
  const pill = {open: "Open", won: "Cashed", lost: "Lost", push: "Push"}[b.status];
  const res = b.status === "won" ? "+" + mbMoney(mbProfit(b)) : b.status === "lost" ? "−" + mbMoney(b.stake) : b.status === "push" ? mbMoney(b.stake) : mbMoney(toWin);
  const acts = !b.id ? "" : b.status === "open"
    ? `<button data-mbs="${b.id}|won">Won</button><button data-mbs="${b.id}|lost">Lost</button><button data-mbs="${b.id}|push">Push</button><button data-mbd="${b.id}" class="del">Delete</button>`
    : `<button data-mbs="${b.id}|open">Reopen</button><button data-mbd="${b.id}" class="del">Delete</button>`;
  return `<div class="ticket ${b.status}"><div class="tkh">${b.status === "open" && mbIsLive(b) ? `<span class="livetag"><span class="livedot"></span>LIVE</span>` : ""}<span class="tkmeta">${b.sport} · ${b.kind === "parlay" ? "Parlay" : "Single"}</span><span class="tkodds">${mbSign(b.odds)}</span></div>
    ${body}<div class="tkdiv"></div>
    <div class="tkf"><div><span>Risk</span><b>${mbMoney(b.stake)}</b></div><div><span>${b.status === "won" ? "Won" : b.status === "lost" ? "Lost" : b.status === "push" ? "Refund" : "To win"}</span><b class="${b.status === "won" ? "pos" : ""}">${res}</b></div>
      <span class="tkpill ${b.status}">${pill}</span></div>
    <div class="tkfoot"><span>#${esc(b.id || "")} · ${when}</span>${acts ? `<span class="tkact">${acts}</span>` : ""}</div></div>`;
}
function mbChart(bets) {
  const done = bets.filter(b => b.status !== "open").sort((a, b) => (a.result_ts || a.ts).localeCompare(b.result_ts || b.ts));
  if (done.length < 2) return "";
  let run = 0; const pts = [{x: 0, y: 0, t: "Start: $0"}];
  done.forEach((b, i) => { run += mbProfit(b); pts.push({x: i + 1, y: run, t: `${b.label}: ${(run >= 0 ? "+" : "") + mbMoney(run)}`}); });
  return `<div class="card mbchart">${mhLine([{name: "Profit", color: run >= 0 ? MH_C2 : "#c0504d", pts}], {title: "Profit ($) after each settled bet", w: 320, h: 120, ref: "zero", yd: 0, L: 36, xl: ["first", "latest"]})}</div>`;
}
function mbView() {
  const s = mbLoad(), all = s.bets, bets = all.filter(b => MB_SPORT === "all" || b.sport === MB_SPORT), W = mbWallet(s), st = mbStats(bets), stAll = mbStats(all);
  const chips = [["all", "All"], ["NHL", "🏒 NHL"], ["NFL", "🏈 NFL"]].map(([k, n]) => `<button class="chip ${MB_SPORT === k ? "on" : ""}" data-mbsp="${k}">${n}</button>`).join("");
  const openAll = bets.filter(b => b.status === "open").sort((a, b) => b.ts.localeCompare(a.ts));
  const live = openAll.filter(mbIsLive), open = openAll.filter(b => !mbIsLive(b));
  const done = bets.filter(b => b.status !== "open").sort((a, b) => (b.result_ts || b.ts).localeCompare(a.result_ts || a.ts));
  const w = done.filter(b => b.status === "won").length, l = done.filter(b => b.status === "lost").length, p = done.filter(b => b.status === "push").length;
  const got = new Set(s.badges || []);
  const xp = mbXP(s), T = mbTier(xp);
  return `<div class="wallet"><div class="wtop"><div class="wl"><span>Balance</span><b>${mbMoney(W.bankroll)}</b><i>${mbMoney(W.available)} available · ${mbMoney(W.risk)} in play</i></div>
      <div class="wr ${W.pl > 0 ? "up" : W.pl < 0 ? "down" : ""}"><span>All-time</span><b>${(W.pl > 0 ? "+" : "") + mbMoney(W.pl)}</b></div></div>
      <div class="tier"><div class="tierh"><em>${T.cur[2]} ${T.cur[0]}</em><span>${T.nxt ? `${xp} / ${T.nxt[1]} XP to ${T.nxt[2]} ${T.nxt[0]}` : `${xp} XP · top tier`}</span></div>
        <div class="tbar"><b style="width:${Math.round(100 * T.pct)}%"></b></div></div></div>
    ${mbDailyHtml(s)}
    <div class="strip" style="padding:0 0 8px">${chips}</div>
    <div class="card mbsum"><div class="mbtiles">
      <div><span>Record</span><b>${w}-${l}${p ? "-" + p : ""}</b></div>
      <div><span>ROI</span><b class="${st.roi > 0 ? "pos" : st.roi < 0 ? "neg" : ""}">${(st.roi >= 0 ? "+" : "") + (100 * st.roi).toFixed(1)}%</b></div>
      <div><span>Streak</span><b>${st.streak ? "🔥" + st.streak + "W" : "–"}</b></div>
      <div><span>Best win</span><b>${st.bigWin ? mbShort(st.bigWin) : "–"}</b></div></div>
      ${MB_MSG ? `<div class="hint"><b>${esc(MB_MSG)}</b></div>` : ""}</div>
    <div class="card badges"><div class="lk-h" style="font-size:16px">🏅 Badges <span class="pl-tag">${got.size}/${BADGES.length}</span></div>
      <div class="bgrid">${BADGES.map(([k, e, n, d]) => `<div class="bdg ${got.has(k) ? "on" : ""}" title="${esc(d)}"><em>${e}</em><b>${n}</b><i>${d}</i></div>`).join("")}</div></div>
    ${mbChart(bets)}
    ${live.length ? `<div class="sec mbsec livesec"><span class="livedot"></span> Live sweat · ${live.length}</div>${live.map(mbTicket).join("")}` : ""}
    ${open.length || !live.length ? `<div class="sec mbsec">${live.length ? "Upcoming" : "Open bets"} ${open.length ? `· ${mbMoney(open.reduce((a, b) => a + b.stake, 0))} in play` : ""}</div>` : ""}
    ${open.length ? open.map(mbTicket).join("") : live.length ? "" : `<div class="note">No open bets. Tap any price, prop or parlay and ＋ Add to bet slip.</div>`}
    ${done.length ? `<div class="sec mbsec">Settled</div>${done.slice(0, 40).map(mbTicket).join("")}` : ""}
    <details class="card mbset"><summary>⚙️ Bankroll &amp; backup</summary>
      <label class="f">Starting bankroll ($)</label><input id="mbstart" inputmode="decimal" value="${s.start}">
      <div class="mbx" style="margin-top:10px"><button id="mbexp">Copy backup</button><button id="mbimp">Restore backup</button><button id="mbreset" class="del">Reset all</button></div>
      <div class="hint">Paper money, stored in this browser only. On iPhone, the home-screen app and Safari keep separate copies: use Copy / Restore backup to move them.</div></details>`;
}
function mbWire(render) {
  MB_RENDER = render;
  const cl = document.getElementById("mbclaim"); if (cl) cl.onclick = () => { mbClaim(); render(); };
  document.querySelectorAll("[data-mbsp]").forEach(b => b.onclick = () => { MB_SPORT = b.dataset.mbsp; render(); });
  document.querySelectorAll("[data-mbs]").forEach(b => b.onclick = () => { const [id, st] = b.dataset.mbs.split("|"); mbHaptic(st === "won" ? "success" : "");
    mbUpdate(id, x => { x.status = st; x.manual = st !== "open"; x.result_ts = st === "open" ? null : new Date().toISOString(); x.seen = st === "open" ? undefined : false; });
    mbCelebrate(); render(); });
  document.querySelectorAll("[data-mbd]").forEach(b => b.onclick = () => { if (!confirm("Delete this bet?")) return;
    const s = mbLoad(); s.bets = s.bets.filter(x => x.id !== b.dataset.mbd); mbSave(s); render(); });
  const st = document.getElementById("mbstart");
  if (st) st.onchange = () => { const v = Number(st.value.replace(/[^0-9.]/g, "")); if (v > 0) { const s = mbLoad(); s.start = v; mbSave(s); render(); } };
  const ex = document.getElementById("mbexp");
  if (ex) ex.onclick = async () => { const txt = JSON.stringify(mbLoad());
    try { await navigator.clipboard.writeText(txt); MB_MSG = "Backup copied. Paste it somewhere safe (Notes works)."; }
    catch (e) { prompt("Copy this backup:", txt); MB_MSG = ""; } render(); };
  const im = document.getElementById("mbimp");
  if (im) im.onclick = () => { const txt = prompt("Paste a backup (replaces the bets on this device):"); if (!txt) return;
    try { const s = JSON.parse(txt); if (!Array.isArray(s.bets)) throw 0; mbSave(s); MB_MSG = `Restored ${s.bets.length} bets.`; } catch (e) { MB_MSG = "That backup didn't read. Copy it again."; } render(); };
  const rs = document.getElementById("mbreset");
  if (rs) rs.onclick = () => { if (confirm("Delete every paper bet and reset the bankroll?")) { mbSave({start: mbLoad().start, unit: 10, bets: [], badges: [], daily: mbLoad().daily}); MB_MSG = "Reset."; render(); } };
}
// every render: keep the slip button and the wallet in the nav current
function mbAfterRender(render) { MB_RENDER = render; mbFab(); mbWireBanner(render); }

// ---- haptics: Android vibrates; iPhone (iOS 18+) ticks when a hidden switch is flipped during a tap ----
function mbHaptic(kind) {
  try { if (navigator.vibrate && navigator.vibrate(kind === "success" ? [14, 50, 22] : 9)) return; } catch (e) {}
  try {
    let l = document.getElementById("mbhap");
    if (!l) { l = document.createElement("label"); l.id = "mbhap"; l.className = "mbhap"; l.setAttribute("aria-hidden", "true");
              l.innerHTML = '<input type="checkbox" switch tabindex="-1">'; document.body.appendChild(l); }
    l.click();
  } catch (e) {}
}

// ---- the sweat: live status for every open leg. The page supplies mbLiveLeg(leg) ->
// {state: "pre"|"in"|"post", detail, start, home, away, homeAbbr, awayAbbr, cur (prop stat so far or null), unit} or null ----
function mbSweat(leg) {
  const L = typeof mbLiveLeg === "function" ? (() => { try { return mbLiveLeg(leg); } catch (e) { return null; } })() : null;
  const k = leg.key || {};
  if (!L) return null;
  if (L.state === "pre" || !L.state) return {st: "pre", text: L.start ? "Starts " + new Date(L.start).toLocaleString("en-US", {weekday: "short", hour: "numeric", minute: "2-digit"}) : "Not started", score: ""};
  const score = `${L.awayAbbr} ${L.away}–${L.home} ${L.homeAbbr}`, fin = L.state === "post", clock = fin ? "Final" : (L.detail || "Live");
  if (k.t === "prop") {
    if (L.cur == null) return {st: fin ? "unk" : "live", text: fin ? "No stat line found: settle it yourself" : "Waiting on stats", score, clock};
    const over = (k.dir || "over") === "over", need = Math.floor(k.l) + 1, cur = L.cur, hit = cur > k.l;
    const st = over ? (hit ? "hit" : fin ? "dead" : "live") : (hit ? "dead" : fin ? "hit" : "live");
    const left = over ? Math.max(need - cur, 0) : Math.max(Math.floor(k.l) - cur, 0);
    const text = over ? (hit ? `${cur} ${L.unit || ""} · cashed ✓` : `${cur} of ${need} ${L.unit || ""} · need ${left} more`)
                      : (hit ? `${cur} ${L.unit || ""} · over the line` : `${cur} ${L.unit || ""} · ${left} to spare`);
    return {st, text, score, clock, pct: over ? Math.min(cur / need, 1) : Math.min(cur / (Math.floor(k.l) + 1), 1)};
  }
  const tot = L.home + L.away, mine = k.s === "home" ? L.home - L.away : L.away - L.home;
  if (k.m === "total" || k.m === "p1_total") {
    const over = k.s === "over", hit = tot > k.l, need = Math.floor(k.l) + 1;
    const st = over ? (hit ? "hit" : fin ? "dead" : "live") : (hit ? "dead" : fin ? "hit" : "live");
    return {st, score, clock, pct: Math.min(tot / need, 1),
            text: over ? (hit ? `Total ${tot} · over ✓` : `Total ${tot} · need ${need - tot} more`) : (hit ? `Total ${tot} · over the line` : `Total ${tot} · ${Math.floor(k.l) - tot} to spare`)};
  }
  if (k.m === "spread" || k.m === "puckline") {
    const cov = mine + k.l;
    return {st: cov > 0 ? (fin ? "hit" : "live up") : cov < 0 ? (fin ? "dead" : "live down") : (fin ? "push" : "live"), score, clock,
            text: cov > 0 ? `Covering by ${cov}` : cov < 0 ? `Need ${-cov} more to cover` : "Right on the number"};
  }
  return {st: mine > 0 ? (fin ? "hit" : "live up") : mine < 0 ? (fin ? "dead" : "live down") : (fin ? "push" : "live"), score, clock,
          text: mine > 0 ? `Leading by ${mine}` : mine < 0 ? `Trailing by ${-mine}` : "Tied"};
}
function mbSweatHtml(leg) {
  const w = mbSweat(leg); if (!w) return "";
  const sts = w.st.split(" ").map(x => "s-" + x).join(" "), cls = "s-" + w.st.split(" ")[0];
  return `<div class="swt ${sts}"><span class="swd ${cls}"></span><div class="swb"><div class="swl"><b>${esc(w.text)}</b>${w.score ? `<i>${esc(w.score)} · ${esc(w.clock)}</i>` : ""}</div>
    ${w.pct != null ? `<div class="swbar"><span style="width:${Math.round(100 * w.pct)}%"></span></div>` : ""}</div></div>`;
}
function mbIsLive(b) { return b.status === "open" && b.legs.some(l => { const w = mbSweat(l); return w && w.st !== "pre"; }); }
function mbLiveBanner() {
  const s = mbLoad(), D = mbDaily(s);
  const daily = D.claimed ? "" : `<button class="swbanner dailybanner" data-gobets="1"><span>🎁</span><b>Daily bonus ready</b><i>day ${D.streak} · +${mbMoney(D.amount)}</i><span>→</span></button>`;
  return daily + mbSweatBanner(s);
}
function mbSweatBanner(s) {
  const open = s.bets.filter(b => b.status === "open" && b.sport === MB_PAGE), live = open.filter(mbIsLive);
  if (!live.length) return "";
  const hitting = live.filter(b => b.legs.every(l => { const w = mbSweat(l); return w && /hit|up/.test(w.st); })).length;
  return `<button class="swbanner" data-gobets="1"><span class="livedot"></span><b>Sweating ${live.length} live bet${live.length > 1 ? "s" : ""}</b><i>${hitting ? hitting + " on track" : "tap to follow"}</i><span>→</span></button>`;
}
function mbWireBanner(render) {
  document.querySelectorAll("[data-gobets]").forEach(b => b.onclick = () => { mbHaptic(); MB_VIEW = "bets"; if (typeof TAB !== "undefined") TAB = "check"; render(); window.scrollTo(0, 0); });
}

// ---- come back tomorrow: daily paper bonus that grows with the streak, and VIP tiers from XP ----
const TIERS = [["Rookie", 0, "🥉"], ["Pro", 250, "🥈"], ["All-Star", 750, "🥇"], ["MVP", 2000, "💎"], ["Hall of Fame", 5000, "👑"]];
function mbXP(s) { return s.bets.length * 10 + s.bets.filter(b => b.status === "won").length * 25 + (s.claims || 0) * 15; }
function mbTier(xp) {
  let i = 0; TIERS.forEach((t, j) => { if (xp >= t[1]) i = j; });
  const cur = TIERS[i], nxt = TIERS[i + 1];
  return {cur, nxt, pct: nxt ? (xp - cur[1]) / (nxt[1] - cur[1]) : 1};
}
const mbDay = (off = 0) => { const d = new Date(Date.now() - off * 864e5); return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate(); };
function mbDaily(s = mbLoad()) {
  const d = s.daily || {}, claimed = d.last === mbDay(0);
  const streak = claimed ? d.streak : (d.last === mbDay(1) ? (d.streak || 0) + 1 : 1);
  return {claimed, streak, amount: 25 + 10 * Math.min(streak - 1, 7), next: 25 + 10 * Math.min(streak, 7)};
}
function mbClaim() {
  const s = mbLoad(), D = mbDaily(s); if (D.claimed) return;
  s.daily = {last: mbDay(0), streak: D.streak}; s.bonus = (s.bonus || 0) + D.amount; s.claims = (s.claims || 0) + 1; mbSave(s);
  mbHaptic("success"); mbBurst(26, ["💵", "✨", "🎁"]);
  mbToast(`<div class="tbig">🎁 Daily bonus</div><div class="tamt">+${mbMoney(D.amount)}</div><div class="tsub">🔥 ${D.streak}-day streak · come back tomorrow for ${mbMoney(D.next)}</div>`, "win");
}
function mbDailyHtml(s) {
  const D = mbDaily(s), filled = Math.min(D.claimed ? D.streak : D.streak - 1, 7), dots = Array.from({length: 7}, (_, i) => `<span class="${i < filled ? "on" : ""}"></span>`).join("");
  return D.claimed
    ? `<div class="daily done"><div class="gift">✅</div><div class="dt"><b>Bonus claimed · 🔥 ${D.streak}-day streak</b><i>Come back tomorrow for ${mbMoney(D.next)} paper</i><div class="streakdots">${dots}</div></div></div>`
    : `<div class="daily"><div class="gift">🎁</div><div class="dt"><b>Daily bonus · day ${D.streak}</b><i>+${mbMoney(D.amount)} paper · grows every day you come back</i><div class="streakdots">${dots}</div></div><button class="claim" id="mbclaim">Claim</button></div>`;
}

// ---- live sportsbook prices: DraftKings lines from ESPN's public scoreboard (no key, refreshed with the live scores) ----
const LIVEODDS = {};   // gid -> {book, ml: {home, away}, spread: {home: {line, odds}, away}, total: {over: {line, odds}, under}, ts}
function mbParseEspnOdds(comp) {
  const o = ((comp || {}).odds || [])[0]; if (!o) return null;
  const n = v => { const x = Number(String(v || "").replace(/[ou+]/g, "").replace("EVEN", "100")); return isFinite(x) && x !== 0 ? x : null; };
  const side = (blk, k) => { const c = ((blk || {})[k] || {}).current || ((blk || {})[k] || {}).close || {}; return {line: n(c.line), odds: n(c.odds)}; };
  const out = {book: (o.provider || {}).name || "Sportsbook", ts: Date.now(),
    ml: {home: side(o.moneyline, "home").odds, away: side(o.moneyline, "away").odds},
    spread: {home: side(o.pointSpread, "home"), away: side(o.pointSpread, "away")},
    total: {over: side(o.total, "over"), under: side(o.total, "under")}};
  if (out.ml.home == null && o.homeTeamOdds && o.homeTeamOdds.moneyLine) { out.ml.home = Number(o.homeTeamOdds.moneyLine); out.ml.away = Number((o.awayTeamOdds || {}).moneyLine) || null; }
  if (out.total.over.line == null && o.overUnder) { out.total.over.line = out.total.under.line = Number(o.overUnder); }
  return out;
}
// the book's price for a game leg, only when the book hangs the same number
function mbBookOdds(leg) {
  const k = leg.key || {};
  if (k.t === "prop") { try { return typeof mbPropOdds === "function" ? mbPropOdds(leg) : null; } catch (e) { return null; } }
  const L = LIVEODDS[leg.gid]; if (!L || k.t !== "game") return null;
  const same = (a, b) => a != null && b != null && Math.abs(a - b) < 1e-6;
  if (k.m === "moneyline" || k.m === "ml") return L.ml[k.s] ? {odds: L.ml[k.s], book: L.book} : null;
  if (k.m === "spread" || k.m === "puckline") { const x = L.spread[k.s]; return x && x.odds && same(x.line, k.l) ? {odds: x.odds, book: L.book} : null; }
  if (k.m === "total") { const x = L.total[k.s]; return x && x.odds && same(x.line, k.l) ? {odds: x.odds, book: L.book} : null; }
  return null;
}
