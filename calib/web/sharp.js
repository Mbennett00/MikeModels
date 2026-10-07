// ===== 🧠 Sharp Score, coach, share-a-win card, install as an app =====
// Paper money, real skill: the score grades HOW you bet (taking prices the model likes, beating
// the odds, return), so practice here carries over. Needs bets.js (mbLoad, mbProfit, mbDec, ...).

// ---- Sharp Score ----
const SH_MIN = 5;
const shImp = o => 1 / mbDec(o);
function shModelP(b) {   // the model's chance when you placed it (null if any leg lacks one)
  if (!b.legs || !b.legs.length) return null;
  let P = 1; for (const l of b.legs) { if (l.p == null || !isFinite(l.p)) return null; P *= l.p; } return P;
}
const shDone = bets => bets.filter(b => b.status === "won" || b.status === "lost" || b.status === "cashout");
const SH_GRADES = [[90, "A+"], [82, "A"], [75, "A−"], [68, "B+"], [60, "B"], [52, "B−"], [45, "C+"], [38, "C"], [0, "D"]];
const SH_TIERS = [[85, "Wiseguy", "The book fears you."], [70, "Sharp", "You bet like a pro."], [55, "Grinder", "Solid habits, keep stacking edges."],
                  [40, "Recreational", "Fun first. Hunt more value tags."], [0, "Square", "Plenty of upside. Follow the edges."]];
function mbSharp(bets) {
  const done = shDone(bets), n = done.length;
  if (n < SH_MIN) return {ready: false, n, need: SH_MIN};
  const eds = done.map(b => { const P = shModelP(b); return P == null ? null : P - shImp(b.odds); }).filter(x => x != null);
  const edge = eds.length ? eds.reduce((a, x) => a + x, 0) / eds.length : 0;
  const wl = done.filter(b => b.status !== "cashout"), W = wl.filter(b => b.status === "won").length;
  const E = wl.reduce((a, b) => a + shImp(b.odds), 0), V = wl.reduce((a, b) => { const q = shImp(b.odds); return a + q * (1 - q); }, 0);
  const z = V ? (W - E) / Math.sqrt(V) : 0;
  const pl = done.reduce((a, b) => a + mbProfit(b), 0), staked = done.reduce((a, b) => a + b.stake, 0), roi = staked ? pl / staked : 0;
  const cl = (x, lo, hi) => Math.max(0, Math.min(100, 100 * (x - lo) / (hi - lo)));
  const parts = {edge: cl(edge, -0.06, 0.06), luck: cl(z, -2, 2), roi: cl(roi, -0.3, 0.3)};
  const raw = 0.45 * parts.edge + 0.25 * parts.luck + 0.30 * parts.roi, k = Math.min(1, n / 30);   // small samples pull toward 50
  const score = Math.max(1, Math.min(99, Math.round(50 + (raw - 50) * (0.5 + 0.5 * k))));
  return {ready: true, n, score, edge, z, W, E, roi, pl, parts, grade: SH_GRADES.find(g => score >= g[0])[1], tier: SH_TIERS.find(t => score >= t[0]),
          value: eds.length ? eds.filter(x => x > 0).length / eds.length : 0};
}
function shRing(score, size = 64, sw = 6) {
  const R = size / 2 - sw, C = 2 * Math.PI * R, p = score == null ? 0 : score / 100;
  return `<svg class="sx-svg" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}"><defs><linearGradient id="sxg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2ef08a"/><stop offset="1" stop-color="#f2c96d"/></linearGradient></defs>
    <circle cx="${size / 2}" cy="${size / 2}" r="${R}" fill="none" stroke="rgba(255,255,255,.07)" stroke-width="${sw}"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${R}" fill="none" stroke="url(#sxg)" stroke-width="${sw}" stroke-linecap="round" stroke-dasharray="${C * p} ${C}" transform="rotate(-90 ${size / 2} ${size / 2})"/></svg>`;
}

