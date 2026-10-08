// ===== 💓 stakes & sweat: make paper money feel like it matters =====
// Bankroll runs (a bust ends the run; a new run once a day), bankroll-at-risk on the slip, press-and-hold to place,
// the Sweat Room (live chance-to-cash chart, heartbeat, cash-out ticker, one-leg-away alerts) and swing alerts.

// ---- runs: protect the bankroll ----
function stkRun(s = mbLoad()) {
  if (!s.run) s.run = {n: (s.busts || 0) + 1, start: s.bets.length ? s.bets[0].ts : new Date().toISOString(), peak: mbWallet(s).bankroll};
  return s.run;
}
function stkTrack(s = mbLoad()) {   // keeps the run's peak current; returns {run, W, off}
  const W = mbWallet(s), run = stkRun(s);
  let dirty = !s.runSaved;
  if (W.bankroll > (run.peak || 0) + 0.004) { run.peak = Math.round(W.bankroll * 100) / 100; dirty = true; }
  if (W.bankroll > (s.bestPeak || 0) + 0.004) { s.bestPeak = Math.round(W.bankroll * 100) / 100; dirty = true; }
  if (dirty) { s.runSaved = 1; mbSave(s); }
  return {run, W, off: run.peak > 0 ? Math.max(0, 1 - W.bankroll / run.peak) : 0};
}
function stkRunLine() {
  const {run, W, off} = stkTrack(), days = Math.max(1, Math.ceil((Date.now() - new Date(run.start).getTime()) / 864e5));
  return `<div class="stk-run"><span>Run #${run.n} · day ${days}</span><span>Peak ${mbShort(run.peak)}</span>${off >= 0.01 ? `<span class="dn">${Math.round(100 * off)}% off peak</span>` : `<span class="up">At peak</span>`}</div>`;
}
const stkBroke = s => mbWallet(s).available < 5 && !s.bets.some(b => b.status === "open");
function stkNewRun(render) {
  const s = mbLoad(); if (!stkBroke(s) || s.rebuy === mbDay(0)) return;
  const W = mbWallet(s);
  s.busts = (s.busts || 0) + 1; s.rebuy = mbDay(0);
  s.bonus = (s.bonus || 0) + (1000 - W.available);
  s.run = {n: s.busts + 1, start: new Date().toISOString(), peak: 1000};
  (s.runs = s.runs || []).push({n: s.busts, peak: (s.run && s.run.peak) || 0, end: new Date().toISOString()});
  mbSave(s); document.querySelectorAll(".stk-bust").forEach(x => x.remove());
  mbHaptic("success"); try { funBlip(); } catch (e) {}
  mbToast(`<div class="tbig">Run #${s.run.n} starts now</div><div class="tamt">$1,000.00</div><div class="tsub">Make this one last.</div>`, "win");
  render && render();
}
function stkBustCheck(render) {   // the moment you go broke: the run ends, loudly
  const s = mbLoad(); if (!stkBroke(s)) return;
  const run = stkRun(s); if (s.bustShown === run.n) return;
  s.bustShown = run.n; mbSave(s);
  const days = Math.max(1, Math.ceil((Date.now() - new Date(run.start).getTime()) / 864e5));
  const bets = s.bets.filter(b => new Date(b.ts) >= new Date(run.start)).length, ok = s.rebuy !== mbDay(0);
  const d = document.createElement("div"); d.className = "stk-bust";
  d.innerHTML = `<div class="stk-bc"><div class="stk-bt">BUSTED</div><div class="stk-bs">Run #${run.n} is over</div>
    <div class="stk-bg"><div><b>${mbShort(run.peak)}</b><span>Peak</span></div><div><b>${days}</b><span>Day${days > 1 ? "s" : ""}</span></div><div><b>${bets}</b><span>Bets</span></div></div>
    <p>${ok ? "You get one fresh $1,000 run per day. Use it like it's real." : "You've already started a run today. Come back tomorrow for run #" + (run.n + 1) + "."}</p>
    ${ok ? `<button class="stk-go" data-newrun="1">Start run #${run.n + 1}</button>` : ""}<button class="stk-x">Close</button></div>`;
  document.body.appendChild(d); requestAnimationFrame(() => d.classList.add("in")); mbHaptic("error");
  d.querySelector(".stk-x").onclick = () => { d.classList.remove("in"); setTimeout(() => d.remove(), 250); };
  const go = d.querySelector("[data-newrun]"); if (go) go.onclick = () => stkNewRun(render);
}

