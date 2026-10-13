// ---------- ⚡ BLITZ, the character: a mascot that lives in the app and texts you ----------
// A floating buddy (the bolt, with eyes) opens a chat. Blitz briefs you on the slate, sends picks as tappable bet
// cards, builds parlays, sweats your live bets, roasts or hypes your form. Lightning strikes when you cash.

const BZ_FACE = (cls = "") => `<span class="bzf ${cls}"><img src="bolt.png" alt=""><i class="e l"><b></b></i><i class="e r"><b></b></i></span>`;
const pick1 = a => a[Math.floor(Math.random() * a.length)];
let CH = null;   // {log: [{who, html}], cards: []}

function chSlate() { try { return (typeof D !== "undefined" && D && D.games || []).filter(g => !mbStarted({start: g.start_utc})); } catch (e) { return []; } }
function chValue() { return bzPool().filter(l => bzEdge(l) > 0.005); }
function chCard(l) {
  const i = CH.cards.push(l) - 1, e = bzEdge(l);
  return `<div class="chc">${mbPic(l)}<div class="chc-t"><b>${esc(l.label)}</b><i>${esc(l.sub || "")}${l.p != null ? ` · model ${Math.round(100 * l.p)}%` : ""}${e > -1 ? ` · <em class="${e >= 0 ? "pos" : "neg"}">${e >= 0 ? "+" : "−"}${Math.abs(100 * e).toFixed(1)}%</em>` : ""}</i></div>
    <button class="chc-add" data-chadd="${i}">${mbSign(l.odds)}</button><button class="chc-xr" data-chxr="${i}" aria-label="X-Ray">🔬</button></div>`;
}
function chParlayCard(legs) {
  const i = CH.cards.push({parlay: legs}) - 1, dec = legs.reduce((a, l) => a * mbDec(l.odds), 1), p = legs.reduce((a, l) => a * (l.p || 0), 1);
  return `<div class="chp">${legs.map(l => `<div class="chp-l">${mbPic(l)}<b>${esc(l.label)}</b><i>${mbSign(l.odds)}</i></div>`).join("")}
    <div class="chp-f"><span>${legs.length}-leg parlay · model ${Math.round(100 * p)}%</span><button data-chadd="${i}">Add all · ${mbSign(mbAm(dec))}</button></div></div>`;
}