// ---- coach: what your own history says ----
const shMoney = v => (v >= 0 ? "+" : "−") + mbMoney(Math.abs(v)).replace("−", "");
function shGroup(x) { const w = x.filter(b => b.status === "won").length, l = x.filter(b => b.status === "lost").length,
  pl = x.reduce((a, b) => a + mbProfit(b), 0), st = x.reduce((a, b) => a + b.stake, 0); return {n: x.length, w, l, pl, roi: st ? pl / st : 0}; }
function mbCoach(bets) {
  const done = shDone(bets), out = [];
  if (done.length < 3) return out;
  const withP = done.filter(b => shModelP(b) != null);
  const pos = shGroup(withP.filter(b => shModelP(b) > shImp(b.odds))), neg = shGroup(withP.filter(b => shModelP(b) <= shImp(b.odds)));
  if (pos.n >= 2 && neg.n >= 2) out.push(pos.pl >= neg.pl
    ? {tone: "good", h: "Value is paying you", b: `Bets the model rated as value: ${pos.w}–${pos.l}, ${shMoney(pos.pl)}. The rest: ${neg.w}–${neg.l}, ${shMoney(neg.pl)}. Keep hunting the green edges.`}
    : {tone: "tip", h: "Trust the edges", b: `Value bets: ${pos.w}–${pos.l}, ${shMoney(pos.pl)}. Bets without an edge: ${neg.w}–${neg.l}, ${shMoney(neg.pl)}. Over a season, the edges win. Small samples swing.`});
  const cats = [["Game lines", b => b.kind !== "parlay" && (b.legs[0].key || {}).t === "game"], ["Player props", b => b.kind !== "parlay" && (b.legs[0].key || {}).t === "prop"], ["Parlays", b => b.kind === "parlay"]]
    .map(([name, f]) => ({name, ...shGroup(done.filter(f))})).filter(c => c.n >= 3).sort((a, b) => b.roi - a.roi);
  if (cats.length >= 2 && cats[0].pl > 0) out.push({tone: "good", h: `${cats[0].name} are your money-maker`, b: `${cats[0].w}–${cats[0].l}, ${(100 * cats[0].roi).toFixed(0)}% ROI. That's where your read is sharpest.`});
  const worst = cats[cats.length - 1];
  if (worst && worst.roi < -0.1 && worst !== cats[0]) out.push({tone: "warn", h: `${worst.name} are leaking`, b: `${worst.w}–${worst.l}, ${shMoney(worst.pl)}. Try smaller stakes there until it turns.`});
  const bands = [["Favorites (−150 or shorter)", b => b.odds <= -150], ["Coin flips (−149 to +149)", b => b.odds > -150 && b.odds < 150], ["Longshots (+150 or longer)", b => b.odds >= 150]]
    .map(([name, f]) => ({name, ...shGroup(done.filter(f))})).filter(c => c.n >= 3);
  const bb = bands.slice().sort((a, b) => a.roi - b.roi)[0];
  if (bb && bb.roi < -0.15) out.push({tone: "warn", h: `Watch your ${bb.name.split(" (")[0].toLowerCase()}`, b: `${bb.name}: ${bb.w}–${bb.l}, ${shMoney(bb.pl)}. ${/Fav/.test(bb.name) ? "Heavy chalk needs a very high hit rate to pay." : /Long/.test(bb.name) ? "Longshots are fun but need real edges to be worth it." : "These live and die on price, so shop for value."}`});
  const par = done.filter(b => b.kind === "parlay").length;
  if (par / done.length > 0.5 && shGroup(done.filter(b => b.kind === "parlay")).pl < 0) out.push({tone: "tip", h: "Parlay heavy", b: `${Math.round(100 * par / done.length)}% of your bets are parlays. Each extra leg multiplies the house edge. Mix in more singles on your best reads.`});
  return out.slice(0, 4);
}
// a lesson a day: the stuff that makes you a better bettor anywhere
const SH_TIPS = [
  ["Implied probability", "−110 means you need to win 52.4% just to break even. Turn every price into a % before you bet."],
  ["The vig", "Both sides at −110 add up to 104.8%. That extra 4.8% is the book's cut. Value is beating it."],
  ["Bet the number, not the team", "A great team at a bad price is a bad bet. A bad team at a great price can be a good one."],
  ["Unit sizing", "Pros risk 1–2% of bankroll per bet. Flat stakes keep one bad night from wrecking a good month."],
  ["Parlay math", "A 3-leg parlay of −110s pays +596 but true odds are about +600 only if every leg is a coin flip. Edges compound, but so does vig."],
  ["Closing line value", "If the line moves your way after you bet, you beat the market. Do that often and the wins follow."],
  ["Results vs process", "A good bet can lose and a bad bet can win. Judge yourself on the price you got, not one result."],
  ["Correlation", "Same-game legs that move together (a QB's yards and his WR's yards) are why books price SGPs carefully."],
  ["Chasing", "The next bet doesn't know you lost the last one. Stick to your stake size after a loss."],
  ["Overs and pace", "Totals hinge on pace and goalies. A backup in net or a back-to-back can move a total a full goal."],
];
function shTip() { const d = Math.floor(Date.now() / 864e5); return SH_TIPS[d % SH_TIPS.length]; }