// ---- the slip: what you're actually risking ----
function stkRiskHtml(tot) {
  const W = mbWallet(); if (!(tot > 0) || W.bankroll <= 0) return "";
  const p = tot / W.bankroll, lvl = p >= 0.25 ? "hi" : p >= 0.1 ? "md" : "lo";
  const say = p >= 0.25 ? "That's a big swing. One bad beat and this run is hurting." : p >= 0.1 ? "A serious bet. Pros rarely go above 5%." : "Disciplined. This is how runs last.";
  return `<div class="stk-risk ${lvl}"><div class="stk-rh"><span>Risking <b>${(100 * p).toFixed(p < 0.1 ? 1 : 0)}%</b> of your bankroll</span><i>${mbShort(W.bankroll - tot)} left if it loses</i></div>
    <div class="stk-rb"><i style="width:${Math.min(100, 100 * p)}%"></i></div><em>${say}</em></div>`;
}
// press and hold to place (a quick tap just explains); window.MB_TAP_PLACE skips the hold for tests
function stkHold(btn, fire) {
  if (!btn || btn.disabled) return;
  if (window.MB_TAP_PLACE) { btn.onclick = fire; return; }
  const ms = 650; let t = null, t0 = 0, raf = 0;
  const lab = btn.querySelector("span"), orig = lab ? lab.textContent : "";
  const stop = () => { clearTimeout(t); cancelAnimationFrame(raf); btn.classList.remove("holding"); btn.style.setProperty("--hold", 0); };
  const tick = () => { btn.style.setProperty("--hold", Math.min(1, (performance.now() - t0) / ms)); raf = requestAnimationFrame(tick); };
  btn.onpointerdown = e => { e.preventDefault(); t0 = performance.now(); btn.classList.add("holding"); mbHaptic(); tick(); t = setTimeout(() => { stop(); fire(); }, ms); };
  btn.onpointerup = btn.onpointerleave = btn.onpointercancel = () => { const short = btn.classList.contains("holding") && performance.now() - t0 < ms; stop();
    if (short && lab) { lab.textContent = "Hold to place"; setTimeout(() => { lab.textContent = orig; }, 1100); } };
  btn.onclick = e => e.preventDefault();
  btn.oncontextmenu = e => e.preventDefault();
}

// ---- chance-to-cash history (for the live chart and swing alerts) ----
const STK_KEY = "mm_sweat_v1";
function stkHist() { try { return JSON.parse(localStorage.getItem(STK_KEY) || "{}"); } catch (e) { return {}; } }
function stkSample() {
  const s = mbLoad(), H = stkHist(), now = Date.now(), alerts = [];
  for (const b of s.bets.filter(x => x.status === "open")) {
    const P = mbWinProb(b); if (P == null) continue;
    const h = H[b.id] = H[b.id] || [], last = h[h.length - 1];
    if (!last || Math.abs(last[1] - P) >= 0.005) {
      h.push([now, Math.round(P * 1000) / 1000]); if (h.length > 160) h.splice(0, h.length - 160);
      if (last && mbIsLive(b) && Math.abs(P - last[1]) >= 0.15) alerts.push({b, from: last[1], to: P});
    }
  }
  for (const id of Object.keys(H)) if (!s.bets.some(b => b.id === id && b.status === "open")) delete H[id];
  try { localStorage.setItem(STK_KEY, JSON.stringify(H)); } catch (e) {}
  return alerts;
}
function stkOneAway(b) {   // a parlay with every leg cashed but one, and that one still alive
  if (b.kind !== "parlay" || b.status !== "open") return false;
  const open = b.legs.filter(l => l.res !== true && l.res !== "push");
  if (open.length !== 1) return false;
  const w = mbSweat(open[0]); return !w || !/dead/.test(w.st);
}
const stkPayout = b => b.stake + b.stake * (mbDec(b.odds) - 1) * (1 + (b.boost || 0));
function stkAlerts(alerts) {
  for (const {b, from, to} of alerts) {
    const up = to > from;
    mbToast(`<div class="tbig">${up ? "📈 Swinging your way" : "📉 Momentum swing"}</div><div class="tamt">${Math.round(100 * from)}% → ${Math.round(100 * to)}%</div><div class="tsub">${esc(b.label)}</div>`, up ? "win" : "");
    mbHaptic(up ? "success" : "error");
  }
  const s = mbLoad(); let dirty = false; s.oneAway = s.oneAway || {};
  for (const b of s.bets.filter(stkOneAway)) {
    if (s.oneAway[b.id]) continue; s.oneAway[b.id] = 1; dirty = true;
    mbToast(`<div class="tbig">😰 One leg away</div><div class="tamt">${mbMoney(stkPayout(b))}</div><div class="tsub">${esc(b.label)} · everything else has hit</div>`, "goal");
    mbHaptic("success"); try { funHorn(0.6); } catch (e) {}
  }
  if (dirty) mbSave(s);
}