// ---- what Blitz says ----
const CH_REPLIES = {
  lock() {
    const v = chValue().filter(l => (l.p || 0) >= 0.5).sort((a, b) => (b.p * bzEdge(b)) - (a.p * bzEdge(a)));
    if (!v.length) return [pick1(["Nothing I'd call a lock right now. The book's being careful tonight.", "No locks. Anyone selling you one is lying. Check back after the next odds update."])];
    const l = v[0];
    return [pick1([`My strongest spot tonight 🔒`, `If I had to bet one thing, it's this.`, `Don't overthink it.`]), chCard(l),
      `I've got it at <b>${Math.round(100 * l.p)}%</b>. The price says ${Math.round(100 * bzImplied(l.odds))}%. That gap is the whole game.`];
  },
  spicy() {
    const v = chValue().filter(l => l.odds >= 150).sort((a, b) => bzEdge(b) - bzEdge(a));
    if (!v.length) return ["No plus-money spots with real value right now. I don't do spicy for the sake of spicy 🌶️"];
    const l = v[0];
    return [pick1(["Feeling dangerous? 🌶️", "Small stake, big upside.", "This one pays."]), chCard(l), `Plus money <b>and</b> the model likes it. ${pick1(["Rare combo.", "Don't tell the book.", "Sprinkle, don't pour."])}`];
  },
  parlay() {
    const v = chValue(), legs = [], seen = new Set();
    for (const l of v) { if (seen.has(l.gid)) continue; seen.add(l.gid); legs.push(l); if (legs.length === 3) break; }
    if (legs.length < 2) return ["Not enough separate games with value to build a parlay I'd stand behind."];
    return [pick1(["Cooked you up something 🎰", "Three games, three edges.", "Here's one I'd actually ride."]), chParlayCard(legs), "Every leg has an edge on its own, all in different games. Parlays are long shots either way. Size it small."];
  },
  form() {
    const s = mbLoad(), me = mbStats(s.bets), mb = mbStats(((s.model || {}).bets || []).filter(b => b.status !== "open")), W = mbWallet(s);
    if (!me.n) return ["You haven't settled a bet yet. The scoreboard's at zero. Let's change that."];
    const ahead = me.pl >= mb.pl;
    return [`You're <b class="${me.pl >= 0 ? "pos" : "neg"}">${me.pl >= 0 ? "+" : "−"}${mbMoney(Math.abs(me.pl)).replace("−", "")}</b> on ${me.n} bets (${(me.roi >= 0 ? "+" : "") + (100 * me.roi).toFixed(1)}% ROI). Balance ${mbShort(W.available)}.`,
      ahead ? pick1(["And you're beating me. I don't love it. 😤", "You're ahead of me. Enjoy it while it lasts.", "Fine. You're better than me right now. For now."])
            : pick1([`I'm up ${mbMoney(mb.pl - me.pl).replace("−", "")} on you. Just saying. 😏`, "I'm ahead. Want me to carry you?", "The machine leads. Tail me or fade me."]),
      me.streak >= 3 ? `${me.streak} straight wins 🔥 Don't get greedy.` : ""].filter(Boolean);
  },
  live() {
    const s = mbLoad(), out = [];
    for (const b of s.bets.filter(b => b.status === "open")) for (const l of b.legs) {
      let L; try { L = typeof mbLiveLeg === "function" ? mbLiveLeg(l) : null; } catch (e) { L = null; }
      if (!L || L.state === "pre") continue; const k = l.key || {};
      if (k.t === "prop" && L.cur != null) { const need = Math.floor(k.l) + 1 - L.cur;
        out.push(need <= 0 ? `✅ <b>${esc(k.name || l.label)}</b> already cashed ${esc(l.label)}.` : need === 1 ? `👀 <b>${esc(k.name || l.label)}</b> has ${L.cur} ${L.unit}. ONE more.` : `${esc(k.name || l.label)}: ${L.cur} ${L.unit}, needs ${need} more.`); }
      else out.push(`${esc(L.awayAbbr)} ${L.away}–${L.home} ${esc(L.homeAbbr)}${L.detail ? ` · ${esc(L.detail)}` : ""} · you've got ${esc(l.label)}`);
      if (out.length >= 4) break; }
    return out.length ? ["Here's your sweat 🥵", ...out] : ["Nothing of yours is live right now. I'll ping you when the puck drops."];
  },
};
function chOpening() {
  const s = mbLoad(), h = new Date().getHours(), nm = typeof acctName === "function" ? acctName(s) : "", g = chSlate(), v = chValue();
  const hi = h < 12 ? pick1(["Morning", "Rise and grind", "Coffee first, then edges"]) : h < 18 ? pick1(["Afternoon", "Yo", "What's good"]) : pick1(["Evening", "Lights are on", "Game time"]);
  const live = s.bets.filter(b => b.status === "open" && mbIsLive(b)).length;
  const msgs = [`${hi}, ${esc(nm)} ⚡`];
  msgs.push(g.length ? `${g.length} game${g.length > 1 ? "s" : ""} still to play. I've found <b>${v.length}</b> price${v.length === 1 ? "" : "s"} the book got wrong.` : "Slate's done for today. I'm studying tomorrow's lines.");
  if (live) msgs.push(`You've got ${live} bet${live > 1 ? "s" : ""} live right now. Tap <b>My sweat</b> and I'll walk you through it.`);
  else msgs.push(pick1(["What are we doing?", "Want my best spot?", "Lock, spicy or parlay. Your call."]));
  return msgs;
}

