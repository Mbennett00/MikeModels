// Game simulator shell shared by the NFL and NHL sims: the matchup picker, live playback, the final with its tabs, and the
// 1,000-game mode. Each page defines SIMX: its data, its engine and how its own pieces (field or rink, box score) look.
"use strict";
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const R = Math.random;
const pick = (arr, w) => { let t = 0; for (const x of w) t += x; let r = R() * t; for (let i = 0; i < arr.length; i++) { r -= w[i]; if (r <= 0) return arr[i]; } return arr[arr.length - 1]; };
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const expo = () => -Math.log(1 - R());
const norm = () => { let u = 0, v = 0; while (!u) u = R(); while (!v) v = R(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
const lastName = n => { const w = String(n).split(" "); return w.length > 1 && /^(jr\.?|sr\.?|ii|iii|iv)$/i.test(w[w.length - 1]) ? w[w.length - 2] : w[w.length - 1]; };
const sxPct = p => `${Math.round(100 * p)}%`;
// a team colour that reads on the dark background: the second colour when the first is too dark, else the first lifted toward white
function sxVis(c, alt) {
  const lum = h => { const m = /^#?([0-9a-f]{6})$/i.exec(h || ""); if (!m) return -1; const n = parseInt(m[1], 16); return (.2126 * (n >> 16) + .7152 * (n >> 8 & 255) + .0722 * (n & 255)) / 255; };
  if (lum(c) >= .22) return c; if (lum(alt) >= .22 && lum(alt) < .9) return alt; if (lum(c) < 0) return "#7a8a84";
  const n = parseInt(c.replace("#", ""), 16), mix = v => Math.round(v + (255 - v) * .38);
  return `rgb(${mix(n >> 16)},${mix(n >> 8 & 255)},${mix(n & 255)})`;
}
const SX = {mode: "live", sim: null, n: 0, speed: 1, playing: true, tab: "sum", timer: null, multi: null};
const ICON = {
  back: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>`,
  pause: `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>`,
  play: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L8.5 4.64A1 1 0 0 0 7 5.5z"/></svg>`,
  skip: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 6.2v11.6a.8.8 0 0 0 1.2.7l8.3-5.8a.8.8 0 0 0 0-1.4L5.2 5.5a.8.8 0 0 0-1.2.7zM13 6.2v11.6a.8.8 0 0 0 1.2.7l8.3-5.8a.8.8 0 0 0 0-1.4l-8.3-5.8a.8.8 0 0 0-1.2.7z"/></svg>`,
};

// ---------- small shared pieces ----------
function sxNoLogo(img) { const s = document.createElement("span"); s.className = "sx-code " + img.className.replace("sx-logo", ""); s.textContent = img.dataset.ab || ""; img.replaceWith(s); }
const sxLogo = t => t.logo ? `<img class="sx-logo" src="${esc(t.logo)}" alt="" data-ab="${esc(t.ab)}" onerror="sxNoLogo(this)">` : `<span class="sx-code sx-logo">${esc(t.ab)}</span>`;
// team stat comparison: [label, away value, home value, higher is better (true), lower is better (false) or neither (null), shown away, shown home]
function sxCompare(sim, rows) {
  const {T} = sim;
  return `<div class="sx-card sx-cmp">${rows.map(([l, va, vh, hib, sa, sh]) => {
    const tot = Math.abs(va) + Math.abs(vh), wa = hib == null || va === vh ? "" : (va > vh) === hib ? "w" : "l", wh = wa === "w" ? "l" : wa === "l" ? "w" : "";
    return `<div class="sx-cr"><div><b class="${wa}">${sa ?? va}</b><span>${l}</span><b class="${wh}">${sh ?? vh}</b></div>
      <div class="sx-bar"><i style="flex:${tot ? Math.abs(va) / tot : .5};background:${esc(T.a.color)}"></i><i style="flex:${tot ? Math.abs(vh) / tot : .5};background:${esc(T.h.color)}"></i></div></div>`; }).join("")}</div>`;
}
// line score: columns are periods, then the total
function sxLineScore(sim, heads, cols) {
  return `<div class="sx-card"><table class="sx-ls"><tr><th></th>${heads.map(h => `<th>${h}</th>`).join("")}<th>T</th></tr>${["a", "h"].map(k => `<tr><td>${sxLogo(sim.T[k])}${esc(sim.T[k].ab)}</td>${cols[k].map(v => `<td>${v}</td>`).join("")}<td class="t">${sim.final[k]}</td></tr>`).join("")}</table></div>`;
}
const sxTable = (head, rows) => rows.length ? `<table class="sx-tb"><tr>${head.map(h => `<th>${h}</th>`).join("")}</tr>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</table>` : "";
const sxHead = t => `<div class="sx-bh">${sxLogo(t)}${esc(t.full || t.name)}</div>`;
function sxTops(cards) {   // three spotlight players: {label, name, img, team, line}
  return `<div class="sx-tops">${cards.map(c => `<div class="sx-top3" style="--c:${esc(c.team.color)}"><i>${esc(c.label)}</i>${c.img ? `<img class="hs" src="${esc(c.img)}" alt="" onerror="this.src='${esc(c.team.logo)}'">` : `<img class="hs" src="${esc(c.team.logo)}" alt="">`}<b>${esc(c.name)}</b><span>${esc(c.team.ab)} · ${c.line}</span></div>`).join("")}</div>`;
}
const sxSec = (text, t) => `<div class="sx-sec">${t ? sxLogo(t) : ""}${esc(text)}</div>`;
function sxRow(e, sim) {
  if (e.kind === "sec") return sxSec(e.text, e.side && sim.T[e.side]);
  return `<div class="sx-r ${e.sc ? "sc" : ""} ${e.to ? "to" : ""}"><i>${esc(e.pl)} ${esc(e.t)}</i><span>${e.dd ? `<span class="sx-dd">${esc(e.dd)}</span>` : ""}${e.text}</span>${e.sc ? `<em>${e.score.a}–${e.score.h}</em>` : ""}</div>`;
}

// ---------- picker ----------
function sxPicker() {
  const T = SIMX.teams(), G = SIMX.slate(), u = new URLSearchParams(location.search), g0 = G[0];
  const a = T.some(t => t.ab === u.get("away")) ? u.get("away") : g0 ? g0.a.ab : T[0].ab, h = T.some(t => t.ab === u.get("home")) ? u.get("home") : g0 ? g0.h.ab : T[1].ab;
  const opt = sel => T.map(t => `<option value="${t.ab}" ${t.ab === sel ? "selected" : ""}>${esc(t.full || t.name)}</option>`).join("");
  const rows = G.map(g => `<button class="sx-g" data-go="${g.a.ab}|${g.h.ab}">
      <span class="sx-gt">${sxLogo(g.a)}<b>${esc(g.a.ab)}</b><i>${SIMX.fmt(g.pa)}</i></span>
      <span class="sx-gm"><em>${esc(g.when || "")}</em><span class="sx-wp"><i style="width:${Math.round(84 * (1 - g.pHome))}px;background:${esc(g.a.color)}"></i><i style="background:${esc(g.h.color)}"></i></span><small>${sxPct(1 - g.pHome)} · ${sxPct(g.pHome)}</small></span>
      <span class="sx-gt r"><i>${SIMX.fmt(g.ph)}</i><b>${esc(g.h.ab)}</b>${sxLogo(g.h)}</span></button>`).join("");
  return `<div class="sx-seg sx-mode">${[["live", "Watch a game"], ["multi", "Sim 1,000 games"]].map(([k, l]) => `<button class="${SX.mode === k ? "on" : ""}" data-mode="${k}">${l}</button>`).join("")}</div>
    ${G.length ? `<div class="sx-h"><b>${esc(SIMX.slateLabel())}</b><span>Model projection · win chance</span></div><div class="sx-list">${rows}</div>` : ""}
    <div class="sx-h"><b>Any matchup</b></div>
    <div class="sx-card sx-custom"><div class="sx-sel"><label>Away<select id="sa">${opt(a)}</select></label><span>@</span><label>Home<select id="sh">${opt(h)}</select></label></div>
      <button class="sx-btn" id="go">${SX.mode === "multi" ? "Sim 1,000 games" : "Watch the game"}</button></div>
    <p class="sx-note">${SIMX.note}</p>`;
}

// ---------- live ----------
function sxBoard(sim, e, final) {
  const sc = final ? sim.final : e ? e.score : {a: 0, h: 0};
  const team = k => { const o = k === "a" ? "h" : "a", lose = final && sc[k] < sc[o];
    return `<div class="sx-team ${k} ${lose ? "dim" : ""}">${sxLogo(sim.T[k])}<div class="sx-tn"><b>${k === "h" && !final && e && e.side === k ? '<i class="sx-pos"></i>' : ""}${esc(sim.T[k].ab)}${k === "a" && !final && e && e.side === k ? '<i class="sx-pos"></i>' : ""}</b><span>${esc(SIMX.teamSub(sim, e, k, final))}</span></div><strong>${sc[k]}</strong></div>`; };
  const mid = final ? `<b class="sx-fin">${esc(SIMX.finalLab(sim))}</b>` : `<b>${esc(e ? e.pl : SIMX.startPl)}</b><span>${esc(e ? e.t : SIMX.startClock)}</span>`;
  return `<div class="sx-sb">${team("a")}<div class="sx-mid">${mid}</div>${team("h")}</div>`;
}
function sxLive() {
  const sim = SX.sim, shown = sim.ev.slice(0, SX.n), cur = shown[shown.length - 1], last = [...shown].reverse().find(e => e.kind !== "sec");
  const now = last ? `<div class="sx-now ${last.sc ? "big" : ""}" style="--c:${esc(last.side ? sim.T[last.side].color : "var(--line2)")}"><div><span>${esc(last.pl)} ${esc(last.t)}${last.side ? " · " + esc(sim.T[last.side].ab) : ""}</span><p>${last.text}</p></div></div>` : `<div class="sx-now"><div><span>&nbsp;</span><p>${esc(SIMX.kickText)}</p></div></div>`;
  const sp = [[1, "1×"], [3, "3×"], [10, "10×"]].map(([s, l]) => `<button class="${SX.speed === s ? "on" : ""}" data-sp="${s}">${l}</button>`).join("");
  return `<section class="sx-card">${sxBoard(sim, cur, false)}${SIMX.stage(sim, cur, SX.n)}${now}</section>
    <div class="sx-ctl"><div class="sx-seg">${sp}</div><button class="sx-ib" data-play aria-label="${SX.playing ? "Pause" : "Play"}">${SX.playing ? ICON.pause : ICON.play}</button><button class="sx-ib" data-skip>Final ${ICON.skip}</button></div>
    <div class="sx-card sx-feed">${shown.slice(-50).reverse().map(e => sxRow(e, sim)).join("")}</div>`;
}

// ---------- final ----------
function sxFinal() {
  const sim = SX.sim, tabs = [["sum", "Summary"], ["box", "Box score"], ["pbp", "Plays"]];
  const body = SX.tab === "box" ? SIMX.box(sim) : SX.tab === "pbp" ? `<div class="sx-card sx-feed">${sim.ev.map(e => sxRow(e, sim)).join("")}</div>` : SIMX.summary(sim);
  return `<section class="sx-card">${sxBoard(sim, null, true)}</section>
    <div class="sx-seg sx-tabs">${tabs.map(([k, l]) => `<button class="${SX.tab === k ? "on" : ""}" data-tab="${k}">${l}</button>`).join("")}</div>
    ${body}
    <div class="sx-act"><button class="sx-btn" data-again>Sim again</button><button class="sx-btn ghost" data-new>New matchup</button></div>`;
}

// ---------- 1,000 games ----------
function sxMultiView() {
  const M = SX.multi, T = M.T;
  if (M.done < M.N) return `<section class="sx-card" style="padding:18px 14px"><div class="sx-sb" style="padding:0">${["a", "h"].map(k => `<div class="sx-team ${k}">${sxLogo(T[k])}<div class="sx-tn"><b>${esc(T[k].ab)}</b><span>${esc(T[k].name)}</span></div></div>`).join('<div class="sx-mid"><b>vs</b></div>')}</div>
      <div class="sx-prog"><i style="width:${(100 * M.done / M.N).toFixed(1)}%"></i></div><div class="sx-note" style="margin:0">${M.done ? `Simulated ${M.done.toLocaleString()} of ${M.N.toLocaleString()} games…` : "Tuning the sim to the model's projection for this matchup…"}</div></section>`;
  const D = M.res, n = D.length, wa = D.filter(d => d.s.a > d.s.h).length / n, wh = D.filter(d => d.s.h > d.s.a).length / n, tie = 1 - wa - wh;
  const avg = k => D.reduce((x, d) => x + (d.r || d.s)[k], 0) / n, ex = M.exp;   // NHL compares regulation goals, as the model does
  const sc = {}; for (const d of D) { const k = `${d.s.a}–${d.s.h}`; sc[k] = (sc[k] || 0) + 1; }
  const top = Object.entries(sc).sort((x, y) => y[1] - x[1]).slice(0, 8);
  const bins = SIMX.marginBins, hist = bins.map(([lo, hi]) => D.filter(d => { const m = d.s.h - d.s.a; return m >= lo && m <= hi; }).length), hmax = Math.max(...hist, 1);
  const ot = D.filter(d => d.ot).length / n;
  return `<section class="sx-card"><div class="sx-mw">${["a", "h"].map(k => `<div class="${k}"><span class="tn">${sxLogo(T[k])}${esc(T[k].ab)}</span><strong>${sxPct(k === "a" ? wa : wh)}</strong><span>${M.pModel != null ? `Model ${sxPct(k === "a" ? 1 - M.pModel : M.pModel)}` : "win"}</span></div>`).join("")}</div>
      <div class="sx-mbar"><i style="flex:${wa};background:${esc(T.a.color)}"></i>${tie > .001 ? `<i style="flex:${tie};background:var(--line2)"></i>` : ""}<i style="flex:${wh};background:${esc(T.h.color)}"></i></div>
      <div class="sx-kv"><div><i>${esc(SIMX.avgLabel || "Avg score")}</i><b>${SIMX.fmt(avg("a"))} – ${SIMX.fmt(avg("h"))}</b><span>Model ${SIMX.fmt(ex[0])} – ${SIMX.fmt(ex[1])}</span></div>
        <div><i>Avg total</i><b>${SIMX.fmt(avg("a") + avg("h"))}</b><span>Model ${SIMX.fmt(ex[0] + ex[1])}</span></div>
        <div><i>${esc(SIMX.otLabel)}</i><b>${sxPct(ot)}</b><span>${tie > .001 ? `Ties ${sxPct(tie)}` : `${n.toLocaleString()} games`}</span></div></div></section>
    <div class="sx-h"><b>Most common finals</b><span>${esc(T.a.ab)}–${esc(T.h.ab)}</span></div>
    <div class="sx-chips">${top.map(([s, c]) => `<span>${s}<i>${(100 * c / n).toFixed(1)}%</i></span>`).join("")}</div>
    <div class="sx-h"><b>Winning margin</b><span>How often each result came up</span></div>
    <div class="sx-card"><div class="sx-hist">${hist.map((c, i) => { const [lo, hi] = bins[i], mid = (lo + hi) / 2; return `<i title="${c}" style="height:${(100 * c / hmax).toFixed(1)}%;background:${esc(mid < 0 ? T.a.color : mid > 0 ? T.h.color : "var(--line2)")}"></i>`; }).join("")}</div>
      <div class="sx-hx"><span>${esc(T.a.ab)} by ${SIMX.marginEdge}+</span><span>${esc(SIMX.marginMid)}</span><span>${esc(T.h.ab)} by ${SIMX.marginEdge}+</span></div></div>
    ${SIMX.multiPlayers(M)}
    <div class="sx-act"><button class="sx-btn" data-watch>Watch one</button><button class="sx-btn ghost" data-new>New matchup</button></div>`;
}
function sxRunMulti(a, h) {
  clearTimeout(SX.timer); SX.sim = null;
  const T = {a: SIMX.team(a), h: SIMX.team(h)};
  SX.multi = {a, h, T, N: SIMX.multiN, done: 0, res: [], exp: SIMX.expected(a, h), pModel: SIMX.pModel(a, h)};
  history.replaceState(null, "", `?away=${a}&home=${h}&mode=multi`); render(); window.scrollTo(0, 0);
  const M = SX.multi;
  setTimeout(() => { SIMX.prepare(a, h);
    const step = () => { if (SX.multi !== M) return; const end = Math.min(M.N, M.done + SIMX.multiChunk);
      for (; M.done < end; M.done++) M.res.push(SIMX.digest(SIMX.simulate(a, h, true)));
      render(); if (M.done < M.N) SX.timer = setTimeout(step, 0); };
    step(); }, 30);
}

// ---------- flow ----------
function render() {
  const v = $("#view");
  v.innerHTML = SX.multi ? sxMultiView() : !SX.sim ? sxPicker() : SX.n >= SX.sim.ev.length ? sxFinal() : sxLive();
  const on = (sel, f) => v.querySelectorAll(sel).forEach(b => b.onclick = () => f(b));
  on("[data-mode]", b => { SX.mode = b.dataset.mode; render(); });
  on("[data-go]", b => { const [a, h] = b.dataset.go.split("|"); go(a, h); });
  on("#go", () => go($("#sa").value, $("#sh").value));
  on("[data-sp]", b => { SX.speed = +b.dataset.sp; SX.playing = true; play(); render(); });
  on("[data-play]", () => { SX.playing = !SX.playing; SX.playing ? play() : clearTimeout(SX.timer); render(); });
  on("[data-skip]", () => { clearTimeout(SX.timer); SX.n = SX.sim.ev.length; SX.tab = "sum"; render(); window.scrollTo(0, 0); });
  on("[data-tab]", b => { SX.tab = b.dataset.tab; render(); });
  on("[data-again]", () => watch(SX.sim.a, SX.sim.h));
  on("[data-watch]", () => watch(SX.multi.a, SX.multi.h));
  on("[data-new]", () => { clearTimeout(SX.timer); SX.sim = null; SX.multi = null; history.replaceState(null, "", location.pathname); render(); window.scrollTo(0, 0); });
}
function play() {
  clearTimeout(SX.timer);
  const step = () => { if (!SX.sim || !SX.playing) return; SX.n++; if (SX.n >= SX.sim.ev.length) SX.tab = "sum"; render(); if (SX.n >= SX.sim.ev.length) { window.scrollTo(0, 0); return; } SX.timer = setTimeout(step, 1000 / SX.speed); };
  SX.timer = setTimeout(step, 1000 / SX.speed);
}
function watch(a, h) {
  clearTimeout(SX.timer); SX.multi = null; SX.sim = null;
  history.replaceState(null, "", `?away=${a}&home=${h}`);
  $("#view").innerHTML = `<section class="sx-card" style="padding:18px 14px"><div class="sx-note" style="margin:0">Setting up ${esc(SIMX.team(a).ab)} at ${esc(SIMX.team(h).ab)}…</div><div class="sx-prog"><i style="width:60%"></i></div></section>`;
  window.scrollTo(0, 0);
  setTimeout(() => { SIMX.prepare(a, h); SX.sim = SIMX.simulate(a, h, false); SX.n = 1; SX.playing = true; SX.tab = "sum"; render(); play(); }, 30);
}
// each matchup's tuning is kept per data release, so a matchup tunes once
function sxCalGet(sport, ver, key) { try { const v = JSON.parse(localStorage.getItem(`pikt-sim-${sport}`) || "{}"); return v.ver === String(ver) ? v.k[key] : null; } catch (e) { return null; } }
function sxCalPut(sport, ver, key, k) { try { const id = `pikt-sim-${sport}`, v = JSON.parse(localStorage.getItem(id) || "{}"), o = v.ver === String(ver) ? v : {ver: String(ver), k: {}}; o.k[key] = k; localStorage.setItem(id, JSON.stringify(o)); } catch (e) {} }
const go = (a, h) => { if (a === h) return; SX.mode === "multi" ? sxRunMulti(a, h) : watch(a, h); };
function sxBoot() {
  const extra = SIMX.extraUrl ? fetch(SIMX.extraUrl + "?v=" + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null) : Promise.resolve(null);   // the sim's league, team and player profiles
  Promise.all([fetch(SIMX.dataUrl + "?v=" + Date.now()).then(r => r.json()), extra]).then(([d, x]) => {
    SIMX.init(d, x);
    if (!SIMX.teams().length) { $("#view").innerHTML = `<div class="empty"><div class="t">${esc(SIMX.emptyText)}</div></div>`; return; }
    const u = new URLSearchParams(location.search);
    if (u.get("mode") === "multi") SX.mode = "multi";
    render();
  }).catch(e => { console.error(e); $("#view").innerHTML = `<div class="empty"><div class="t">Couldn't load the data</div></div>`; });
}
