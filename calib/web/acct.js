// ---------- 🏦 ACCOUNT: wallet (deposit / withdraw / statement), ticket receipts, profile, live alerts ----------
// Everything a real book has around the bets. Builds on bets.js (wallet, tickets) and stakes.js (hold to confirm).

// ---- ledger: every money movement that isn't a bet (bets and payouts come from the bets themselves) ----
function mbTx(s, type, amt, note) {
  s.tx = s.tx || [];
  s.tx.push({id: (type === "deposit" ? "DP" : type === "withdrawal" ? "WD" : "TX") + Date.now().toString(36).toUpperCase().slice(-6) + Math.random().toString(36).slice(2, 4).toUpperCase(),
    ts: new Date().toISOString(), type, amt: Math.round(amt * 100) / 100, note});
  if (s.tx.length > 600) s.tx = s.tx.slice(-600);
  return s.tx[s.tx.length - 1];
}
const mbTicketNo = id => { const c = String(id || "").replace(/[^A-Za-z0-9]/g, "").toUpperCase(); return "BZ-" + [c.slice(0, 4), c.slice(4, 8), c.slice(8)].filter(Boolean).join("-"); };
function acctCreated(s) {
  if (!s.created) s.created = [...s.bets.map(b => b.ts), ...(s.tx || []).map(t => t.ts)].sort()[0] || new Date().toISOString();
  return s.created;
}
// the statement: newest first, with the balance after each line (ends at what you can bet right now)
function mbStatement(s = mbLoad()) {
  const created = acctCreated(s), rows = [{ts: created, type: "open", amt: s.start, note: "Account opened · welcome bankroll"}];
  const txSum = (s.tx || []).reduce((a, t) => a + t.amt, 0), legacy = Math.round(((s.bonus || 0) - txSum) * 100) / 100;
  if (Math.abs(legacy) >= 0.01) rows.push({ts: created, type: "bonus", amt: legacy, note: "Rewards & bonuses to date"});
  rows.push(...(s.tx || []));
  for (const b of s.bets) {
    rows.push({ts: b.ts, type: "bet", amt: -b.stake, note: b.label, bet: b.id});
    if (b.status === "open") continue;
    const back = b.stake + mbProfit(b);
    if (back > 0.004) rows.push({ts: b.result_ts || b.ts, type: b.status === "cashout" ? "cashout" : b.status === "won" ? "payout" : "refund", amt: back, note: b.label, bet: b.id});
  }
  rows.sort((a, b) => a.ts.localeCompare(b.ts) || (a.type === "open" ? -1 : b.type === "open" ? 1 : 0));
  let bal = 0; for (const r of rows) { bal += r.amt; r.bal = bal; }
  return rows.reverse();
}
const TX_UI = {open: ["🏦", "Account opened"], deposit: ["⬇️", "Deposit"], withdrawal: ["⬆️", "Withdrawal"], bonus: ["🎁", "Bonus"], reward: ["🎁", "Reward"],
  bet: ["🎟️", "Bet placed"], payout: ["💰", "Payout"], cashout: ["💸", "Cash out"], refund: ["↩️", "Refund"], pro: ["⚡", "Blitzed Pro"], reset: ["🔄", "Bankroll reset"]};
function mbDayLabel(ts) {
  const d = new Date(ts), t = new Date(), y = new Date(Date.now() - 864e5), same = (a, b) => a.toDateString() === b.toDateString();
  return same(d, t) ? "Today" : same(d, y) ? "Yesterday" : d.toLocaleDateString("en-US", {weekday: "short", month: "short", day: "numeric"});
}
// any list → day headers + rows
function mbByDay(list, tsOf, row) {
  let last = "", out = "";
  for (const x of list) { const k = mbDayLabel(tsOf(x)); if (k !== last) { out += `<div class="dayh">${k}</div>`; last = k; } out += row(x); }
  return out;
}

// ---- 💳 the Wallet tab (inside My Bets) ----
function acctWalletHtml() {
  const s = mbLoad(), W = mbWallet(s), rows = mbStatement(s), dep = (s.tx || []).filter(t => t.type === "deposit").reduce((a, t) => a + t.amt, 0);
  return `<section class="wl-card"><div class="wl-k">Available to bet</div><div class="wl-bal">${mbMoney(W.available)}</div>
      <div class="wl-sub"><span>In play <b>${mbMoney(W.risk)}</b></span><span>Bankroll <b>${mbMoney(W.bankroll)}</b></span><span>Deposited <b>${mbShort(s.start + dep)}</b></span></div>
      <div class="wl-acts"><button class="wl-dep" data-cashier="deposit">Deposit</button><button class="wl-wd" data-cashier="withdraw">Withdraw</button></div></section>
    <div class="wl-h"><b>Transactions</b><em>${rows.length}</em></div>
    <div class="wl-list">${mbByDay(rows.slice(0, 120), r => r.ts, r => { const [ic, nm] = TX_UI[r.type] || ["•", r.type];
      return `<div class="tx ${r.amt >= 0 ? "in" : "out"}" ${r.bet ? `data-tk="${esc(r.bet)}"` : ""}><span class="tx-ic">${ic}</span><span class="tx-t"><b>${nm}</b><i>${esc(r.note || "")}</i></span>
        <span class="tx-a"><b>${r.amt >= 0 ? "+" : "−"}${mbMoney(Math.abs(r.amt)).replace("−", "")}</b><i>${mbMoney(r.bal)}</i></span></div>`; })}</div>`;
}