// ---- Home card + full report ----
function mbSharpCard() {
  const s = mbLoad(), S = mbSharp(s.bets);
  if (!S.ready) return `<button class="sx-card lock" data-sharp="1"><div class="sx-ring">${shRing(100 * S.n / S.need)}<span><b>${S.n}/${S.need}</b></span></div>
    <div class="sx-t"><span>Sharp Score</span><b>Unlocks after ${S.need} settled bets</b><em>Grades how you bet, not just if you won</em></div><span class="sx-chev">›</span></button>`;
  const c = mbCoach(s.bets)[0];
  return `<button class="sx-card" data-sharp="1"><div class="sx-ring">${shRing(S.score)}<span><b>${S.score}</b><i>${S.grade}</i></span></div>
    <div class="sx-t"><span>Sharp Score</span><b>${S.tier[1]}</b><em>${c ? esc(c.h) : esc(S.tier[2])}</em></div><span class="sx-chev">›</span></button>`;
}
function mbOpenSharp() {
  const s = mbLoad(), S = mbSharp(s.bets), co = mbCoach(s.bets), tip = shTip(), sh = document.getElementById("sheet");
  const bar = (lab, v, txt) => `<div class="sx-bar"><div class="sx-bh"><span>${lab}</span><b>${txt}</b></div><div class="sx-bt"><i style="width:${Math.round(v)}%"></i></div></div>`;
  const top = S.ready ? `<div class="sx-hero"><div class="sx-ring big">${shRing(S.score, 120, 9)}<span><b>${S.score}</b><i>${S.grade}</i></span></div>
      <div class="sx-ht"><span>Sharp Score</span><b>${S.tier[1]}</b><em>${esc(S.tier[2])}</em><i>${S.n} settled bets</i></div></div>
      ${bar("Value taken", S.parts.edge, `${S.edge >= 0 ? "+" : "−"}${Math.abs(100 * S.edge).toFixed(1)}% avg edge`)}
      ${bar("Beat the odds", S.parts.luck, `${S.W - S.E >= 0 ? "+" : "−"}${Math.abs(S.W - S.E).toFixed(1)} wins vs expected`)}
      ${bar("Return", S.parts.roi, `${S.roi >= 0 ? "+" : ""}${(100 * S.roi).toFixed(1)}% ROI`)}`
    : `<div class="sx-hero"><div class="sx-ring big">${shRing(100 * S.n / S.need, 120, 9)}<span><b>${S.n}/${S.need}</b></span></div>
      <div class="sx-ht"><span>Sharp Score</span><b>Calibrating</b><em>Settle ${S.need - S.n} more bet${S.need - S.n === 1 ? "" : "s"} to get graded.</em></div></div>`;
  sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>${top}
    <div class="sx-how">Your score weighs the <b>edge</b> you took against the model's fair price (45%), wins <b>vs what the odds expected</b> (25%) and <b>ROI</b> (30%). Sharp bettors win on price, so value matters most.</div>
    ${co.length ? `<div class="sx-h">Your coach</div>${co.map(c => `<div class="sx-co ${c.tone}"><b>${esc(c.h)}</b><span>${esc(c.b)}</span></div>`).join("")}` : ""}
    <div class="sx-h">Today's lesson</div><div class="sx-tip"><b>${esc(tip[0])}</b><span>${esc(tip[1])}</span></div>`;
  document.getElementById("shx").onclick = () => closeSheet();
  document.getElementById("scrim").classList.add("open"); sh.classList.add("open"); sh.scrollTop = 0;
}

