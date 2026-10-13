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
      <label class="ac-row"><span>🔔</span><b>Sounds &amp; alerts</b><input type="checkbox" id="acsnd" ${s.sound !== false ? "checked" : ""}></label></div>
    <div class="ac-foot">Blitzed is a free-to-play sportsbook simulator: balances have no cash value.</div>`;
  document.getElementById("shx").onclick = () => { closeSheet(); MB_RENDER && MB_RENDER(); };
  const save = f => { const s2 = mbLoad(); f(s2); mbSave(s2); };
  document.getElementById("acname").onchange = e => save(s2 => { s2.name = e.target.value.trim().slice(0, 24); });
  document.getElementById("aclim").onchange = e => save(s2 => { s2.lim = Object.assign({}, s2.lim, {dep: Number(e.target.value)}); });
  document.getElementById("acsess").onchange = e => save(s2 => { s2.lim = Object.assign({}, s2.lim, {sess: Number(e.target.value)}); });
  document.getElementById("achold").onchange = e => { save(s2 => { s2.tapPlace = !e.target.checked; }); window.MB_TAP_PLACE = !e.target.checked; };
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
  // the avatar on the league row opens your account
  const hb2 = document.querySelector(".hb2");
  if (hb2 && !hb2.querySelector(".sh-av")) { const a = document.createElement("button"); a.className = "sh-av"; a.setAttribute("aria-label", "Account");
    hb2.appendChild(a); a.onclick = () => { mbHaptic(); mbOpenAccount(); }; }
  const av = hb2 && hb2.querySelector(".sh-av"); if (av) { av.textContent = acctIni(acctName(s)); av.classList.toggle("pro", !!s.pro); }
  try { acctLiveAlerts(); } catch (e) {}
}