// ---- cashier: deposit / withdraw, with a receipt ----
let CASH_MODE = "deposit", CASH_AMT = 100;
function acctDepToday(s) { const d = new Date().toDateString(); return (s.tx || []).filter(t => t.type === "deposit" && new Date(t.ts).toDateString() === d).reduce((a, t) => a + t.amt, 0); }
function mbOpenCashier(mode) {
  if (mode) CASH_MODE = mode;
  const sh = document.getElementById("sheet"), s = mbLoad(), W = mbWallet(s), lim = (s.lim || {}).dep || 0, left = lim ? Math.max(0, lim - acctDepToday(s)) : Infinity;
  const dep = CASH_MODE === "deposit", amt = Number(CASH_AMT) || 0;
  const err = !(amt > 0) ? "Enter an amount" : dep && amt > left ? `Daily deposit limit: ${mbShort(left)} left today` : !dep && amt > W.available ? `You can withdraw up to ${mbMoney(W.available)}` : "";
  sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>
    <div class="sh-t">Cashier</div>
    <div class="gseg c cs-seg"><button class="${dep ? "on" : ""}" data-cm="deposit">Deposit</button><button class="${dep ? "" : "on"}" data-cm="withdraw">Withdraw</button></div>
    <div class="cs-amt"><em>$</em><input id="csamt" inputmode="decimal" value="${amt || ""}" aria-label="Amount"></div>
    <div class="cs-chips">${(dep ? [50, 100, 250, 500, 1000] : [50, 100, 250, Math.floor(W.available)]).filter((x, i, a) => x > 0 && a.indexOf(x) === i).map(a => `<button class="${amt === a ? "on" : ""}" data-ca="${a}">${a === Math.floor(W.available) && !dep ? "All" : mbShort(a)}</button>`).join("")}</div>
    <div class="cs-method"><span class="cs-mi">⚡</span><span><b>Blitzed Wallet</b><i>Instant · no fees</i></span><span class="cs-ok">✓</span></div>
    <div class="cs-rows"><div><span>${dep ? "Balance now" : "Available"}</span><b>${mbMoney(W.available)}</b></div><div><span>After ${dep ? "deposit" : "withdrawal"}</span><b>${mbMoney(W.available + (dep ? 1 : -1) * (err ? 0 : amt))}</b></div>
      ${dep && lim ? `<div><span>Daily limit</span><b>${mbShort(left)} of ${mbShort(lim)} left</b></div>` : ""}</div>
    <button class="placebet c" id="csgo" ${err ? "disabled" : ""}><span>${err || `${window.MB_TAP_PLACE ? (dep ? "Deposit" : "Withdraw") : (dep ? "Hold to deposit" : "Hold to withdraw")} ${mbMoney(amt)}`}</span></button>`;
  document.getElementById("shx").onclick = () => closeSheet();
  sh.querySelectorAll("[data-cm]").forEach(b => b.onclick = () => { mbHaptic(); CASH_MODE = b.dataset.cm; mbOpenCashier(); });
  sh.querySelectorAll("[data-ca]").forEach(b => b.onclick = () => { mbHaptic(); CASH_AMT = Number(b.dataset.ca); mbOpenCashier(); });
  const inp = document.getElementById("csamt"); inp.onchange = () => { CASH_AMT = Number(inp.value.replace(/[^0-9.]/g, "")); mbOpenCashier(); };
  const go = document.getElementById("csgo");
  const fire = () => {
    const s2 = mbLoad(), a = Math.round(amt * 100) / 100;
    s2.bonus = (s2.bonus || 0) + (dep ? a : -a); const t = mbTx(s2, dep ? "deposit" : "withdrawal", dep ? a : -a, dep ? "Blitzed Wallet · instant" : "To Blitzed Wallet");
    mbSave(s2); mbHaptic("success"); try { funBlip(); } catch (e) {}
    sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>
      <div class="cs-done"><div class="okring">✓</div><div class="sh-t">${dep ? "Deposit successful" : "Withdrawal complete"}</div><div class="cs-big">${dep ? "+" : "−"}${mbMoney(a)}</div>
      <div class="cs-rows"><div><span>Reference</span><b>${t.id}</b></div><div><span>Method</span><b>Blitzed Wallet</b></div><div><span>Time</span><b>${new Date(t.ts).toLocaleString("en-US", {month: "short", day: "numeric", hour: "numeric", minute: "2-digit"})}</b></div>
      <div><span>New balance</span><b>${mbMoney(mbWallet().available)}</b></div></div><button class="placebet c" id="csok"><span>Done</span></button></div>`;
    document.getElementById("shx").onclick = document.getElementById("csok").onclick = () => { closeSheet(); MB_RENDER && MB_RENDER(); };
    if (dep) try { mbCoins(document.querySelector(".cs-big"), 12); } catch (e) {}
  };
  if (go && !err) { if (typeof stkHold === "function") stkHold(go, fire); else go.onclick = fire; }
  document.getElementById("scrim").classList.add("open"); sh.classList.add("open");
}

