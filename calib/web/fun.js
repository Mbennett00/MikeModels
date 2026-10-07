// ---------- 🎉 THE FUN LAYER: prize wheel, missions, boosts, goal horn, big wins, you vs the model ----------
// All paper money, all in this browser. Builds on bets.js (wallet, slip, grading) and the page hooks
// mbLiveLeg (live score / stat for a leg) and mbModelPicks (the model's picks for today).

// ---- 🔊 goal horn + sounds (Web Audio, no files). iPhone needs one tap before audio can play. ----
let FUN_AC = null;
function funAudio() {
  try { if (!FUN_AC) FUN_AC = new (window.AudioContext || window.webkitAudioContext)(); if (FUN_AC.state === "suspended") FUN_AC.resume(); } catch (e) { FUN_AC = null; }
  return FUN_AC;
}
document.addEventListener("pointerdown", () => funAudio(), {once: true, capture: true});
const funSoundOn = () => mbLoad().sound !== false;
function funHorn(len = 1.6) {
  if (!funSoundOn()) return; const ac = funAudio(); if (!ac) return;
  const t = ac.currentTime, out = ac.createGain(), lp = ac.createBiquadFilter();
  lp.type = "lowpass"; lp.frequency.value = 1400; out.gain.setValueAtTime(0, t);
  out.gain.linearRampToValueAtTime(0.22, t + 0.06); out.gain.setValueAtTime(0.22, t + len - 0.25); out.gain.linearRampToValueAtTime(0, t + len);
  lp.connect(out); out.connect(ac.destination);
  for (const f of [174.6, 220, 261.6]) {   // F major: the classic arena horn chord
    const o = ac.createOscillator(), g = ac.createGain(), vib = ac.createOscillator(), vg = ac.createGain();
    o.type = "sawtooth"; o.frequency.value = f; vib.frequency.value = 5.5; vg.gain.value = f * 0.006;
    vib.connect(vg); vg.connect(o.frequency); g.gain.value = 0.33; o.connect(g); g.connect(lp);
    o.start(t); vib.start(t); o.stop(t + len + 0.05); vib.stop(t + len + 0.05);
  }
}
function funBlip(up = true) {
  if (!funSoundOn()) return; const ac = funAudio(); if (!ac) return;
  const t = ac.currentTime, o = ac.createOscillator(), g = ac.createGain();
  o.type = "triangle"; o.frequency.setValueAtTime(up ? 660 : 330, t); o.frequency.exponentialRampToValueAtTime(up ? 1320 : 220, t + 0.12);
  g.gain.setValueAtTime(0.12, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.18); o.connect(g); g.connect(ac.destination); o.start(t); o.stop(t + 0.2);
}
function funTick() {   // wheel clicks
  if (!funSoundOn()) return; const ac = funAudio(); if (!ac) return;
  const t = ac.currentTime, o = ac.createOscillator(), g = ac.createGain();
  o.type = "square"; o.frequency.value = 1800; g.gain.setValueAtTime(0.04, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.03);
  o.connect(g); g.connect(ac.destination); o.start(t); o.stop(t + 0.04);
}

// ---- 🚨 goal light: full-screen red flash ----
function funGoalLight(ms = 1400) {
  const d = document.createElement("div"); d.className = "goallight"; document.body.appendChild(d);
  setTimeout(() => d.remove(), ms);
}