// ---- bankroll sparkline for the Home hero ----
function mbSpark(bets, w = 320, h = 54) {
  const done = bets.filter(b => b.status !== "open").sort((a, b) => (a.result_ts || a.ts).localeCompare(b.result_ts || b.ts));
  if (done.length < 2) return "";
  let run = 0; const ys = [0, ...done.map(b => (run += mbProfit(b)))];
  const lo = Math.min(...ys), hi = Math.max(...ys), sp = hi - lo || 1;
  const pts = ys.map((y, i) => [w * i / (ys.length - 1), h - 4 - (h - 8) * (y - lo) / sp]);
  const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" "), up = run >= 0;
  return `<svg class="hx-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><defs><linearGradient id="hxs" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${up ? "#2ef08a" : "#ff5d5d"}" stop-opacity=".35"/><stop offset="1" stop-color="${up ? "#2ef08a" : "#ff5d5d"}" stop-opacity="0"/></linearGradient></defs>
    <path d="${d} L ${w} ${h} L 0 ${h} Z" fill="url(#hxs)"/><path d="${d}" fill="none" stroke="${up ? "#2ef08a" : "#ff5d5d"}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
    <circle cx="${pts[pts.length - 1][0]}" cy="${pts[pts.length - 1][1]}" r="3.5" fill="${up ? "#2ef08a" : "#ff5d5d"}"/></svg>`;
}

