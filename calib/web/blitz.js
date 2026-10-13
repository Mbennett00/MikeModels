// ---------- ⚡ BLITZ: swipe mode, pick X-Ray, holo cards, Blitz Wrapped ----------
// Page hooks used when present: mbModelPool() (NHL: the model's full menu) or mbQuickPicks() (both pages), D (the slate).

// ---- shared bits ----
const bzSport = () => (typeof MB_PAGE !== "undefined" ? MB_PAGE : "NHL");
function bzPool() {
  let legs = [];
  try { if (typeof mbModelPool === "function") legs = mbModelPool(); } catch (e) {}
  if (!legs.length) try { legs = (typeof mbQuickPicks === "function" ? mbQuickPicks() || [] : []).flatMap(q => q.legs || []); } catch (e) {}
  const seen = new Set();
  return legs.filter(l => l && isFinite(l.odds) && !mbStarted(l) && !seen.has(slipKey(l)) && seen.add(slipKey(l)))
    .map(l => Object.assign({sport: l.sport || bzSport()}, l))
    .sort((a, b) => bzEdge(b) - bzEdge(a));
}
const bzImplied = o => 1 / mbDec(o);
const bzEdge = l => (l.p != null ? l.p - bzImplied(l.odds) : -1);
function bzGame(l) { try { return (typeof D !== "undefined" && D && D.games || []).find(g => String(g.game_id) === String(l.gid)); } catch (e) { return null; } }
function bzPlayer(l) { const k = l.key || {}; try { return (typeof D !== "undefined" && D && D.players || []).find(p => String(p.id) === String(k.pid)); } catch (e) { return null; } }