// ---- 🎟️ ticket receipt ----
function mbOpenTicket(id) {
  const s = mbLoad(), b = s.bets.find(x => x.id === id); if (!b) return;
  const sh = document.getElementById("sheet"), fmt = t => new Date(t).toLocaleString("en-US", {weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit"});
  const stamp = {open: "Accepted", won: "Winner", lost: "Lost", push: "Push", cashout: "Cashed out"}[b.status];
  const toWin = b.stake * (mbDec(b.odds) - 1) * (1 + (b.boost || 0)), co = mbCashOffer(b);
  const legs = b.legs.map(l => { let live = null; try { live = typeof mbLiveLeg === "function" ? mbLiveLeg(l) : null; } catch (e) {}
    const st = l.res === true ? "w" : l.res === false ? "l" : l.res === "push" ? "p" : "";
    const now = live && live.cur != null ? `${live.cur} ${live.unit}` : live && live.state && live.state !== "pre" ? `${live.awayAbbr} ${live.away}–${live.home} ${live.homeAbbr}${live.state === "post" ? " · Final" : ""}` : "";
    return `<div class="rc-leg ${st}"><span class="rc-res">${st === "w" ? "✓" : st === "l" ? "✕" : st === "p" ? "–" : ""}</span>${mbPic(l)}<span class="rc-lt"><b>${esc(l.label)}</b><i>${esc(l.sub || "")}${now ? ` · <em>${esc(now)}</em>` : ""}</i></span><span class="rc-lo">${l.odds ? mbSign(l.odds) : ""}</span></div>`; }).join("");
  const paid = b.status === "open" ? null : b.stake + mbProfit(b);
  sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>
    <div class="rc"><div class="rc-top"><span class="rc-brand"><img src="bolt.png" alt="">BLITZED</span><span class="rc-stamp ${b.status}">${stamp}</span></div>
      <div class="rc-kind">${b.sport} · ${b.kind === "parlay" ? `${b.legs.length}-leg ${b.sgp ? "Same Game Parlay" : "parlay"}` : "Single"}${b.boost ? ` · 🚀 +${100 * b.boost}%` : ""}</div>
      <div class="rc-legs">${legs}</div>
      <div class="rc-tear"></div>
      <div class="rc-rows"><div><span>Odds</span><b>${mbSign(b.odds)}</b></div><div><span>Stake</span><b>${mbMoney(b.stake)}</b></div>
        <div><span>${paid == null ? "To win" : "Returned"}</span><b class="${paid != null && paid > b.stake ? "pos" : ""}">${mbMoney(paid == null ? toWin : paid)}</b></div>
        <div><span>Placed</span><b>${fmt(b.ts)}</b></div>${b.result_ts ? `<div><span>Settled</span><b>${fmt(b.result_ts)}</b></div>` : ""}</div>
      <div class="rc-bar"></div><div class="rc-no">${mbTicketNo(b.id)}</div></div>
    ${co ? `<button class="cashout" data-co="${b.id}"><span>Cash out</span><b>${mbMoney(co.value)}</b></button>` : ""}
    ${b.status === "won" || (b.status === "cashout" && (b.cash || 0) > b.stake) ? `<button class="placebet c" data-share="${b.id}"><span>Share ticket</span></button>` : ""}`;
  document.getElementById("shx").onclick = () => closeSheet();
  sh.querySelectorAll("[data-share]").forEach(x => x.onclick = () => { try { mbShareBet(b.id); } catch (e) {} });
  if (co) acctWireCashOut(sh, () => { closeSheet(); MB_RENDER && MB_RENDER(); });
  document.getElementById("scrim").classList.add("open"); sh.classList.add("open");
}
// cash out confirms with the same press-and-hold as placing a bet
function acctWireCashOut(root, done) {
  (root || document).querySelectorAll("[data-co]").forEach(btn => {
    const fire = () => {
      const s = mbLoad(), b = s.bets.find(x => x.id === btn.dataset.co), co = b && mbCashOffer(b); if (!co) return;
      b.status = "cashout"; b.cash = co.value; b.result_ts = new Date().toISOString(); b.seen = true; mbSave(s);
      mbHaptic("success"); try { funBlip(); } catch (e) {} mbBurst(20, ["💸", "✨"]);
      mbAlert("💸 Cashed out " + mbMoney(co.value), `${b.label} · ${co.value >= b.stake ? "+" : "−"}${mbMoney(Math.abs(co.value - b.stake))}`, co.value >= b.stake ? "win" : "");
      done && done();
    };
    const lab = btn.querySelector("span"); if (lab && !window.MB_TAP_PLACE) lab.textContent = "Hold to cash out";
    if (typeof stkHold === "function") stkHold(btn, fire); else btn.onclick = fire;
  });
}

// ---- 👤 profile & account ----
const acctName = (s = mbLoad()) => (s.name || "Mike").trim() || "Mike";
const acctIni = n => n.split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
function mbOpenAccount() {
  const s = mbLoad(), W = mbWallet(s), st = mbStats(s.bets), done = s.bets.filter(b => b.status !== "open"), nm = acctName(s), lim = s.lim || {};
  const since = new Date(acctCreated(s)).toLocaleDateString("en-US", {month: "long", year: "numeric"}); mbSave(s);
  const sel = (id, cur, opts) => `<select id="${id}">${opts.map(([v, n]) => `<option value="${v}" ${Number(cur || 0) === v ? "selected" : ""}>${n}</option>`).join("")}</select>`;
  const sh = document.getElementById("sheet");
  sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>
    <div class="ac-top"><div class="ac-av ${s.pro ? "pro" : ""}">${esc(acctIni(nm))}</div><div class="ac-id"><input id="acname" value="${esc(nm)}" maxlength="24" aria-label="Your name">
      <i>${s.pro ? "⚡ Blitzed Pro · " : ""}Member since ${since}</i></div></div>
    <div class="ac-stats"><div><b>${s.bets.length}</b><span>Bets</span></div><div><b>${done.filter(b => b.status === "won").length}–${done.filter(b => b.status === "lost").length}</b><span>Record</span></div>
      <div><b class="${st.roi >= 0 ? "pos" : "neg"}">${(st.roi >= 0 ? "+" : "") + (100 * st.roi).toFixed(1)}%</b><span>ROI</span></div><div><b>${st.bigWin ? mbShort(st.bigWin) : "–"}</b><span>Best win</span></div></div>
    <div class="ac-bal"><span>Balance</span><b>${mbMoney(W.available)}</b><button data-cashier="deposit">Deposit</button><button data-cashier="withdraw" class="alt">Withdraw</button></div>
    <div class="ac-h">Account</div>
    <div class="ac-list"><button class="ac-row" data-acgo="wallet"><span>💳</span><b>Wallet &amp; transactions</b><em>›</em></button>
      <button class="ac-row" data-acgo="settled"><span>🎟️</span><b>Bet history</b><em>›</em></button>
      <button class="ac-row" data-acgo="rewards"><span>🏆</span><b>Rewards &amp; Season Pass</b><em>›</em></button></div>
    <div class="ac-h">Play responsibly</div>
    <div class="ac-list"><label class="ac-row"><span>🛑</span><b>Daily deposit limit</b>${sel("aclim", lim.dep, [[0, "None"], [100, "$100"], [250, "$250"], [500, "$500"], [1000, "$1,000"]])}</label>
      <label class="ac-row"><span>⏱️</span><b>Session reminder</b>${sel("acsess", lim.sess, [[0, "Off"], [30, "30 min"], [60, "1 hour"], [120, "2 hours"]])}</label>
      <label class="ac-row"><span>✋</span><b>Hold to place bets</b><input type="checkbox" id="achold" ${s.tapPlace ? "" : "checked"}></label>
      <label class="ac-row"><span>📏</span><b>Unit size (1u)</b>${sel("acunit", typeof rcUnit === "function" ? rcUnit(s) : 100, [[10, "$10"], [25, "$25"], [50, "$50"], [100, "$100"], [250, "$250"], [500, "$500"], [1000, "$1,000"]])}</label>
      <label class="ac-row"><span>🔁</span><b>Show results in units</b><input type="checkbox" id="acshowu" ${s.showUnits ? "checked" : ""}></label>
      <label class="ac-row"><span>🔔</span><b>Sounds &amp; alerts</b><input type="checkbox" id="acsnd" ${s.sound !== false ? "checked" : ""}></label></div>
    <div class="ac-foot">Blitzed is a free-to-play sportsbook simulator: balances have no cash value.</div>`;
  document.getElementById("shx").onclick = () => { closeSheet(); MB_RENDER && MB_RENDER(); };
  const save = f => { const s2 = mbLoad(); f(s2); mbSave(s2); };
  document.getElementById("acname").onchange = e => save(s2 => { s2.name = e.target.value.trim().slice(0, 24); });
  document.getElementById("aclim").onchange = e => save(s2 => { s2.lim = Object.assign({}, s2.lim, {dep: Number(e.target.value)}); });
  document.getElementById("acsess").onchange = e => save(s2 => { s2.lim = Object.assign({}, s2.lim, {sess: Number(e.target.value)}); });
  document.getElementById("achold").onchange = e => { save(s2 => { s2.tapPlace = !e.target.checked; }); window.MB_TAP_PLACE = !e.target.checked; };
  document.getElementById("acunit").onchange = e => save(s2 => { s2.unitSize = Number(e.target.value); });
  document.getElementById("acshowu").onchange = e => save(s2 => { s2.showUnits = e.target.checked; });
  document.getElementById("acsnd").onchange = e => save(s2 => { s2.sound = e.target.checked; });
  sh.querySelectorAll("[data-cashier]").forEach(b => b.onclick = () => { mbHaptic(); mbOpenCashier(b.dataset.cashier); });
  sh.querySelectorAll("[data-acgo]").forEach(b => b.onclick = () => { mbHaptic(); closeSheet(); const k = b.dataset.acgo;
    if (k === "rewards") TAB = "rewards"; else { TAB = "check"; MB_VIEW = "bets"; MB_BTAB = k; } MB_RENDER && MB_RENDER(); window.scrollTo(0, 0); });
  document.getElementById("scrim").classList.add("open"); sh.classList.add("open");
}

// ---- 🔔 alerts: a banner from the top, like a push notification (while the app is open) ----
function mbAlert(title, sub, kind) {
  if (mbLoad().sound === false && kind === "quiet") return;
  const box = document.getElementById("bzalerts") || Object.assign(document.body.appendChild(document.createElement("div")), {id: "bzalerts"});
  const a = document.createElement("div"); a.className = "bza " + (kind || "");
  a.innerHTML = `<img src="icon-192.png" alt=""><div><span class="bza-h"><b>BLITZED</b><i>now</i></span><b class="bza-t">${title}</b>${sub ? `<span class="bza-s">${esc(sub)}</span>` : ""}</div>`;
  box.prepend(a); requestAnimationFrame(() => a.classList.add("in"));
  try { mbHaptic(kind === "win" ? "success" : undefined); if (mbLoad().sound !== false) funBlip(); } catch (e) {}
  const bye = () => { a.classList.remove("in"); setTimeout(() => a.remove(), 350); };
  a.onclick = bye; setTimeout(bye, 5200);
  while (box.children.length > 3) box.lastChild.remove();
}
// live: a stat ticks for your player prop, or a goal / score in a game you're on
const ACCT_SEEN = {};
function acctLiveAlerts() {
  if (typeof mbLiveLeg !== "function") return;
  const s = mbLoad(), games = {};
  for (const b of s.bets) { if (b.status !== "open") continue;
    for (const l of b.legs) { if (l.res !== undefined && l.res !== null) continue;
      let L; try { L = mbLiveLeg(l); } catch (e) { L = null; } if (!L || L.state === "pre") continue;
      const k = l.key || {};
      if (k.t === "prop" && L.cur != null) { const id = b.id + "|" + l.label, was = ACCT_SEEN[id]; ACCT_SEEN[id] = L.cur;
        if (was != null && L.cur > was) { const hit = k.dir !== "under" && L.cur > k.l, nm = k.name || l.label;
          mbAlert(k.mk === "goals" ? `🚨 GOAL · ${esc(nm)}` : `📈 ${esc(nm)}: ${L.cur} ${L.unit}`, hit ? `${l.label} · ✅ that leg is a winner` : `${l.label} · ${Math.max(0, Math.floor(k.l) + 1 - L.cur)} to go`, hit ? "win" : ""); } }
      games[l.gid] = L; }
  }
  for (const [gid, L] of Object.entries(games)) { const sc = L.home + L.away, was = ACCT_SEEN["g" + gid]; ACCT_SEEN["g" + gid] = sc;
    if (was != null && sc > was) mbAlert(`🚨 Score · ${L.awayAbbr} ${L.away}–${L.home} ${L.homeAbbr}`, "A game on your slip just changed", ""); }
}
// legs that hit while the rest of the parlay is still going
function acctLegHits(before, after) {
  for (const b of after.bets) { if (b.status !== "open" || b.kind !== "parlay") continue; const o = before[b.id]; if (!o) continue;
    b.legs.forEach((l, i) => { if (l.res === true && o[i] !== true) mbAlert("✅ Leg hit", `${l.label} · ${b.legs.filter(x => x.res !== true).length} to go on your ${b.legs.length}-leg`, "win"); }); }
}
// responsible play: a gentle reminder after N minutes in the app
let ACCT_T0 = (() => { try { const t = Number(sessionStorage.getItem("bz_t0")); if (t) return t; const n = Date.now(); sessionStorage.setItem("bz_t0", n); return n; } catch (e) { return Date.now(); } })(), ACCT_NAG = 0;
setInterval(() => { try { const m = (mbLoad().lim || {}).sess; if (!m) return; const mins = (Date.now() - ACCT_T0) / 6e4;
  if (mins >= m * (ACCT_NAG + 1)) { ACCT_NAG++; mbAlert(`⏱️ You've been on Blitzed for ${Math.round(mins)} min`, "Take a breather? Your bets keep running while you're away.", ""); } } catch (e) {} }, 60000);

// ---- wiring (every render) ----
function acctAfterRender(render) {
  const s = mbLoad(); if (s.tapPlace != null) window.MB_TAP_PLACE = !!s.tapPlace;
  document.querySelectorAll("[data-cashier]").forEach(b => b.onclick = e => { e.stopPropagation(); mbHaptic(); mbOpenCashier(b.dataset.cashier); });
  document.querySelectorAll("#view [data-tk], #view .ticket[data-tid]").forEach(t => t.onclick = e => { if (e.target.closest("button, a, input, summary, details")) return; mbHaptic(); mbOpenTicket(t.dataset.tk || t.dataset.tid); });
  acctWireCashOut(document.getElementById("view"), render);
  document.querySelectorAll("[data-action-share]").forEach(b => b.onclick = () => { mbHaptic(); mbShareAction(); });
  // the avatar on the league row opens your account
  const hb2 = document.querySelector(".hb2");
  if (hb2 && !hb2.querySelector(".sh-av")) { const a = document.createElement("button"); a.className = "sh-av"; a.setAttribute("aria-label", "Account");
    hb2.appendChild(a); a.onclick = () => { mbHaptic(); mbOpenAccount(); }; }
  const av = hb2 && hb2.querySelector(".sh-av"); if (av) { av.textContent = acctIni(acctName(s)); av.classList.toggle("pro", !!s.pro); }
  try { acctLiveAlerts(); } catch (e) {}
}

// ---- 📤 my action: a shareable graphic of your open bets — picks and prices only, no stakes or payouts ----
const ACT_IMG = {};
function actImg(src) {
  if (!src) return Promise.resolve(null);
  if (ACT_IMG[src]) return ACT_IMG[src];
  const load = u => new Promise(r => { const im = new Image(); im.crossOrigin = "anonymous"; let done = false;
    const fin = v => { if (!done) { done = true; r(v); } }; im.onload = () => fin(im.naturalWidth ? im : null); im.onerror = () => fin(null); setTimeout(() => fin(null), 5000); im.src = u; });
  // NHL headshots don't allow canvas use; the relay serves the same public image with CORS headers
  const relay = u => load(`https://wsrv.nl/?url=${encodeURIComponent(u.replace(/^https?:\/\//, ""))}&w=240&output=png`);
  const alt = typeof MB_IMG_ALT !== "undefined" ? MB_IMG_ALT[src] : null;   // this season's mug missing -> the player's latest one
  return ACT_IMG[src] = load(src).then(im => im || relay(src)).then(im => im || (alt ? load(alt).then(i2 => i2 || relay(alt)) : null));
}
function actArt(l) {   // {img, logo, logos} for a leg, same rules as the app's pick art
  let a = {img: l.img, logo: l.logo, logos: l.logos, name: l.name || (l.key || {}).name || l.label};
  if (!a.img && !a.logos && typeof mbArtFor === "function") { try { Object.assign(a, mbArtFor(l) || {}); } catch (e) {} }
  if (!a.img && !a.logos && !a.logo) { const t = mbTeamsIn(l); if ((l.key || {}).t === "prop") a.logo = t[0]; else if (t.length >= 2) a.logos = t.slice(0, 2); else a.logo = t[0]; }
  return a;
}
async function actDrawArt(x, a, cx, cy, r) {   // a round avatar: headshot with a team badge, or two overlapping logos
  const circ = (X, Y, R, fill) => { x.beginPath(); x.arc(X, Y, R, 0, 7); x.fillStyle = fill; x.fill(); };
  const clipDraw = async (src, X, Y, R, cover) => { const im = await actImg(src); if (!im) return false; x.save(); x.beginPath(); x.arc(X, Y, R, 0, 7); x.clip();
    if (cover) { const s = Math.max(2 * R / im.width, 2 * R / im.height); x.drawImage(im, X - im.width * s / 2, Y - R * 0.95, im.width * s, im.height * s); }
    else { const s = Math.min(1.5 * R / im.width, 1.5 * R / im.height); x.drawImage(im, X - im.width * s / 2, Y - im.height * s / 2, im.width * s, im.height * s); }
    x.restore(); return true; };
  if (a.logos && a.logos.length >= 2) {
    const o = r * 0.5, q = r * 0.62;   // two logos side by side with a slight overlap, the second ringed so both read
    circ(cx - o, cy, q, "#1a1c18"); await clipDraw(a.logos[0], cx - o, cy, q, false);
    circ(cx + o, cy, q + 4, "#121411"); circ(cx + o, cy, q, "#1a1c18"); await clipDraw(a.logos[1], cx + o, cy, q, false); return;
  }
  circ(cx, cy, r, "#1d201b");
  const ok = a.img ? await clipDraw(a.img, cx, cy, r, true) : a.logo ? await clipDraw(a.logo, cx, cy, r, false) : false;
  if (!ok) { x.fillStyle = "rgba(255,255,255,.75)"; x.font = `800 ${Math.round(r * 0.7)}px 'Inter Tight', sans-serif`; x.textAlign = "center"; const tb = x.textBaseline; x.textBaseline = "middle";
    x.fillText(String(a.name || "?").split(" ").filter(Boolean).slice(0, 2).map(w => w[0]).join(""), cx, cy + 2); x.textAlign = "left"; x.textBaseline = tb; }
  if (a.img && a.logo) { circ(cx + r * 0.72, cy + r * 0.72, r * 0.42, "#050605"); circ(cx + r * 0.72, cy + r * 0.72, r * 0.36, "#1d201b"); await clipDraw(a.logo, cx + r * 0.72, cy + r * 0.72, r * 0.36, false); }
}
async function mbShareAction() {
  const s = mbLoad(), open = s.bets.filter(b => b.status === "open").sort((a, b) => String((a.legs[0] || {}).start || a.ts).localeCompare(String((b.legs[0] || {}).start || b.ts)));
  if (!open.length) { mbToast(`<div class="tbig">No open bets</div><div class="tsub">Place a bet and your action shows up here</div>`); return; }
  mbToast(`<div class="tsub">Building your action card…</div>`);
  try { await Promise.all(["700 40px 'Inter Tight'", "600 28px 'Inter Tight'", "800 30px 'Inter'", "500 24px 'Inter'", "italic 900 40px 'Barlow Condensed'"].map(f => document.fonts.load(f))); } catch (e) {}
  const W = 1080, P = 64, CP = 36, F = (w, px, fam) => `${w} ${px}px ${fam === "c" ? "'Barlow Condensed'" : fam === "b" ? "'Inter'" : "'Inter Tight'"}, system-ui, sans-serif`;
  const meas = document.createElement("canvas").getContext("2d");
  const wrap = (txt, font, max) => { meas.font = font; const words = String(txt).split(" "), out = []; let line = "";
    for (const w of words) { const t = line ? line + " " + w : w; if (meas.measureText(t).width > max && line) { out.push(line); line = w; } else line = t; } if (line) out.push(line); return out.slice(0, 2); };
  const when = l => l && l.start ? new Date(l.start).toLocaleString("en-US", {weekday: "short", hour: "numeric", minute: "2-digit"}) : "";
  // geometry: card = header row + one row per pick; every row is avatar | text | price, all centred on the row's midline
  const X0 = P, X1 = W - P, AV = 76, TX = X0 + CP + AV + 24, PRICE_W = 150;
  const blocks = open.map(b => {
    const par = b.kind === "parlay";
    const tag = `${b.sport} · ${par ? (b.sgp ? "SAME GAME PARLAY" : `${b.legs.length}-LEG PARLAY`) : "SINGLE"}${b.boost ? ` · +${Math.round(100 * b.boost)}% BOOST` : ""}${mbIsLive(b) ? " · LIVE" : ""}`;
    const rows = b.legs.map(l => { const big = !par, font = F(big ? 700 : 600, big ? 40 : 32), lh = big ? 48 : 40;
      const t = wrap(l.label, font, X1 - CP - TX - (par ? PRICE_W : 20)), sub = [l.sub, when(l)].filter(Boolean).join(" · ");
      const th = t.length * lh + (sub ? 34 : 0), h = Math.max(AV + 28, th + 32);
      return {t, sub, font, lh, th, h, o: par && l.odds ? mbSign(l.odds) : "", res: l.res, art: actArt(l)}; });
    const h = 96 + rows.reduce((a, r) => a + r.h, 0) + 16;
    return {b, tag, rows, h, par};
  });
  const H = 250 + blocks.reduce((a, k) => a + k.h + 22, 0) + 96;
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H; const x = cv.getContext("2d");
  const g = x.createLinearGradient(0, 0, W, H); g.addColorStop(0, "#0d0f0b"); g.addColorStop(1, "#050605"); x.fillStyle = g; x.fillRect(0, 0, W, H);
  const glow = x.createRadialGradient(W, 0, 0, W, 0, 700); glow.addColorStop(0, "rgba(198,255,46,.2)"); glow.addColorStop(1, "rgba(0,0,0,0)"); x.fillStyle = glow; x.fillRect(0, 0, W, H);
  // header: B mark + wordmark on one baseline, date and count opposite
  const mark = await new Promise(r => { const im = new Image(); im.onload = () => r(im); im.onerror = () => r(null); im.src = "bmark.png"; });
  const mh = 54, mw = mark ? mh * mark.width / mark.height : 0;
  if (mark) x.drawImage(mark, X0, 70, mw, mh);
  x.textBaseline = "middle"; x.fillStyle = "#fff"; x.font = F("italic 900", 50, "c"); x.fillText("BLITZED", X0 + mw + (mark ? 18 : 0), 99);
  x.fillStyle = "rgba(255,255,255,.55)"; x.font = F(600, 26, "b"); x.textAlign = "right"; x.fillText(new Date().toLocaleDateString("en-US", {weekday: "long", month: "short", day: "numeric"}), X1, 99);
  x.textAlign = "left"; x.fillStyle = "#c6ff2e"; x.font = F(800, 22, "b"); x.letterSpacing = "6px"; x.fillText("MY ACTION", X0, 180); x.letterSpacing = "0px";
  x.fillStyle = "rgba(255,255,255,.55)"; x.font = F(600, 26, "b"); x.textAlign = "right"; x.fillText(`${open.length} bet${open.length > 1 ? "s" : ""}`, X1, 180); x.textAlign = "left";
  const rr = (X, Y, w, h, r) => { x.beginPath(); x.roundRect ? x.roundRect(X, Y, w, h, r) : x.rect(X, Y, w, h); };
  let y = 220;
  for (const k of blocks) {
    rr(X0, y, X1 - X0, k.h, 30); x.fillStyle = "rgba(255,255,255,.045)"; x.fill(); x.strokeStyle = "rgba(255,255,255,.09)"; x.lineWidth = 2; x.stroke();
    // header row: tag on the left, the bet's price in a lime pill on the right, sharing one midline
    const hm = y + 48;
    x.fillStyle = k.tag.includes("LIVE") ? "#ff5d5d" : "rgba(255,255,255,.5)"; x.font = F(800, 19, "b"); x.letterSpacing = "3px"; x.fillText(k.tag, X0 + CP, hm); x.letterSpacing = "0px";
    x.font = F(800, 34); const pw = Math.max(PRICE_W, x.measureText(mbSign(k.b.odds)).width + 44);
    rr(X1 - CP - pw, hm - 30, pw, 60, 18); x.fillStyle = "#c6ff2e"; x.fill();
    x.fillStyle = "#0b1000"; x.textAlign = "center"; x.fillText(mbSign(k.b.odds), X1 - CP - pw / 2, hm + 1); x.textAlign = "left";
    let ry = y + 96;
    k.rows.forEach((r, i) => {
      if (i) { x.strokeStyle = "rgba(255,255,255,.07)"; x.lineWidth = 2; x.beginPath(); x.moveTo(TX, ry); x.lineTo(X1 - CP, ry); x.stroke(); }
      r.mid = ry + r.h / 2; ry += r.h; });
    for (const r of k.rows) {
      await actDrawArt(x, r.art, X0 + CP + AV / 2, r.mid, AV / 2);
      let ty = r.mid - r.th / 2 + r.lh / 2;
      x.fillStyle = r.res === true ? "#3ee08f" : r.res === false ? "#ff6b6b" : "#fff"; x.font = r.font;
      for (const t of r.t) { x.fillText(t, TX, ty); ty += r.lh; }
      if (r.sub) { x.fillStyle = "rgba(255,255,255,.48)"; x.font = F(500, 24, "b"); x.fillText(r.sub, TX, ty - r.lh / 2 + 17); }
      if (r.o) { x.fillStyle = "rgba(255,255,255,.8)"; x.font = F(700, 30); x.textAlign = "right"; x.fillText(r.o, X1 - CP, r.mid); x.textAlign = "left"; }
    }
    y += k.h + 22;
  }
  x.fillStyle = "rgba(255,255,255,.3)"; x.font = F(600, 24, "b"); x.fillText("Picks only. Lines may move.", X0, H - 56);
  x.fillStyle = "#c6ff2e"; x.font = F("italic 900", 30, "c"); x.textAlign = "right"; x.fillText("BLITZED", X1, H - 56);
  if (mark) { const w2 = 28 * mark.width / mark.height, tw = x.measureText("BLITZED").width; x.drawImage(mark, X1 - tw - 12 - w2, H - 70, w2, 28); } x.textAlign = "left"; x.textBaseline = "alphabetic";
  cv.toBlob(blob => { if (!blob) return; const url = URL.createObjectURL(blob), file = new File([blob], `blitzed-action-${new Date().toISOString().slice(0, 10)}.png`, {type: "image/png"});
    const canShare = navigator.canShare && navigator.canShare({files: [file]});
    const d = document.createElement("div"); d.className = "shx act";
    d.innerHTML = `<div class="shx-in"><img src="${url}" alt="My action"><div class="shx-b">${canShare ? `<button class="shx-go" data-x="share">Share</button>` : ""}<a class="shx-go ${canShare ? "alt" : ""}" href="${url}" download="${file.name}">Save image</a><button class="shx-go alt" data-x="close">Close</button></div></div>`;
    document.body.appendChild(d); requestAnimationFrame(() => d.classList.add("in")); mbHaptic("success");
    const close = () => { d.classList.remove("in"); setTimeout(() => { d.remove(); URL.revokeObjectURL(url); }, 250); };
    d.onclick = e => { if (e.target === d || e.target.dataset.x === "close") close(); };
    const sb = d.querySelector('[data-x="share"]'); if (sb) sb.onclick = () => navigator.share({files: [file], title: "My action on Blitzed"}).catch(() => {});
  }, "image/png");
}