// ---- 📸 share a win: a poster-quality image of the ticket ----
function mbShareBet(id) {
  const s = mbLoad(), b = s.bets.find(x => x.id === id); if (!b) return;
  const cv = document.createElement("canvas"); cv.width = 1080; cv.height = 1350; const x = cv.getContext("2d");
  const F = (w, px, fam) => `${w} ${px}px ${fam === "b" ? "'Plus Jakarta Sans'" : "Sora"}, system-ui, sans-serif`;
  const g = x.createLinearGradient(0, 0, 1080, 1350); g.addColorStop(0, "#07120c"); g.addColorStop(.55, "#06080b"); g.addColorStop(1, "#120f06"); x.fillStyle = g; x.fillRect(0, 0, 1080, 1350);
  const glow = (cx, cy, r, c) => { const rg = x.createRadialGradient(cx, cy, 0, cx, cy, r); rg.addColorStop(0, c); rg.addColorStop(1, "rgba(0,0,0,0)"); x.fillStyle = rg; x.fillRect(0, 0, 1080, 1350); };
  glow(180, 160, 700, "rgba(46,240,138,.28)"); glow(980, 1250, 650, "rgba(242,201,109,.20)");
  x.strokeStyle = "rgba(255,255,255,.04)"; x.lineWidth = 2; for (let i = -1350; i < 1080; i += 60) { x.beginPath(); x.moveTo(i, 0); x.lineTo(i + 1350, 1350); x.stroke(); }
  x.fillStyle = "rgba(255,255,255,.55)"; x.font = F(700, 30, "b"); x.letterSpacing = "8px"; x.fillText("MIKEMODELS", 90, 130);
  x.fillStyle = "rgba(255,255,255,.35)"; x.font = F(600, 26, "b"); x.letterSpacing = "4px"; x.textAlign = "right"; x.fillText(`${b.sport} · ${b.kind === "parlay" ? (b.sgp ? "SAME GAME PARLAY" : `${b.legs.length}-LEG PARLAY`) : "SINGLE"}`, 990, 130); x.textAlign = "left";
  const won = b.status === "cashout" ? (b.cash || 0) - b.stake : mbProfit(b);
  x.letterSpacing = "14px"; x.font = F(700, 64, "h"); x.fillStyle = "#2ef08a"; x.shadowColor = "rgba(46,240,138,.6)"; x.shadowBlur = 40; x.fillText(b.status === "cashout" ? "CASHED OUT" : "CASHED", 90, 300); x.shadowBlur = 0;
  x.letterSpacing = "-4px"; x.font = F(600, 190, "h"); x.fillStyle = "#ffffff"; x.fillText("+" + mbMoney(won), 82, 490);
  x.letterSpacing = "0px"; x.font = F(500, 36, "b"); x.fillStyle = "rgba(255,255,255,.6)"; x.fillText(`${mbMoney(b.stake)} at ${mbSign(b.odds)}${b.boost ? `  ·  boosted +${100 * b.boost}%` : ""}`, 90, 560);
  let y = 680; x.fillStyle = "rgba(255,255,255,.06)"; x.beginPath(); x.roundRect(70, y - 70, 940, Math.min(b.legs.length, 6) * 96 + 60, 36); x.fill();
  b.legs.slice(0, 6).forEach(l => { x.fillStyle = "#2ef08a"; x.beginPath(); x.arc(130, y - 12, 20, 0, 7); x.fill(); x.strokeStyle = "#06120a"; x.lineWidth = 6; x.beginPath(); x.moveTo(120, y - 12); x.lineTo(128, y - 3); x.lineTo(142, y - 22); x.stroke();
    x.fillStyle = "#fff"; x.font = F(700, 40, "b"); let t = l.label; while (x.measureText(t).width > 640 && t.length > 4) t = t.slice(0, -2); if (t !== l.label) t += "…"; x.fillText(t, 180, y);
    if (l.odds) { x.textAlign = "right"; x.fillStyle = "rgba(255,255,255,.55)"; x.font = F(600, 38, "h"); x.fillText(mbSign(l.odds), 970, y); x.textAlign = "left"; } y += 96; });
  if (b.legs.length > 6) { x.fillStyle = "rgba(255,255,255,.45)"; x.font = F(600, 30, "b"); x.fillText(`+${b.legs.length - 6} more`, 180, y - 20); }
  const sy = Math.max(y + 40, 1000), cols = [["ODDS", mbSign(b.odds)], ["RISK", mbMoney(b.stake)], ["PAYOUT", mbMoney(b.stake + won)]];
  cols.forEach(([k, v], i) => { const cx = 90 + i * 310; x.fillStyle = "rgba(255,255,255,.4)"; x.font = F(700, 24, "b"); x.letterSpacing = "4px"; x.fillText(k, cx, sy);
    x.letterSpacing = "-1px"; x.fillStyle = i === 2 ? "#2ef08a" : "#fff"; x.font = F(600, 58, "h"); x.fillText(v, cx, sy + 66); x.letterSpacing = "0px"; });
  const S = mbSharp(s.bets), L = typeof mbLevel === "function" ? mbLevel(mbXP(s)) : null;
  x.fillStyle = "rgba(255,255,255,.08)"; x.fillRect(90, 1150, 900, 2);
  x.fillStyle = "rgba(255,255,255,.5)"; x.font = F(600, 28, "b"); x.fillText(new Date(b.result_ts || b.ts).toLocaleDateString("en-US", {month: "long", day: "numeric", year: "numeric"}), 90, 1220);
  x.textAlign = "right"; x.fillStyle = "#f2c96d"; x.font = F(700, 30, "b"); x.fillText([S.ready ? `SHARP SCORE ${S.score}` : "", L ? `LVL ${L.lvl}` : ""].filter(Boolean).join("   ·   "), 990, 1220); x.textAlign = "left";
  x.fillStyle = "rgba(255,255,255,.28)"; x.font = F(500, 24, "b"); x.fillText("Paper money. Real reads.", 90, 1270);
  cv.toBlob(blob => { if (!blob) return; const url = URL.createObjectURL(blob), file = new File([blob], `mikemodels-${b.id}.png`, {type: "image/png"});
    const canShare = navigator.canShare && navigator.canShare({files: [file]});
    const d = document.createElement("div"); d.className = "shx";
    d.innerHTML = `<div class="shx-in"><img src="${url}" alt="Your winning ticket"><div class="shx-b">${canShare ? `<button class="shx-go" data-x="share">Share</button>` : ""}<a class="shx-go ${canShare ? "alt" : ""}" href="${url}" download="mikemodels-${esc(b.id)}.png">Save image</a><button class="shx-x" data-x="close">Close</button></div></div>`;
    document.body.appendChild(d); requestAnimationFrame(() => d.classList.add("in")); mbHaptic("success");
    const close = () => { d.classList.remove("in"); setTimeout(() => { d.remove(); URL.revokeObjectURL(url); }, 250); };
    d.onclick = e => { if (e.target === d || e.target.dataset.x === "close") close(); };
    const sb = d.querySelector('[data-x="share"]'); if (sb) sb.onclick = () => navigator.share({files: [file], title: "Cashed on MikeModels"}).catch(() => {});
  }, "image/png");
}