// ---- the chat window ----
function chOpen() {
  if (document.getElementById("bzchat")) return;
  CH = CH || {log: [], cards: []};
  const o = document.createElement("div"); o.id = "bzchat";
  o.innerHTML = `<div class="ch-top"><button class="ch-x" aria-label="Close">‹</button>${BZ_FACE("sm")}<div class="ch-id"><b>Blitz</b><i><span class="ch-dot"></span>online · your model</i></div></div>
    <div class="ch-log"></div>
    <div class="ch-qr"><button data-q="lock">🔒 Give me a lock</button><button data-q="spicy">🌶️ Something spicy</button><button data-q="parlay">🎰 Build a parlay</button><button data-q="live">🥵 My sweat</button><button data-q="form">📈 How am I doing?</button><button data-q="blitz">⚡ Blitz Mode</button></div>`;
  document.body.appendChild(o); document.body.classList.add("ch-on"); requestAnimationFrame(() => o.classList.add("in"));
  o.querySelector(".ch-x").onclick = chClose;
  o.querySelectorAll("[data-q]").forEach(b => b.onclick = () => chAsk(b.dataset.q, b.textContent));
  o.addEventListener("click", e => {
    const a = e.target.closest("[data-chadd]"), x = e.target.closest("[data-chxr]");
    if (a) { const c = CH.cards[Number(a.dataset.chadd)]; if (!c) return; (c.parlay || [c]).forEach(l => slipAdd(Object.assign({}, l))); if (c.parlay) SLIP_MODE = "parlay";
      a.classList.add("on"); a.textContent = "✓ Added"; mbHaptic("success"); try { funBlip(); } catch (e2) {}
      chSay([pick1(["Locked in 🤝", "Good taste.", "On your slip. Let's eat.", "Bold. I like it."])], 300); }
    if (x) { const c = CH.cards[Number(x.dataset.chxr)]; if (c) bzXray(c); }
  });
  const log = o.querySelector(".ch-log");
  if (CH.log.length) { log.innerHTML = CH.log.map(m => chBubble(m.who, m.html)).join(""); log.scrollTop = log.scrollHeight; }
  else chSay(chOpening(), 350);
  document.getElementById("bzbuddy") && document.getElementById("bzbuddy").classList.remove("ping");
}
function chClose() { const o = document.getElementById("bzchat"); if (!o) return; o.classList.remove("in"); document.body.classList.remove("ch-on"); setTimeout(() => o.remove(), 300); MB_RENDER && MB_RENDER(); }
function chBubble(who, html) { return who === "me" ? `<div class="chm me"><div class="chb">${html}</div></div>` : html.startsWith("<div") ? `<div class="chm bot card">${html}</div>` : `<div class="chm bot"><div class="chb">${html}</div></div>`; }
function chAsk(q, label) {
  if (q === "blitz") { chClose(); setTimeout(bzOpen, 250); return; }
  chPush("me", esc(label)); chSay(CH_REPLIES[q](), 650);
}
function chPush(who, html) {
  CH.log.push({who, html}); if (CH.log.length > 60) CH.log = CH.log.slice(-60);
  const log = document.querySelector("#bzchat .ch-log"); if (!log) return;
  log.insertAdjacentHTML("beforeend", chBubble(who, html)); const n = log.lastElementChild; n.classList.add("new"); log.scrollTo({top: log.scrollHeight, behavior: "smooth"});
}
function chSay(msgs, delay) {
  const log = document.querySelector("#bzchat .ch-log"); let t = 0;
  msgs.forEach((m, i) => { t += i ? Math.min(1300, 420 + m.replace(/<[^>]+>/g, "").length * 12) : delay;
    setTimeout(() => { const ty = log && log.querySelector(".chm.typing"); if (ty) ty.remove(); chPush("bot", m);
      if (i < msgs.length - 1 && log) { log.insertAdjacentHTML("beforeend", `<div class="chm bot typing"><div class="chb"><i></i><i></i><i></i></div></div>`); log.scrollTop = log.scrollHeight; } }, t); });
  if (log) { log.insertAdjacentHTML("beforeend", `<div class="chm bot typing"><div class="chb"><i></i><i></i><i></i></div></div>`); log.scrollTop = log.scrollHeight; }
}