// ---- 💥 big win overlay: count-up, goal light, horn ----
function funBigWin(amount, title, sub) {
  document.querySelectorAll(".bigwin").forEach(x => x.remove());
  const d = document.createElement("div"); d.className = "bigwin";
  d.innerHTML = `<div class="bw-beams"></div><div class="bw-card"><div class="bw-siren">🚨</div><div class="bw-t">${esc(title)}</div>
    <div class="bw-amt">+$0.00</div><div class="bw-sub">${esc(sub || "")}</div><button class="bw-ok">LET'S GO</button></div>`;
  document.body.appendChild(d); requestAnimationFrame(() => d.classList.add("in"));
  funHorn(2.2); mbHaptic("success"); mbBurst(70, ["💵", "🚨", "🏒", "💰", "✨"]);
  const el = d.querySelector(".bw-amt"), t0 = performance.now(), dur = 1500;
  const step = now => { const k = Math.min((now - t0) / dur, 1), e = 1 - Math.pow(1 - k, 3); el.textContent = "+" + mbMoney(amount * e); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
  const close = () => { d.classList.remove("in"); setTimeout(() => d.remove(), 300); };
  d.onclick = close; setTimeout(close, 9000);
}
// which wins deserve the full show
const funIsBig = b => b.kind === "parlay" || b.odds >= 300 || mbProfit(b) >= 50 || b.boost;

// ---- 🎡 daily prize wheel (replaces the flat daily bonus; the streak multiplies the cash) ----
const WHEEL = [
  {k: "c25", lab: "$25", cash: 25, w: 22, col: "#2fe06e"},
  {k: "b25", lab: "🚀25%", tok: "boost25", w: 15, col: "#7c5cff"},
  {k: "c10", lab: "$10", cash: 10, w: 17, col: "#1f8f4e"},
  {k: "ins", lab: "🛡️", tok: "ins", w: 12, col: "#3aa0ff"},
  {k: "c50", lab: "$50", cash: 50, w: 15, col: "#2fe06e"},
  {k: "b50", lab: "🚀50%", tok: "boost50", w: 6, col: "#b04cff"},
  {k: "c100", lab: "$100", cash: 100, w: 9, col: "#ffc83d"},
  {k: "c250", lab: "$250", cash: 250, w: 4, col: "#ff5a5a"},
];
const TOKENS = {boost25: ["🚀", "+25% profit boost"], boost50: ["🚀", "+50% profit boost"], ins: ["🛡️", "Parlay insurance"]};
const funMult = streak => 1 + 0.1 * Math.min(Math.max(streak - 1, 0), 7);
function funGive(s, prize, mult = 1) {   // applies a wheel / mission / level-up prize to the state; returns its text
  if (prize.cash) { const amt = Math.round(prize.cash * mult * 100) / 100; s.bonus = (s.bonus || 0) + amt; return "+" + mbMoney(amt); }
  if (prize.tok) { s.tokens = s.tokens || {}; s.tokens[prize.tok] = (s.tokens[prize.tok] || 0) + 1; return TOKENS[prize.tok][0] + " " + TOKENS[prize.tok][1]; }
  return "";
}
function funWheelSvg() {
  const n = WHEEL.length, R = 120, seg = 360 / n;
  const pt = a => [R + R * Math.sin(a * Math.PI / 180), R - R * Math.cos(a * Math.PI / 180)];
  return `<svg viewBox="0 0 ${2 * R} ${2 * R}" class="wh-svg">${WHEEL.map((w, i) => { const [x1, y1] = pt(i * seg), [x2, y2] = pt((i + 1) * seg), mid = (i + 0.5) * seg;
    return `<path d="M${R},${R} L${x1},${y1} A${R},${R} 0 0 1 ${x2},${y2} Z" fill="${w.col}" stroke="#0b0f14" stroke-width="2"/>
      <text x="${R}" y="${R - R * 0.62}" transform="rotate(${mid} ${R} ${R})" text-anchor="middle" class="wh-lab">${w.lab}</text>`; }).join("")}
    <circle cx="${R}" cy="${R}" r="22" fill="#0b0f14" stroke="#ffc83d" stroke-width="4"/><text x="${R}" y="${R + 6}" text-anchor="middle" class="wh-hub">SPIN</text></svg>`;
}
function funOpenWheel(render) {
  const sh = document.getElementById("sheet"), D = mbDaily();
  sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>
    <div class="sh-t">🎡 Daily spin</div><div class="sh-s">🔥 ${D.streak}-day streak · cash prizes ×${funMult(D.streak).toFixed(1)}</div>
    <div class="wheel"><div class="wh-ptr">▼</div><div class="wh-rot" id="whrot">${funWheelSvg()}</div></div>
    <div class="wh-res" id="whres">${D.claimed ? "Already spun today. Come back tomorrow!" : "Tap SPIN. Cash, profit boosts or parlay insurance."}</div>
    <button class="placebet c" id="whgo" ${D.claimed ? "disabled" : ""}><span>${D.claimed ? "See you tomorrow" : "SPIN"}</span></button>`;
  document.getElementById("shx").onclick = () => { closeSheet(); render && render(); };
  document.getElementById("scrim").classList.add("open"); sh.classList.add("open");
  const go = document.getElementById("whgo"), rot = document.getElementById("whrot");
  const spin = () => {
    const s = mbLoad(), D2 = mbDaily(s); if (D2.claimed) return;
    go.disabled = true; rot.parentElement.querySelector(".wh-hub") && (rot.onclick = null);
    let r = Math.random() * WHEEL.reduce((a, w) => a + w.w, 0), i = 0;
    for (; i < WHEEL.length; i++) { r -= WHEEL[i].w; if (r <= 0) break; }
    i = Math.min(i, WHEEL.length - 1);
    const seg = 360 / WHEEL.length, land = 360 * 6 + (360 - (i + 0.5) * seg) + (Math.random() - 0.5) * seg * 0.6;
    rot.style.transition = "transform 4.2s cubic-bezier(.12,.75,.14,1)"; rot.style.transform = `rotate(${land}deg)`;
    let ticks = 0; const tk = setInterval(() => { funTick(); if (++ticks > 26) clearInterval(tk); }, 140);
    setTimeout(() => {
      const s3 = mbLoad(), D3 = mbDaily(s3);
      s3.daily = {last: mbDay(0), streak: D3.streak}; s3.claims = (s3.claims || 0) + 1;
      const txt = funGive(s3, WHEEL[i], funMult(D3.streak)); mbSave(s3);
      document.getElementById("whres").innerHTML = `<div class="wh-win">${esc(txt)}</div><div>${WHEEL[i].tok ? "Use it on your bet slip." : "Added to your balance."} 🔥 Day ${D3.streak} · tomorrow ×${funMult(D3.streak + 1).toFixed(1)}</div>`;
      go.querySelector("span").textContent = "Nice! Back to betting"; go.disabled = false; go.onclick = () => { closeSheet(); render && render(); };
      funBlip(); mbHaptic("success"); mbBurst(WHEEL[i].cash >= 100 ? 50 : 26, ["💵", "✨", "🎡"]); if (WHEEL[i].cash >= 100) funHorn(1.2);
      mbFab();
    }, 4300);
  };
  if (!D.claimed) { go.onclick = spin; rot.onclick = spin; }
}

// ---- 🎯 daily missions: three a day (easy / medium / hard), progress counted from today's bets ----
const MISSIONS = {
  easy: [
    {k: "prop", t: "Bet a player prop", n: 1, f: b => b.legs.some(l => (l.key || {}).t === "prop")},
    {k: "game", t: "Bet a game line", n: 1, f: b => b.legs.some(l => (l.key || {}).t === "game")},
    {k: "place2", t: "Place 2 bets", n: 2, f: () => true},
    {k: "tail", t: "Tail one of the model's picks", n: 1, f: b => funTailed(b)},
  ],
  medium: [
    {k: "goal", t: "Bet an anytime goalscorer", n: 1, f: b => b.legs.some(l => (l.key || {}).mk === "goals")},
    {k: "sog", t: "Bet 2 shots-on-goal props", n: 2, f: b => b.legs.some(l => (l.key || {}).mk === "sog")},
    {k: "plus", t: "Bet a price of +150 or longer", n: 1, f: b => b.odds >= 150},
    {k: "games3", t: "Bet on 3 different games", n: 3, games: true},
  ],
  hard: [
    {k: "parlay3", t: "Build a 3+ leg parlay", n: 1, f: b => b.kind === "parlay" && b.legs.length >= 3},
    {k: "cash", t: "Cash a bet today", n: 1, won: true},
    {k: "long", t: "Bet a +300 longshot", n: 1, f: b => b.odds >= 300},
    {k: "place5", t: "Place 5 bets", n: 5, f: () => true},
  ],
};
const MREWARD = {easy: {cash: 15, xp: 20}, medium: {cash: 30, xp: 40}, hard: {cash: 50, xp: 75}};
function funHash(str) { let h = 2166136261; for (const c of str) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
function funMissions(s = mbLoad()) {
  const day = mbDay(0), h = funHash(day), today = b => new Date(b.ts).toDateString() === new Date().toDateString();
  const placed = s.bets.filter(today), done = (s.mdone || {})[day] || [];
  return ["easy", "medium", "hard"].map((lvl, j) => {
    const pool = MISSIONS[lvl], m = pool[(h >>> (j * 4)) % pool.length];
    let prog;
    if (m.games) prog = new Set(placed.flatMap(b => b.legs.map(l => l.gid))).size;
    else if (m.won) prog = s.bets.filter(b => b.status === "won" && b.result_ts && new Date(b.result_ts).toDateString() === new Date().toDateString()).length;
    else prog = placed.filter(m.f).length;
    return Object.assign({lvl, prog: Math.min(prog, m.n), claimed: done.includes(m.k), r: MREWARD[lvl]}, m);
  });
}
function funMissionCheck() {   // pays out finished missions (and the all-three bonus) once
  const s = mbLoad(), M = funMissions(s), day = mbDay(0), fresh = M.filter(m => m.prog >= m.n && !m.claimed);
  if (!fresh.length) return;
  s.mdone = {[day]: [...((s.mdone || {})[day] || []), ...fresh.map(m => m.k)]};
  let txt = fresh.map(m => { s.xpb = (s.xpb || 0) + m.r.xp; return `${m.t} · ${funGive(s, {cash: m.r.cash})}`; });
  const all = s.mdone[day].length >= 3 && !(s.mall === day);
  if (all) { s.mall = day; txt.push("All 3 done · " + funGive(s, {tok: "boost25"})); }
  mbSave(s); funBlip(); mbHaptic("success");
  mbToast(`<div class="tbig">🎯 Mission${fresh.length > 1 ? "s" : ""} complete</div><div class="tsub">${txt.map(esc).join("<br>")}</div>`, "win");
  if (all) mbBurst(40, ["🎯", "🚀", "✨"]);
}
function funMissionsHtml(s) {
  const M = funMissions(s), n = M.filter(m => m.claimed).length;
  const mid = new Date(); mid.setHours(24, 0, 0, 0); const hrs = Math.max(1, Math.round((mid - Date.now()) / 36e5));
  return `<div class="card missions"><div class="lk-h" style="font-size:16px">🎯 Daily missions <span class="pl-tag">${n}/3</span><span class="ms-time">new in ${hrs}h</span></div>
    ${M.map(m => `<div class="ms ${m.claimed ? "done" : ""} ${m.lvl}"><span class="ms-ic">${m.claimed ? "✅" : {easy: "🟢", medium: "🟡", hard: "🔴"}[m.lvl]}</span>
      <div class="ms-b"><b>${esc(m.t)}</b><div class="ms-bar"><span style="width:${Math.round(100 * m.prog / m.n)}%"></span></div></div>
      <span class="ms-r">${m.claimed ? "Done" : `+$${m.r.cash}`}<i>${m.prog}/${m.n}</i></span></div>`).join("")}
    <div class="ms-all ${n >= 3 ? "on" : ""}">${n >= 3 ? "🚀 All three done · +25% boost earned" : "Finish all three for a 🚀 +25% profit boost"}</div></div>`;
}

// ---- 🚀 boosts + 🛡️ insurance on the slip ----
let SLIP_BOOST = null, SLIP_INS = false;   // token key or null; insurance flag (parlays only)
const funBoostOf = k => k === "boost50" ? 0.5 : k === "boost25" ? 0.25 : 0;
function funSlipTokensHtml(s, v, parlay) {
  const T = s.tokens || {}, one = parlay || v.length === 1;
  if (!(T.boost25 || T.boost50 || T.ins)) return "";
  if (SLIP_BOOST && (!T[SLIP_BOOST] || !one)) SLIP_BOOST = null;
  if (SLIP_INS && (!T.ins || !parlay || v.length < 3)) SLIP_INS = false;
  const chip = (k, on, dis, lab) => `<button class="tok ${on ? "on" : ""} ${dis ? "dis" : ""}" data-tok="${k}">${lab}<em>×${T[k]}</em></button>`;
  return `<div class="toks">${T.boost25 ? chip("boost25", SLIP_BOOST === "boost25", !one, "🚀 +25%") : ""}${T.boost50 ? chip("boost50", SLIP_BOOST === "boost50", !one, "🚀 +50%") : ""}${T.ins ? chip("ins", SLIP_INS, !(parlay && v.length >= 3), "🛡️ Insure") : ""}
    <span class="tokhint">${!one && (T.boost25 || T.boost50) ? "Boosts work on one bet: a single pick or a parlay" : T.ins && !(parlay && v.length >= 3) ? "Insurance: parlays of 3+ legs" : SLIP_INS ? "Lose by one leg? Stake back" : SLIP_BOOST ? "Boosted profit if it cashes" : "Tap to use a reward"}</span></div>`;
}
function funWireTokens(sh, re) {
  sh.querySelectorAll("[data-tok]").forEach(b => b.onclick = () => { if (b.classList.contains("dis")) return; mbHaptic(); funBlip();
    const k = b.dataset.tok; if (k === "ins") SLIP_INS = !SLIP_INS; else SLIP_BOOST = SLIP_BOOST === k ? null : k; re(); });
}
// take the tokens chosen on the slip (before the bet is saved): {boost, ins}
function funTakeTokens(parlay) {
  const s = mbLoad(), out = {}; s.tokens = s.tokens || {};
  if (SLIP_BOOST && s.tokens[SLIP_BOOST] > 0) { out.boost = funBoostOf(SLIP_BOOST); s.tokens[SLIP_BOOST]--; }
  if (SLIP_INS && parlay && s.tokens.ins > 0) { out.ins = true; s.tokens.ins--; }
  mbSave(s); SLIP_BOOST = null; SLIP_INS = false;
  return out;
}

// ---- 🤖 you vs the model: the model bets $10 on its top picks each day; tail them in one tap ----
function funModelDay(s) {
  s.model = s.model || {bets: [], days: {}};
  const day = mbDay(0);
  if (s.model.days[day] || typeof mbModelPicks !== "function") return false;
  let picks = []; try { picks = mbModelPicks() || []; } catch (e) { picks = []; }
  picks = picks.filter(l => !mbStarted(l) && isFinite(l.odds)).slice(0, 3);
  if (!picks.length) return false;
  s.model.days[day] = picks.length;
  for (const l of picks) s.model.bets.push({id: "M" + funHash(day + JSON.stringify(l.key)).toString(36).toUpperCase(), ts: new Date().toISOString(), day, sport: "NHL", kind: "single",
    label: l.label, odds: l.odds, stake: 10, status: "open", legs: [Object.assign({}, l)]});
  s.model.bets = s.model.bets.slice(-300);
  return true;
}
function funSettleModel(gradeLeg) {
  const s = mbLoad(); let ch = funModelDay(s);
  for (const b of (s.model || {}).bets || []) {
    if (b.status !== "open") continue;
    let r; try { r = gradeLeg(b.legs[0]); } catch (e) { r = undefined; }
    if (r !== undefined) { b.status = r === "push" ? "push" : r ? "won" : "lost"; b.legs[0].res = r; b.result_ts = new Date().toISOString(); ch = true; }
  }
  if (ch) mbSave(s);
}
function funTailed(b) {
  const s = mbLoad(), mk = new Set(((s.model || {}).bets || []).filter(x => x.day === mbDay(0)).map(x => x.legs[0].gid + JSON.stringify(x.legs[0].key)));
  return b.legs.some(l => mk.has(l.gid + JSON.stringify(l.key)));
}
function funVsHtml(s) {
  const mb = ((s.model || {}).bets || []), today = mb.filter(b => b.day === mbDay(0));
  const ms = mbStats(mb), me = mbStats(s.bets);
  if (!mb.length && !today.length) return "";
  const lead = me.pl > ms.pl ? "you" : me.pl < ms.pl ? "model" : "tie";
  return `<div class="card vsm"><div class="lk-h" style="font-size:16px">🤖 You vs the Model</div>
    <div class="vs-row"><div class="vs-side ${lead === "you" ? "lead" : ""}"><span>You</span><b class="${me.pl >= 0 ? "pos" : "neg"}">${(me.pl >= 0 ? "+" : "") + mbMoney(me.pl)}</b><i>${(100 * me.roi).toFixed(1)}% ROI · ${me.n} bets</i></div>
      <div class="vs-mid">${lead === "you" ? "👑" : lead === "model" ? "🤖" : "🤝"}<em>VS</em></div>
      <div class="vs-side r ${lead === "model" ? "lead" : ""}"><span>Model</span><b class="${ms.pl >= 0 ? "pos" : "neg"}">${(ms.pl >= 0 ? "+" : "") + mbMoney(ms.pl)}</b><i>${(100 * ms.roi).toFixed(1)}% ROI · ${ms.n} bets</i></div></div>
    <div class="vs-cap">${lead === "you" ? "You're beating the model. Keep it up!" : lead === "model" ? "The model's ahead. Tail it, or fade it." : "Dead even."} The model bets $10 on its top 3 picks each day.</div>
    ${today.length ? `<div class="vs-picks">${today.map(b => { const l = b.legs[0], st = b.status;
      return `<div class="vs-pick ${st}">${mbPic(l)}<div class="slipt"><b>${esc(b.label)}</b><i>${esc(l.sub || "")}</i></div><span class="slipo">${mbSign(b.odds)}</span>
        ${st === "open" && !mbStarted(l) ? `<button class="vs-tail" data-tail="${esc(b.id)}">Tail</button>` : `<span class="vs-st">${{open: "Live", won: "✅", lost: "❌", push: "➖"}[st]}</span>`}</div>`; }).join("")}
      ${today.some(b => b.status === "open" && !mbStarted(b.legs[0])) ? `<button class="vs-all" data-tail="all">🤖 Tail all of today's picks</button>` : ""}</div>` : ""}</div>`;
}
function funWireVs(render) {
  document.querySelectorAll("[data-tail]").forEach(btn => btn.onclick = () => {
    const s = mbLoad(), today = ((s.model || {}).bets || []).filter(b => b.day === mbDay(0) && b.status === "open" && !mbStarted(b.legs[0]));
    const pick = btn.dataset.tail === "all" ? today : today.filter(b => b.id === btn.dataset.tail);
    pick.forEach(b => slipAdd(Object.assign({}, b.legs[0], {sport: "NHL", label: b.label, odds: b.odds})));
    mbHaptic(); funBlip(); mbOpenSlip();
  });
}

// ---- ⬆️ level-ups pay out, 💸 refill when broke, 🔥 on-fire wallet ----
function funTierCheck() { passCheck(); }   // levels now come from the season pass (home.js)
function funRebuyHtml(s, W) {
  if (W.available >= 5 || s.bets.some(b => b.status === "open")) return "";
  const ok = s.rebuy !== mbDay(0);
  return `<div class="daily rebuy"><div class="gift">💸</div><div class="dt"><b>${ok ? "Running on empty?" : "Refill used today"}</b><i>${ok ? "Grab a $500 paper refill (once a day)" : "Come back tomorrow for another refill"}</i></div>${ok ? `<button class="claim" id="mbrebuy">Refill</button>` : ""}</div>`;
}
function funWireRebuy(render) {
  const b = document.getElementById("mbrebuy"); if (!b) return;
  b.onclick = () => { const s = mbLoad(); if (s.rebuy === mbDay(0)) return; s.rebuy = mbDay(0); s.bonus = (s.bonus || 0) + 500; mbSave(s);
    mbHaptic("success"); funBlip(); mbBurst(24, ["💵", "✨"]); mbToast(`<div class="tbig">💸 Refilled</div><div class="tamt">+$500.00</div>`, "win"); render(); };
}
function funTokensHtml(s) {
  const T = s.tokens || {}, ks = Object.keys(TOKENS).filter(k => T[k] > 0);
  return ks.length ? `<div class="wtoks">${ks.map(k => `<span>${TOKENS[k][0]} ${TOKENS[k][1].replace(" profit boost", "")} <b>×${T[k]}</b></span>`).join("")}</div>` : "";
}

// ---- 🚨 live goal alerts for games you have money on ----
const FUN_SCORE = {}, FUN_STAT = {};
function funGoalWatch() {
  const s = mbLoad(), open = s.bets.filter(b => b.status === "open");
  if (!open.length || typeof mbLiveLeg !== "function") return;
  const games = {};
  for (const b of open) for (const l of b.legs) {
    let L; try { L = mbLiveLeg(l); } catch (e) { L = null; }
    if (!L || !L.state || L.state === "pre") continue;
    (games[l.gid] = games[l.gid] || {L, bets: new Set()}).bets.add(b.label);
    const k = l.key || {};
    if (k.t === "prop" && L.cur != null) {   // your player's stat ticked up
      const id = b.id + "|" + l.gid + "|" + k.pid + "|" + k.mk, was = FUN_STAT[id];
      FUN_STAT[id] = L.cur;
      if (was != null && L.cur > was) {
        const need = Math.floor(k.l) + 1, hit = L.cur >= need && (k.dir || "over") === "over", nm = (k.name || "").split(" ").slice(-1)[0];
        const what = {goals: "SCORES", sog: "fires a shot", points: "picks up a point", assists: "gets an assist"}[k.mk] || "+1";
        mbToast(`<div class="tbig">${k.mk === "goals" ? "🚨" : "🏒"} ${esc(nm)} ${what}!</div><div class="tsub">${L.cur} of ${need} ${esc(L.unit || "")}${hit ? " · ✅ that leg cashes" : ` · ${need - L.cur} to go`}</div>`, hit ? "win" : "");
        if (hit) { funBlip(); mbHaptic("success"); }
      }
    }
  }
  for (const [gid, {L, bets}] of Object.entries(games)) {
    const tot = (L.home || 0) + (L.away || 0), was = FUN_SCORE[gid];
    FUN_SCORE[gid] = tot;
    if (was != null && tot > was) {
      funGoalLight(); funHorn(1.4); mbHaptic("success");
      mbToast(`<div class="tbig">🚨 GOAL!</div><div class="tamt">${esc(L.awayAbbr)} ${L.away}–${L.home} ${esc(L.homeAbbr)}</div><div class="tsub">You're sweating: ${esc([...bets].slice(0, 2).join(" · "))}</div>`, "goal");
    }
  }
}

// ---- hooked into every render (from mbAfterRender) ----
function funAfterRender(render) {
  try { if (typeof mbGrade === "function") funSettleModel(mbGrade); } catch (e) {}
  try { funMissionCheck(); } catch (e) {}
  try { funTierCheck(); } catch (e) {}
  try { funGoalWatch(); } catch (e) {}
  funWireVs(render); funWireRebuy(render);
  document.querySelectorAll("[data-pass]").forEach(b => b.onclick = e => { e.stopPropagation(); mbHaptic(); mbOpenPass(); });
  document.querySelectorAll("[data-spin]").forEach(b => b.onclick = e => { e.stopPropagation(); mbHaptic(); funOpenWheel(render); });
  const snd = document.getElementById("mbsound");
  if (snd) snd.onchange = () => { const s = mbLoad(); s.sound = snd.checked; mbSave(s); if (snd.checked) funHorn(0.8); };
}