// ---- 📲 install as an app ----
let MB_INSTALL = null;
window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); MB_INSTALL = e; });
if ("serviceWorker" in navigator && location.protocol.startsWith("http")) window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
const mbStandalone = () => (window.matchMedia && matchMedia("(display-mode: standalone)").matches) || navigator.standalone === true;
function mbInstallHtml() {
  let x = null; try { x = localStorage.getItem("mm_inst_x"); } catch (e) {}
  if (mbStandalone() || x) return "";
  return `<div class="ix"><div class="ix-ic"><img src="icon-192.png" alt="" onerror="this.remove()"></div><div class="ix-t"><b>Get the app</b><span>Full screen, no browser bars, one tap from your home screen.</span></div>
    <button class="ix-go" data-install="1">Install</button><button class="ix-x" data-installx="1" aria-label="Dismiss">✕</button></div>`;
}
function mbWireInstall(render) {
  document.querySelectorAll("[data-installx]").forEach(b => b.onclick = () => { try { localStorage.setItem("mm_inst_x", "1"); } catch (e) {} render(); });
  document.querySelectorAll("[data-install]").forEach(b => b.onclick = () => {
    mbHaptic();
    if (MB_INSTALL) { MB_INSTALL.prompt(); MB_INSTALL.userChoice.finally(() => { MB_INSTALL = null; render(); }); return; }
    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent), sh = document.getElementById("sheet");
    sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button><div class="sh-t">Add MikeModels to your home screen</div>
      <div class="ix-steps">${ios ? `<div><b>1</b><span>Tap the <em>Share</em> button in Safari's toolbar</span></div><div><b>2</b><span>Scroll and tap <em>Add to Home Screen</em></span></div><div><b>3</b><span>Tap <em>Add</em>. It opens full screen like a real app.</span></div>`
        : `<div><b>1</b><span>Open your browser menu (⋮)</span></div><div><b>2</b><span>Tap <em>Install app</em> or <em>Add to Home screen</em></span></div><div><b>3</b><span>Launch it from your home screen.</span></div>`}</div>`;
    document.getElementById("shx").onclick = () => closeSheet();
    document.getElementById("scrim").classList.add("open"); sh.classList.add("open");
  });
}
function mbWireSharp(render) {
  document.querySelectorAll("[data-sharp]").forEach(b => b.onclick = e => { e.stopPropagation(); mbHaptic(); mbOpenSharp(); });
  document.querySelectorAll("[data-share]").forEach(b => b.onclick = e => { e.stopPropagation(); mbShareBet(b.dataset.share); });
  mbWireInstall(render);
}