// ---- the buddy: always around, reacts to what happens ----
function chBuddy() {
  let b = document.getElementById("bzbuddy");
  if (!b) { b = document.createElement("button"); b.id = "bzbuddy"; b.setAttribute("aria-label", "Chat with Blitz"); b.innerHTML = BZ_FACE() + `<span class="bb-say"></span>`;
    document.body.appendChild(b); b.onclick = () => { mbHaptic(); chOpen(); };
    setTimeout(() => { if (typeof TAB === "undefined" || TAB !== "home") chQuip(chOpening()[1].replace(/<[^>]+>/g, "")); }, 2600); }
  return b;
}
function chQuip(txt, mood) {   // a speech bubble pops from the buddy
  const b = chBuddy(), say = b.querySelector(".bb-say"); if (!say || document.getElementById("bzchat")) return;
  say.textContent = txt; b.classList.add("talk"); if (mood) b.classList.add(mood); b.classList.add("ping");
  clearTimeout(chQuip.t); chQuip.t = setTimeout(() => b.classList.remove("talk", "hype", "sad"), 4200);
}
// ⚡ lightning: the screen gets struck when you cash
function bzStrike() {
  const o = document.createElement("div"); o.className = "strike";
  const pts = [[55, -5]]; let x = 55; for (let y = 8; y <= 100; y += 9) { x += (Math.random() - 0.5) * 22; pts.push([Math.max(10, Math.min(90, x)), y]); }
  const d = pts.map((p, i) => (i ? "L" : "M") + p[0] + " " + p[1]).join(" ");
  o.innerHTML = `<svg viewBox="0 0 100 100" preserveAspectRatio="none"><path d="${d}" class="bolt-glow"/><path d="${d}" class="bolt-core"/></svg>`;
  document.body.appendChild(o); document.body.classList.add("shake"); setTimeout(() => document.body.classList.remove("shake"), 500);
  try { const A = new (window.AudioContext || window.webkitAudioContext)(), n = A.sampleRate * 1.2, buf = A.createBuffer(1, n, A.sampleRate), d0 = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d0[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, 2.5); const s = A.createBufferSource(), f = A.createBiquadFilter(), g = A.createGain();
    f.type = "lowpass"; f.frequency.value = 900; g.gain.value = mbLoad().sound === false ? 0 : 0.5; s.buffer = buf; s.connect(f).connect(g).connect(A.destination); s.start(); } catch (e) {}
  setTimeout(() => o.remove(), 1200);
  chQuip(pick1(["CASHED ⚡⚡⚡", "THAT'S WHAT I'M TALKING ABOUT", "Ring the bell 🔔", "Easy money."]), "hype");
}
function chHomeCard() {
  const m = chOpening();
  return `<section class="ch-home"><div class="chh-face">${BZ_FACE("big")}</div><div class="chh-b"><div class="chh-n">Blitz <i>· your model</i></div><div class="chh-say">${m[1]}</div>
    <div class="chh-q"><button data-chq="lock">🔒 Lock</button><button data-chq="spicy">🌶️ Spicy</button><button data-chq="parlay">🎰 Parlay</button></div></div></section>`;
}
function chAfterRender() {
  chBuddy();
  try { const hx = document.querySelector("#view .hx2"); if (hx && !hx.querySelector(".ch-home")) { const w = hx.querySelector(".w-card"); const d = document.createElement("div"); d.innerHTML = chHomeCard(); if (w) w.before(d.firstElementChild); } } catch (e) {}
  document.querySelectorAll("[data-chq]").forEach(b => b.onclick = () => { mbHaptic(); chOpen(); setTimeout(() => chAsk(b.dataset.chq, b.textContent), CH && CH.log.length ? 150 : 1500); });
  document.querySelectorAll(".ch-home .chh-face").forEach(f => f.onclick = () => { mbHaptic(); chOpen(); });
  document.body.classList.toggle("bb-hide", !!document.getElementById("blitz") || !!document.getElementById("wrap"));
}
