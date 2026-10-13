// ---------- ⚡ BLITZED PRO + 👋 onboarding ----------
// Pro is a gold track on the Season Pass, unlocked once with paper money. Every level you've already reached pays
// its Pro prize on the spot, and every level after pays both tracks. Pro also turns the app's accents gold.
const PRO_COST = 500;
const proOn = (s = mbLoad()) => !!s.pro;
function proReward(l) {
  if (l % 5 === 0) return {cash: 30 * l, tok: "boost50", ins: true, big: true};
  return l % 2 ? {cash: 25 + 5 * l} : {tok: l % 4 === 0 ? "ins" : "boost25"};
}
function proBackpay(lvl) { const r = {cash: 0, n: 0}; for (let l = 1; l <= lvl; l++) { r.cash += proReward(l).cash || 0; r.n++; } return r; }
function proUnlock(after) {
  const s = mbLoad(), W = mbWallet(s), L = mbLevel(mbXP(s));
  if (s.pro) return;
  if (W.available < PRO_COST) { mbToast(`<div class="tbig">Not enough balance</div><div class="tsub">Pro costs ${mbShort(PRO_COST)}. Deposit to top up.</div>`); return; }
  s.bonus = (s.bonus || 0) - PRO_COST; if (typeof mbTx === "function") mbTx(s, "pro", -PRO_COST, "Season unlock"); s.pro = {ts: new Date().toISOString(), lvl: L.lvl};
  let cash = 0; for (let l = 1; l <= L.lvl; l++) { const r = proReward(l); passGrant(s, r, `Pro track · level ${l}`); cash += r.cash || 0; }
  mbSave(s);
  try { funBigWin(cash, "⚡ BLITZED PRO", `Gold track unlocked · ${L.lvl} level${L.lvl > 1 ? "s" : ""} of Pro prizes paid`); } catch (e) { mbToast(`<div class="tbig">⚡ Blitzed Pro</div><div class="tsub">+${mbShort(cash)} back</div>`, "win"); }
  document.body.classList.add("pro");
  if (after) after();
}
function proCardHtml(s = mbLoad()) {
  const L = mbLevel(mbXP(s));
  if (s.pro) return `<section class="pro-card on"><div class="pro-mark">⚡</div><div class="pro-t"><b>Blitzed Pro</b><i>Gold track active · both prizes every level</i></div><button data-pass="1">View ›</button></section>`;
  const bp = proBackpay(L.lvl);
  return `<section class="pro-card"><div class="pro-mark">⚡</div><div class="pro-t"><b>Blitzed Pro</b><i>A gold prize at every level${bp.cash ? `. ${mbShort(bp.cash)} back today for your ${L.lvl} levels` : ""}. Gold look.</i></div>
    <button data-prounlock="1">Unlock · ${mbShort(PRO_COST)}</button></section>`;
}
function proWire(root, re) {
  (root || document).querySelectorAll("[data-prounlock]").forEach(b => b.onclick = e => { e.stopPropagation(); mbHaptic(); proUnlock(re); });
}

// ---- 👋 first run: three cards, swipe or tap through, once ----
const ONB = [
  ["<img class='onb-bolt' src='bolt.png' alt=''>", "Welcome to Blitzed", "A $1,000 paper bankroll, real sportsbook lines, and a model that prices every game. No real money, ever."],
  [`<div class="onb-chips"><span>+1.5<b>-119</b></span><span class="v">O 6.5<b>+107</b></span><span class="on">ML<b>+206</b></span></div>`, "Tap a price, build a slip", "Lime outlines are where the model sees value. Hold the big button to place it. Or play Pick'em: More or Less on a player's line."],
  [`<div class="onb-vs"><b>You</b><em>VS</em><b>🤖</b></div>`, "Beat the model", "Every day the model bets your stake on its own picks. Level up the Season Pass, spin daily, and see who's up."],
];
function shOnboard() {
  const s = mbLoad();
  if (s.onboarded || navigator.webdriver || document.getElementById("onb")) return;
  const o = document.createElement("div"); o.id = "onb";
  o.innerHTML = `<div class="onb-track">${ONB.map(([art, t, d]) => `<section class="onb-s"><div class="onb-art">${art}</div><h2>${t}</h2><p>${d}</p></section>`).join("")}</div>
    <div class="onb-foot"><div class="onb-dots">${ONB.map((_, i) => `<i class="${i ? "" : "on"}"></i>`).join("")}</div><button class="onb-go">Next</button><button class="onb-skip">Skip</button></div>`;
  document.body.appendChild(o); requestAnimationFrame(() => o.classList.add("in"));
  const tr = o.querySelector(".onb-track"), go = o.querySelector(".onb-go"), dots = [...o.querySelectorAll(".onb-dots i")];
  const idx = () => Math.round(tr.scrollLeft / tr.clientWidth);
  const done = () => { const s2 = mbLoad(); s2.onboarded = 1; mbSave(s2); o.classList.remove("in"); setTimeout(() => o.remove(), 400); };
  tr.addEventListener("scroll", () => { const i = idx(); dots.forEach((d, j) => d.classList.toggle("on", j === i)); go.textContent = i === ONB.length - 1 ? "Let's go" : "Next"; }, {passive: true});
  go.onclick = () => { mbHaptic(); const i = idx(); if (i >= ONB.length - 1) done(); else tr.scrollTo({left: (i + 1) * tr.clientWidth, behavior: "smooth"}); };
  o.querySelector(".onb-skip").onclick = done;
}