// ---- the Sweat Room ----
function stkSpark(h, w = 300, ht = 64) {
  if (!h || h.length < 2) return `<div class="sr-nochart">The chart fills in as the game moves</div>`;
  const ys = h.map(p => p[1]), t0 = h[0][0], t1 = h[h.length - 1][0] || t0 + 1;
  const pts = h.map(([t, y]) => [w * (t - t0) / Math.max(1, t1 - t0), ht - 4 - (ht - 8) * y]);
  const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" "), up = ys[ys.length - 1] >= ys[0];
  return `<svg class="sr-spark" viewBox="0 0 ${w} ${ht}" preserveAspectRatio="none"><line x1="0" x2="${w}" y1="${ht / 2}" y2="${ht / 2}" class="sr-mid"/>
    <path d="${d} L ${w} ${ht} L 0 ${ht} Z" class="sr-fill ${up ? "up" : "dn"}"/><path d="${d}" class="sr-line ${up ? "up" : "dn"}" vector-effect="non-scaling-stroke"/></svg>`;
}
function stkRoomHtml() {
  const s = mbLoad(), H = stkHist(), open = s.bets.filter(b => b.status === "open"), live = open.filter(mbIsLive);
  const list = live.length ? live : open;
  if (!list.length) return `<div class="sr-empty"><b>Nothing to sweat</b><span>Place a bet and come back at puck drop.</span></div>`;
  const riding = list.reduce((a, b) => a + b.stake, 0), toWin = list.reduce((a, b) => a + stkPayout(b) - b.stake, 0);
  return `<div class="sr-sum"><div><span>Riding</span><b>${mbMoney(riding)}</b></div><div><span>To win</span><b class="w">${mbMoney(toWin)}</b></div><div><span>${live.length ? "Live" : "Open"}</span><b>${list.length}</b></div></div>
    ${list.map(b => { const P = mbWinProb(b), co = mbCashOffer(b), tension = P == null ? 0 : 1 - Math.abs(2 * P - 1), one = stkOneAway(b);
      const beat = (1.5 - 0.9 * Math.max(tension, one ? 0.9 : 0)).toFixed(2);
      return `<div class="sr-card ${P != null && P >= 0.5 ? "up" : "dn"} ${one ? "one" : ""}" style="--beat:${beat}s">
        ${one ? `<div class="sr-one">ONE LEG AWAY · ${mbMoney(stkPayout(b))}</div>` : ""}
        <div class="sr-top"><div class="sr-t"><span>${esc(b.sport)} · ${b.kind === "parlay" ? (b.sgp ? "SGP" : b.legs.length + "-leg parlay") : "Single"}</span><b>${esc(b.label)}</b><i>${mbMoney(b.stake)} to win ${mbMoney(stkPayout(b) - b.stake)}</i></div>
          <div class="sr-p">${P == null ? `<b>–</b>` : `<div class="sr-heart"></div><b>${Math.round(100 * P)}<small>%</small></b>`}<span>chance to cash</span></div></div>
        ${stkSpark(H[b.id])}
        <div class="sr-legs">${b.legs.map(l => { const w = mbSweat(l) || {}; const st = l.res === true ? "hit" : l.res === false ? "dead" : (w.st || "pre").split(" ")[0];
          return `<div class="sr-leg s-${st}"><span class="sr-dot"></span><div><b>${esc(l.label)}</b><i>${esc(w.text || "")}${w.score ? ` · ${esc(w.score)} · ${esc(w.clock || "")}` : ""}</i>${w.pct != null && st !== "hit" ? `<div class="sr-bar"><i style="width:${Math.round(100 * w.pct)}%"></i></div>` : ""}</div></div>`; }).join("")}</div>
        ${co ? `<button class="sr-co cashout ${co.dir}" data-co="${b.id}"><span>Cash out</span><b>${mbMoney(co.value)}</b>${co.dir ? `<i>${co.dir === "up" ? "▲" : "▼"}</i>` : ""}</button>` : ""}</div>`; }).join("")}`;
}
let STK_ROOM = null;
function stkOpenRoom(render) {
  document.querySelectorAll(".sweatroom").forEach(x => x.remove());
  const d = document.createElement("div"); d.className = "sweatroom"; STK_ROOM = d;
  d.innerHTML = `<div class="sr-h"><div><span class="livedot"></span><b>Sweat room</b></div><button class="sr-x" aria-label="Close">✕</button></div><div class="sr-body"></div>`;
  document.body.appendChild(d); document.body.classList.add("noscroll"); requestAnimationFrame(() => d.classList.add("in"));
  d.querySelector(".sr-x").onclick = () => { d.classList.remove("in"); document.body.classList.remove("noscroll"); STK_ROOM = null; setTimeout(() => d.remove(), 280); };
  stkRoomRefresh(render); mbHaptic();
}
function stkRoomRefresh(render) {
  if (!STK_ROOM || !document.body.contains(STK_ROOM)) return;
  const body = STK_ROOM.querySelector(".sr-body"), y = body.scrollTop;
  body.innerHTML = stkRoomHtml(); body.scrollTop = y;
  try { mbWireCashOut(() => { render && render(); stkRoomRefresh(render); }); } catch (e) {}
}

// ---- settled: the one that got away ----
function stkBadBeat(b) {
  if (b.kind !== "parlay" || b.status !== "lost" || b.legs.filter(l => l.res === false).length !== 1) return "";
  return `<div class="stk-beat">💔 One leg short of ${mbMoney(stkPayout(b))}</div>`;
}

// ---- hooked into every render ----
function stkAfterRender(render) {
  try { stkAlerts(stkSample()); } catch (e) {}
  try { stkBustCheck(render); } catch (e) {}
  document.querySelectorAll("[data-sweat]").forEach(b => b.onclick = e => { e.preventDefault(); e.stopPropagation(); stkOpenRoom(render); });
  stkRoomRefresh(render);
}