// ---- 🔬 Pick X-Ray: why the model likes (or hates) a price ----
function bzGauge(p, imp) {   // a half-moon dial: model chance with the book's implied chance marked
  const R = 70, C = Math.PI * R, val = Math.max(0, Math.min(1, p)), mk = Math.max(0, Math.min(1, imp));
  const a = Math.PI * (1 - mk), mx = 90 + R * Math.cos(a), my = 86 - R * Math.sin(a);
  return `<svg class="xr-g" viewBox="0 0 180 100"><path d="M20 86 A70 70 0 0 1 160 86" class="xr-g-bg"/><path d="M20 86 A70 70 0 0 1 160 86" class="xr-g-fg" style="stroke-dasharray:${C};stroke-dashoffset:${C * (1 - val)}"/>
    <line x1="${mx}" y1="${my - 9}" x2="${mx}" y2="${my + 9}" class="xr-g-mk" transform="rotate(${90 - 180 * mk} ${mx} ${my})"/></svg>`;
}
function bzDist(l) {   // a player prop's projected distribution, the line marked
  const k = l.key || {}, pl = bzPlayer(l); if (k.t !== "prop" || !pl || !pl.lam || pl.lam[k.mk] == null) return "";
  const lam = pl.lam[k.mk], n = Math.max(4, Math.ceil(lam * 2.6 + 2));
  const pm = []; let q = Math.exp(-lam); for (let i = 0; i <= n; i++) { pm.push(q); q *= lam / (i + 1); }
  const top = Math.max(...pm), over = i => (k.dir === "under" ? i < k.l : i > k.l);
  return `<div class="xr-h">Projection · ${lam.toFixed(k.mk === "goals" ? 2 : 1)} ${({sog: "shots", goals: "goals"})[k.mk] || k.mk}</div>
    <div class="xr-dist">${pm.map((v, i) => `<div class="xr-b ${over(i) ? "hit" : ""}" style="--h:${(v / top * 100).toFixed(1)}%;--d:${i * 40}ms"><i></i><span>${i}${i === n ? "+" : ""}</span><em>${Math.round(v * 100)}%</em></div>`).join("")}</div>
    <div class="xr-cap">Lime bars cash your ${k.dir === "under" ? "under" : "over"} ${k.l}. Model chance: <b>${Math.round(100 * (l.p || 0))}%</b></div>`;
}
function bzProj(l) {   // a game line: the projected score
  const g = bzGame(l); if (!g || (l.key || {}).t === "prop") return "";
  const a = g.lam_away != null ? g.lam_away : g.pts_away, h = g.lam_home != null ? g.lam_home : g.pts_home; if (a == null || h == null) return "";
  const dp = g.lam_away != null ? 1 : 0;
  return `<div class="xr-h">Projected score</div><div class="xr-score"><div><img src="${esc((g.away || {}).logo || "")}" alt="" onerror="this.remove()"><b>${Number(a).toFixed(dp)}</b><span>${esc((g.away || {}).abbr || "")}</span></div><em>–</em>
    <div><img src="${esc((g.home || {}).logo || "")}" alt="" onerror="this.remove()"><b>${Number(h).toFixed(dp)}</b><span>${esc((g.home || {}).abbr || "")}</span></div></div>`;
}
function bzXray(l, onAdd) {
  const sh = document.getElementById("sheet"), p = l.p, imp = bzImplied(l.odds), edge = p != null ? p - imp : null, ev = p != null ? 100 * (p * mbDec(l.odds) - 1) : null;
  const fair = p != null && p > 0 && p < 1 ? mbAm(1 / p) : null, inSlip = slipLoad().some(x => slipKey(x) === slipKey(l));
  const verdict = edge == null ? ["Model price unavailable", ""] : edge >= 0.04 ? ["🔥 Strong value", "hot"] : edge >= 0.01 ? ["✅ Value", "ok"] : edge > -0.02 ? ["⚖️ Fair price", ""] : ["🚫 Overpriced", "bad"];
  sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>
    <div class="xr-top">${mbPic(l)}<div><div class="xr-k">🔬 Pick X-Ray</div><div class="xr-t">${esc(l.label)}</div><div class="xr-s">${esc(l.sub || "")}</div></div></div>
    <div class="xr-dial">${p != null ? bzGauge(p, imp) : ""}<div class="xr-dv"><b>${p != null ? Math.round(100 * p) + "%" : "–"}</b><span>model chance</span></div>
      <div class="xr-leg"><span><i class="m"></i>Model ${p != null ? Math.round(100 * p) + "%" : "–"}</span><span><i class="b"></i>Book ${Math.round(100 * imp)}%</span></div></div>
    <div class="xr-verdict ${verdict[1]}">${verdict[0]}</div>
    <div class="xr-stats"><div><span>Price</span><b>${mbSign(l.odds)}</b></div><div><span>Fair odds</span><b>${fair != null ? mbSign(fair) : "–"}</b></div>
      <div><span>Edge</span><b class="${edge >= 0 ? "pos" : "neg"}">${edge != null ? (edge >= 0 ? "+" : "−") + Math.abs(100 * edge).toFixed(1) + "%" : "–"}</b></div>
      <div><span>EV / $100</span><b class="${ev >= 0 ? "pos" : "neg"}">${ev != null ? (ev >= 0 ? "+" : "−") + "$" + Math.abs(ev).toFixed(2) : "–"}</b></div></div>
    ${bzDist(l)}${bzProj(l)}
    <button class="placebet c" id="xradd"><span>${inSlip ? "✓ On your slip" : `Add to slip · ${mbSign(l.odds)}`}</span></button>`;
  document.getElementById("shx").onclick = () => closeSheet();
  document.getElementById("xradd").onclick = () => { if (!inSlip) { slipAdd(Object.assign({}, l)); mbHaptic("success"); try { funBlip(); } catch (e) {} } closeSheet(); onAdd && onAdd(); };
  document.getElementById("scrim").classList.add("open"); sh.classList.add("open");
  requestAnimationFrame(() => sh.classList.add("xr-in"));
}

// ---- ⚡ Blitz Mode: swipe the model's board ----
let BZ = null;
function bzOpen() {
  const pool = bzPool().slice(0, 25);
  const o = document.createElement("div"); o.id = "blitz";
  BZ = {pool, i: 0, added: [], o};
  o.innerHTML = `<div class="bz-top"><button class="bz-x" aria-label="Close">✕</button><div class="bz-brand"><img src="bolt.png" alt="">BLITZ MODE</div><div class="bz-n"></div></div>
    <div class="bz-hint">Swipe right to add · left to pass</div><div class="bz-deck"></div>
    <div class="bz-acts"><button class="bz-pass" aria-label="Pass">✕</button><button class="bz-xr" aria-label="X-Ray">🔬</button><button class="bz-add" aria-label="Add">⚡</button></div>`;
  document.body.appendChild(o); document.body.classList.add("bz-on"); requestAnimationFrame(() => o.classList.add("in"));
  o.querySelector(".bz-x").onclick = bzClose;
  o.querySelector(".bz-pass").onclick = () => bzFling(-1);
  o.querySelector(".bz-add").onclick = () => bzFling(1);
  o.querySelector(".bz-xr").onclick = () => { const l = BZ.pool[BZ.i]; if (l) bzXray(l, () => { bzMark(l); bzNext(); }); };
  bzDeal();
}
function bzClose() { if (!BZ) return; const o = BZ.o; o.classList.remove("in"); document.body.classList.remove("bz-on"); setTimeout(() => o.remove(), 350); BZ = null; MB_RENDER && MB_RENDER(); }
function bzCard(l, depth) {
  const g = bzGame(l), e = bzEdge(l), col = (g && ((g.home || {}).color || (g.away || {}).color)) || "#2a2f28", pl = bzPlayer(l), k = l.key || {};
  const art = l.img ? `<img class="bz-hs" src="${esc(l.img)}" alt="" onerror="this.remove()">` : (l.logos && l.logos.length ? `<div class="bz-duo"><img src="${esc(l.logos[0])}" alt=""><em>VS</em><img src="${esc(l.logos[1])}" alt=""></div>` : `<div class="bz-art">${mbPic(l)}</div>`);
  const proj = pl && pl.lam && k.mk && pl.lam[k.mk] != null ? `<div class="bz-proj"><span>Projection</span><b>${pl.lam[k.mk].toFixed(k.mk === "goals" ? 2 : 1)}</b><span>vs line ${k.l}</span></div>` : "";
  return `<div class="bz-card" style="--tc:${esc(col)};--z:${10 - depth};--dp:${depth}"><div class="bz-glow"></div>${art}${l.logo && l.img ? `<img class="bz-tl" src="${esc(l.logo)}" alt="">` : ""}
    <div class="bz-body"><div class="bz-tag">${e >= 0.04 ? "🔥 Strong value" : e >= 0.01 ? "✅ Model likes it" : k.t === "prop" ? "🎯 Player prop" : "📊 Game line"}</div>
      <div class="bz-t">${esc(l.label)}</div><div class="bz-s">${esc(l.sub || "")}</div>
      <div class="bz-row"><div class="bz-odds">${mbSign(l.odds)}</div><div class="bz-m"><div class="bz-bar"><i style="width:${Math.round(100 * (l.p || 0))}%"></i><b style="left:${Math.round(100 * bzImplied(l.odds))}%"></b></div>
        <span>Model <b>${Math.round(100 * (l.p || 0))}%</b> · Book ${Math.round(100 * bzImplied(l.odds))}%${e > -1 ? ` · <em class="${e >= 0 ? "pos" : "neg"}">${e >= 0 ? "+" : "−"}${Math.abs(100 * e).toFixed(1)}%</em>` : ""}</span></div></div>${proj}</div>
    <div class="bz-stamp add">ADD</div><div class="bz-stamp pass">PASS</div></div>`;
}
function bzDeal() {
  const deck = BZ.o.querySelector(".bz-deck"), rest = BZ.pool.slice(BZ.i, BZ.i + 3);
  BZ.o.querySelector(".bz-n").textContent = BZ.pool.length ? `${Math.min(BZ.i + 1, BZ.pool.length)} / ${BZ.pool.length}` : "";
  if (!rest.length) return bzDone();
  deck.innerHTML = rest.map((l, d) => bzCard(l, d)).reverse().join("");
  const top = deck.lastElementChild; bzDrag(top);
}
function bzDrag(c) {
  let x0 = 0, y0 = 0, dx = 0, dy = 0, on = false;
  c.addEventListener("pointerdown", e => { on = true; x0 = e.clientX; y0 = e.clientY; c.setPointerCapture(e.pointerId); c.style.transition = "none"; });
  c.addEventListener("pointermove", e => { if (!on) return; dx = e.clientX - x0; dy = e.clientY - y0;
    c.style.transform = `translate(${dx}px, ${dy * 0.4}px) rotate(${dx / 18}deg)`; c.style.setProperty("--sa", Math.max(0, Math.min(1, dx / 110))); c.style.setProperty("--sp", Math.max(0, Math.min(1, -dx / 110))); });
  const end = () => { if (!on) return; on = false; c.style.transition = "";
    if (Math.abs(dx) > 100) bzFling(dx > 0 ? 1 : -1, c); else { c.style.transform = ""; c.style.setProperty("--sa", 0); c.style.setProperty("--sp", 0); } dx = dy = 0; };
  c.addEventListener("pointerup", end); c.addEventListener("pointercancel", end);
}
function bzMark(l) { if (!BZ.added.some(x => slipKey(x) === slipKey(l))) BZ.added.push(l); }
function bzFling(dir, c) {
  if (!BZ) return; const l = BZ.pool[BZ.i]; if (!l) return;
  c = c || BZ.o.querySelector(".bz-deck").lastElementChild; if (!c) return;
  c.style.setProperty(dir > 0 ? "--sa" : "--sp", 1);
  c.style.transition = "transform .45s cubic-bezier(.2,.7,.2,1), opacity .45s"; c.style.transform = `translate(${dir * 140}vw, -40px) rotate(${dir * 28}deg)`; c.style.opacity = 0;
  if (dir > 0) { slipAdd(Object.assign({}, l)); bzMark(l); mbHaptic("success"); try { funBlip(); } catch (e) {} } else mbHaptic();
  setTimeout(bzNext, 260);
}
function bzNext() { if (!BZ) return; BZ.i++; bzDeal(); }
function bzDone() {
  const v = slipLoad(), dec = v.reduce((a, x) => a * mbDec(x.odds), 1), n = BZ.added.length;
  BZ.o.querySelector(".bz-deck").innerHTML = `<div class="bz-end"><div class="bz-end-ic">⚡</div><b>${n ? `${n} pick${n > 1 ? "s" : ""} added` : "That's the board"}</b>
    <span>${v.length > 1 && slipParlayOk(v) ? `Your slip as a parlay pays <em>${mbSign(mbAm(dec))}</em>` : v.length ? `${v.length} on your slip` : "Nothing added this time."}</span>
    ${v.length ? `<button class="placebet c" id="bzslip"><span>Open bet slip</span></button>` : ""}<button class="bz-again" id="bzagain">Run it back</button></div>`;
  BZ.o.querySelector(".bz-acts").style.visibility = "hidden"; BZ.o.querySelector(".bz-hint").style.visibility = "hidden";
  const s = document.getElementById("bzslip"); if (s) s.onclick = () => { if (v.length > 1 && slipParlayOk(v)) SLIP_MODE = "parlay"; bzClose(); setTimeout(mbOpenSlip, 200); };
  document.getElementById("bzagain").onclick = () => { BZ.i = 0; BZ.o.querySelector(".bz-acts").style.visibility = ""; BZ.o.querySelector(".bz-hint").style.visibility = ""; bzDeal(); };
}

// ---- ✨ holo cards: tilt toward your finger, a foil sheen follows ----
function bzHolo(el) {
  if (!el || el.dataset.holo) return; el.dataset.holo = "1"; el.classList.add("holo");
  const set = (x, y) => { const r = el.getBoundingClientRect(), px = (x - r.left) / r.width, py = (y - r.top) / r.height;
    el.style.setProperty("--rx", ((0.5 - py) * 10).toFixed(2) + "deg"); el.style.setProperty("--ry", ((px - 0.5) * 12).toFixed(2) + "deg");
    el.style.setProperty("--mx", (px * 100).toFixed(1) + "%"); el.style.setProperty("--my", (py * 100).toFixed(1) + "%"); el.classList.add("tilt"); };
  el.addEventListener("pointermove", e => set(e.clientX, e.clientY), {passive: true});
  el.addEventListener("pointerdown", e => set(e.clientX, e.clientY), {passive: true});
  const off = () => { el.classList.remove("tilt"); el.style.setProperty("--rx", "0deg"); el.style.setProperty("--ry", "0deg"); };
  el.addEventListener("pointerleave", off); el.addEventListener("pointerup", off); el.addEventListener("pointercancel", off);
}

// ---- 🎬 Blitz Wrapped: your betting, as stories ----
function bzWrapData() {
  const s = mbLoad(), done = s.bets.filter(b => b.status !== "open"), wk = Date.now() - 7 * 864e5;
  const recent = done.filter(b => new Date(b.result_ts || b.ts).getTime() >= wk), set = recent.length >= 3 ? recent : done, span = recent.length >= 3 ? "this week" : "all time";
  const st = mbStats(set), staked = set.reduce((a, b) => a + b.stake, 0), w = set.filter(b => b.status === "won").length, l = set.filter(b => b.status === "lost").length;
  const best = set.filter(b => mbProfit(b) > 0).sort((a, b) => mbProfit(b) - mbProfit(a))[0];
  const teams = {}; for (const b of set) for (const leg of b.legs) for (const t of mbTeamsIn(Object.assign({sport: b.sport}, leg)).slice(0, 1)) teams[t] = (teams[t] || 0) + 1;
  const fav = Object.entries(teams).sort((a, b) => b[1] - a[1])[0];
  const kinds = {Props: set.filter(b => b.kind !== "parlay" && (b.legs[0].key || {}).t === "prop").length, "Game lines": set.filter(b => b.kind !== "parlay" && (b.legs[0].key || {}).t !== "prop").length, Parlays: set.filter(b => b.kind === "parlay").length};
  const style = Object.entries(kinds).sort((a, b) => b[1] - a[1])[0];
  const mb = mbStats(((s.model || {}).bets || []).filter(b => b.status !== "open"));
  return {n: set.length, span, staked, pl: st.pl, roi: st.roi, w, l, best, fav, style, mb, streak: st.best, name: typeof acctName === "function" ? acctName(s) : ""};
}
function bzWrapped() {
  const D0 = bzWrapData();
  if (D0.n < 1) { mbAlert("🎬 Blitz Wrapped", "Settle a few bets to unlock your recap", ""); return; }
  const money = x => (x >= 0 ? "+" : "−") + mbMoney(Math.abs(x)).replace("−", "");
  const slides = [
    `<div class="wr-k">Blitz Wrapped · ${D0.span}</div><div class="wr-big">${esc(D0.name || "Your")}${D0.name ? "'s" : ""}<br>run</div><div class="wr-s">Tap to play</div>`,
    `<div class="wr-k">You played</div><div class="wr-big" data-count="${D0.n}">0</div><div class="wr-s">bets, with <b>${mbShort(D0.staked)}</b> on the line</div>`,
    `<div class="wr-k">Record</div><div class="wr-big">${D0.w}<em>–</em>${D0.l}</div><div class="wr-s">${D0.streak >= 3 ? `Longest heater: <b>${D0.streak} straight</b> 🔥` : `${Math.round(100 * D0.w / Math.max(1, D0.w + D0.l))}% of decided bets cashed`}</div>`,
    `<div class="wr-k">Profit</div><div class="wr-big ${D0.pl >= 0 ? "pos" : "neg"}" data-money="${D0.pl.toFixed(2)}">$0</div><div class="wr-s">${(D0.roi >= 0 ? "+" : "") + (100 * D0.roi).toFixed(1)}% ROI ${D0.roi >= 0.05 ? "· that's sharp money" : D0.roi >= 0 ? "· in the green" : "· the comeback starts now"}</div>`,
    D0.best ? `<div class="wr-k">Best hit</div><div class="wr-tk">${mbPic(D0.best.legs[0] || {})}<b>${esc(D0.best.label)}</b><span>${mbSign(D0.best.odds)} · ${mbMoney(D0.best.stake)} stake</span></div><div class="wr-big pos sm">${money(mbProfit(D0.best))}</div>` : "",
    D0.fav ? `<div class="wr-k">Your team</div><img class="wr-logo" src="${esc(D0.fav[0])}" alt=""><div class="wr-s">On <b>${D0.fav[1]}</b> of your tickets. Loyal.</div>` : "",
    `<div class="wr-k">Your style</div><div class="wr-big sm">${esc(D0.style[0])}</div><div class="wr-s">${D0.style[0] === "Parlays" ? "Chasing the big one. Respect." : D0.style[0] === "Props" ? "You bet players, not teams." : "Old-school: sides and totals."}</div>`,
    `<div class="wr-k">You vs the model</div><div class="wr-vs"><div><span>You</span><b class="${D0.pl >= 0 ? "pos" : "neg"}">${money(D0.pl)}</b></div><em>${D0.pl >= D0.mb.pl ? "👑" : "🤖"}</em><div><span>Model</span><b class="${D0.mb.pl >= 0 ? "pos" : "neg"}">${money(D0.mb.pl)}</b></div></div><div class="wr-s">${D0.pl >= D0.mb.pl ? "You beat the machine." : "The model's ahead. Run it back."}</div>`,
  ].filter(Boolean);
  const o = document.createElement("div"); o.id = "wrap";
  o.innerHTML = `<div class="wr-bars">${slides.map(() => "<i><b></b></i>").join("")}</div><button class="wr-x" aria-label="Close">✕</button><div class="wr-stage"></div>`;
  document.body.appendChild(o); requestAnimationFrame(() => o.classList.add("in"));
  let i = -1, t = null;
  const bars = [...o.querySelectorAll(".wr-bars i")];
  const show = n => { if (n >= slides.length) return close(); if (n < 0) n = 0; i = n; clearTimeout(t);
    bars.forEach((b, j) => { b.className = j < i ? "done" : j === i ? "on" : ""; });
    const st = o.querySelector(".wr-stage"); st.innerHTML = `<div class="wr-slide s${i % 4}">${slides[i]}</div>`;
    st.querySelectorAll("[data-count]").forEach(el => bzCount(el, Number(el.dataset.count), v => Math.round(v)));
    st.querySelectorAll("[data-money]").forEach(el => bzCount(el, Number(el.dataset.money), v => (v >= 0 ? "+" : "−") + mbMoney(Math.abs(v)).replace("−", "")));
    if (st.querySelector(".pos") && i > 2) try { fxConfetti(40); } catch (e) {}
    t = setTimeout(() => show(i + 1), 4200); };
  const close = () => { clearTimeout(t); o.classList.remove("in"); setTimeout(() => o.remove(), 350); };
  o.querySelector(".wr-x").onclick = e => { e.stopPropagation(); close(); };
  o.onclick = e => { mbHaptic(); show(e.clientX < innerWidth * 0.3 ? i - 1 : i + 1); };
  show(0);
}
function bzCount(el, to, fmt) { const t0 = performance.now(), dur = 1100; const step = now => { const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3); el.textContent = fmt(to * e); if (k < 1) requestAnimationFrame(step); }; requestAnimationFrame(step); }

// ---- entry points (every render) ----
function bzHomeCards() {
  const n = bzPool().length, s = mbLoad(), done = s.bets.filter(b => b.status !== "open").length;
  return `<div class="bz-entry">${n ? `<button class="bz-go" data-blitz="1"><span class="bz-go-ic"><img src="bolt.png" alt=""></span><span class="bz-go-t"><b>Blitz Mode</b><i>Swipe through ${n} model picks</i></span><span class="bz-go-a">›</span></button>` : ""}
    ${done ? `<button class="bz-wr" data-wrapped="1"><span>🎬</span><b>Blitz Wrapped</b><i>Your ${done} bets, as a story</i></button>` : ""}</div>`;
}
function bzAfterRender() {
  try {
    const hx = document.querySelector("#view .hx2");
    if (hx && !hx.querySelector(".bz-entry")) { const w = hx.querySelector(".w-card"); const box = document.createElement("div"); box.innerHTML = bzHomeCards();
      if (box.firstElementChild && w) w.after(box.firstElementChild); }
    const pv = document.querySelector("body.tab-props #view");
    if (pv && !pv.querySelector(".bz-go") && bzPool().length) { const b = document.createElement("div"); b.innerHTML = `<button class="bz-go sm" data-blitz="1"><span class="bz-go-ic"><img src="bolt.png" alt=""></span><span class="bz-go-t"><b>Blitz Mode</b><i>Swipe the model's picks</i></span><span class="bz-go-a">›</span></button>`; pv.prepend(b.firstElementChild); }
  } catch (e) {}
  document.querySelectorAll("[data-blitz]").forEach(b => b.onclick = () => { mbHaptic(); bzOpen(); });
  document.querySelectorAll("[data-wrapped]").forEach(b => b.onclick = () => { mbHaptic(); bzWrapped(); });
  document.querySelectorAll("#view .w-card, #view .fc, #view .wl-card, #view .pro-card").forEach(bzHolo);
}
// slip + receipt hooks: tap a slip pick to X-Ray it
document.addEventListener("click", e => {
  const t = e.target.closest("#sheet .slipi .slipt"); if (!t) return;
  const i = [...document.querySelectorAll("#sheet .slipi")].indexOf(t.closest(".slipi")), l = slipLoad()[i]; if (!l) return;
  mbHaptic(); bzXray(l, () => mbOpenSlip());
});
