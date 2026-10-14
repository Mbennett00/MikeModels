// ---------- 💎 ATELIER: the premium layer for Obsidian ----------
// Live island (your bets, Dynamic-Island style), cinematic matchup posters on Games, smooth tab transitions,
// and an aurora that leans green or red with today's results.

// ---- 🏝️ live island: a pill under the header that knows what you're sweating ----
let ISL_OPEN = false, ISL_I = 0;
function islData() {
  const s = mbLoad(), open = s.bets.filter(b => b.status === "open"), live = open.filter(mbIsLive), items = [];
  for (const b of live) {
    const l = b.legs.find(x => x.res == null) || b.legs[0]; let L = null; try { L = typeof mbLiveLeg === "function" ? mbLiveLeg(l) : null; } catch (e) {}
    const k = (l && l.key) || {}, P = (() => { try { return mbWinProb(b); } catch (e) { return null; } })();
    const stat = L && k.t === "prop" && L.cur != null ? `${L.cur}/${Math.floor(k.l) + 1} ${L.unit}` : L && L.state !== "pre" ? `${L.awayAbbr} ${L.away}–${L.home} ${L.homeAbbr}` : "";
    items.push({b, l, P, stat, detail: L && L.detail});
  }
  const night = typeof rcNight === "function" ? rcNight : (t => new Date(t).toDateString()), today = night(Date.now()), settled = s.bets.filter(b => b.status !== "open" && night(b.result_ts || b.ts) === today);
  const day = settled.reduce((a, b) => a + mbProfit(b), 0);
  const next = open.flatMap(b => b.legs.map(l => l.start)).filter(t => t && new Date(t) > new Date()).sort()[0];
  return {items, open: open.length, day, nsettled: settled.length, next};
}
function islRender() {
  let el = document.getElementById("island");
  const hdr = document.querySelector(".hdr"); if (!hdr) return;
  if (!el) { el = document.createElement("button"); el.id = "island"; el.onclick = e => { e.stopPropagation(); mbHaptic(); ISL_OPEN = !ISL_OPEN; islRender(); }; document.body.appendChild(el); }
  const d = islData();
  if (!d.items.length && !d.open && !d.nsettled) { el.className = "off"; el.innerHTML = ""; document.body.classList.remove("has-island"); return; }
  document.body.classList.add("has-island");
  const dayTxt = d.nsettled ? `<em class="${d.day >= 0 ? "up" : "dn"}">${typeof rcFmt === "function" ? rcFmt(d.day) : (d.day >= 0 ? "+" : "−") + mbShort(Math.abs(d.day))} tonight</em>` : "";
  let pill;
  if (d.items.length) { const it = d.items[ISL_I % d.items.length];
    pill = `<span class="is-live"><i></i>LIVE</span><span class="is-t">${esc(it.l ? it.l.label : it.b.label)}</span>${it.stat ? `<span class="is-s">${esc(it.stat)}</span>` : ""}${it.P != null ? `<span class="is-p" style="--p:${Math.round(100 * it.P)}"><b>${Math.round(100 * it.P)}</b></span>` : ""}`; }
  else if (d.open) pill = `<span class="is-dot"></span><span class="is-t">${d.open} open bet${d.open > 1 ? "s" : ""}</span>${d.next ? `<span class="is-s" data-cd="${esc(d.next)}">${islCountdown(d.next)}</span>` : ""}${dayTxt}`;
  else pill = `<span class="is-dot ${d.day >= 0 ? "up" : "dn"}"></span><span class="is-t">${d.nsettled} settled tonight</span>${dayTxt}`;
  const panel = ISL_OPEN ? `<div class="is-panel">${d.items.length ? d.items.map(it => `<div class="is-row" data-tk="${esc(it.b.id)}">${mbPic(it.l || {})}<span class="is-rt"><b>${esc(it.b.kind === "parlay" ? `${it.b.legs.length}-leg parlay` : it.b.label)}</b><i>${esc(it.stat || "")}${it.detail ? ` · ${esc(it.detail)}` : ""}</i></span>
      ${it.P != null ? `<span class="is-bar"><i style="width:${Math.round(100 * it.P)}%"></i></span><span class="is-pc">${Math.round(100 * it.P)}%</span>` : ""}</div>`).join("")
      : `<div class="is-empty">${d.open ? `Nothing live yet. ${d.next ? `First puck drop ${islCountdown(d.next)}.` : ""}` : "No bets running."}</div>`}
    <div class="is-foot"><button data-isgo="1">My bets ›</button></div></div>` : "";
  el.className = (d.items.length ? "live " : "") + (ISL_OPEN ? "open" : "");
  el.innerHTML = `<span class="is-pill">${pill}</span>${panel}`;
  el.querySelectorAll("[data-tk]").forEach(r => r.onclick = e => { e.stopPropagation(); ISL_OPEN = false; islRender(); mbOpenTicket(r.dataset.tk); });
  const go = el.querySelector("[data-isgo]"); if (go) go.onclick = e => { e.stopPropagation(); ISL_OPEN = false; TAB = "check"; MB_VIEW = "bets"; MB_BTAB = "open"; MB_RENDER && MB_RENDER(); window.scrollTo(0, 0); };
}
function islCountdown(t) { const m = Math.max(0, Math.round((new Date(t) - Date.now()) / 6e4)); return m >= 60 ? `in ${Math.floor(m / 60)}h ${m % 60}m` : m > 0 ? `in ${m}m` : "now"; }
setInterval(() => { if (document.hidden || ISL_OPEN) return; const el = document.getElementById("island"); if (!el || !el.classList.contains("live")) return; ISL_I++; try { islRender(); } catch (e) {} }, 5000);
document.addEventListener("click", () => { if (ISL_OPEN) { ISL_OPEN = false; islRender(); } });

// ---- 🎬 spotlight: tonight's games as cinematic posters (top of Games) ----
function atWinHome(g) { try { if (g.p_home != null) return g.p_home; if (typeof gameProb === "function") return gameProb(g, "moneyline", "home"); } catch (e) {} return null; }
function atPosters() {
  const gs = (typeof D !== "undefined" && D && D.games || []).filter(g => !mbStarted({start: g.start_utc})).slice(0, 8); if (gs.length < 2) return "";
  const best = {}; try { for (const l of bzPool()) if (bzEdge(l) > 0.01 && !best[l.gid]) best[l.gid] = l; } catch (e) {}
  return `<div class="spot"><div class="spot-h"><b>Spotlight</b><i>${gs.length} games · swipe</i></div><div class="spot-rail">${gs.map(g => {
    const a = g.away || {}, h = g.home || {}, ph = atWinHome(g), t = g.start_utc ? new Date(g.start_utc).toLocaleTimeString("en-US", {hour: "numeric", minute: "2-digit"}) : "", bb = best[g.game_id];
    return `<button class="post" data-post="${esc(String(g.game_id))}" style="--ca:${esc(a.color || "#333")};--ch:${esc(h.color || "#333")}">
      <span class="post-bg"></span><span class="post-grain"></span>
      <img class="post-l a" src="${esc(a.logo || "")}" alt="" onerror="this.remove()"><img class="post-l h" src="${esc(h.logo || "")}" alt="" onerror="this.remove()">
      <span class="post-time">${esc(t)}</span>
      <span class="post-names"><b>${esc(a.name || a.abbr || "")}</b><em>at</em><b>${esc(h.name || h.abbr || "")}</b></span>
      ${ph != null ? `<span class="post-wp"><span>${Math.round(100 * (1 - ph))}%</span><span class="post-wb"><i style="width:${Math.round(100 * (1 - ph))}%"></i></span><span>${Math.round(100 * ph)}%</span></span>` : ""}
      ${bb ? `<span class="post-bb">Best bet · ${esc(bb.label)} <b>${mbSign(bb.odds)}</b></span>` : ""}</button>`; }).join("")}</div></div>`;
}
function atWirePosters() {
  const rail = document.querySelector("#view .spot-rail"); if (!rail) return;
  const par = () => { const r = rail.getBoundingClientRect(); rail.querySelectorAll(".post").forEach(p => { const b = p.getBoundingClientRect(), k = ((b.left + b.width / 2) - (r.left + r.width / 2)) / r.width;
    p.style.setProperty("--k", k.toFixed(3)); }); };
  let q = 0; rail.addEventListener("scroll", () => { if (q) return; q = requestAnimationFrame(() => { q = 0; par(); }); }, {passive: true}); requestAnimationFrame(par);
  rail.querySelectorAll("[data-post]").forEach(p => p.onclick = () => { mbHaptic(); const id = p.dataset.post;
    const jump = () => { const c = document.querySelector(`#view [data-gid="${CSS.escape(id)}"]`); if (c) c.scrollIntoView({behavior: "smooth", block: "start"}); };
    if (!document.querySelector(`#view [data-gid="${CSS.escape(id)}"]`) && typeof FX_GMODE !== "undefined") { FX_GMODE = "feed"; try { localStorage.setItem("mm_gmode", "feed"); } catch (e) {} MB_RENDER && MB_RENDER(); setTimeout(jump, 120); } else jump(); });
}

// ---- 🌗 smooth tab changes (View Transitions where the browser has them) ----
if (document.startViewTransition) document.documentElement.classList.add("has-vt");
function atNavTransitions() {
  if (!document.startViewTransition) return;
  document.querySelectorAll("#nav [data-k]").forEach(b => { if (b.dataset.vt) return; b.dataset.vt = 1; const orig = b.onclick;
    b.onclick = e => { if (!orig) return; document.documentElement.classList.add("vt"); const t = document.startViewTransition(() => orig.call(b, e)); t.finished.finally(() => document.documentElement.classList.remove("vt")); }; });
}

// ---- aurora mood: today's results tint the light ----
function atMood() {
  const s = mbLoad(), today = new Date().toDateString(), day = s.bets.filter(b => b.status !== "open" && new Date(b.result_ts || b.ts).toDateString() === today).reduce((a, b) => a + mbProfit(b), 0);
  document.body.classList.toggle("mood-up", day > 0.5); document.body.classList.toggle("mood-dn", day < -0.5);
}

// sideways rails keep their place when the screen redraws (live refreshes, taps)
const AT_RAILS = ".spot-rail, .alt-lad, .fz, .strip, .gchips", AT_X = {};
const atRailKey = el => { const host = el.closest("[data-player], .pk, .gc2"); const id = host ? (host.querySelector("[data-player]") || host).getAttribute("data-player") || host.getAttribute("data-gid") || "" : "";
  const all = [...document.querySelectorAll("#view " + el.className.split(" ")[0].replace(/^/, "."))]; return (typeof TAB !== "undefined" ? TAB : "") + "|" + el.className.split(" ")[0] + "|" + (id || all.indexOf(el)); };
document.addEventListener("scroll", e => { const el = e.target; if (el && el.nodeType === 1 && el.matches && el.matches(AT_RAILS)) AT_X[atRailKey(el)] = el.scrollLeft; }, {capture: true, passive: true});
function atRestoreRails() { document.querySelectorAll("#view " + AT_RAILS.split(", ").join(", #view ")).forEach(el => { const x = AT_X[atRailKey(el)]; if (x != null) { el.scrollLeft = x; el.dataset.cen = 1; } }); }
function atAfterRender() {
  try { islRender(); } catch (e) {}
  try { const v = document.querySelector("body.tab-games #view"); if (v && !v.querySelector(".spot")) { const h = atPosters(); if (h) { const d = document.createElement("div"); d.innerHTML = h; const anchor = v.querySelector(".pmode, .gmode"); anchor ? anchor.before(d.firstElementChild) : v.prepend(d.firstElementChild); } } atWirePosters(); } catch (e) {}
  try { atNavTransitions(); } catch (e) {}
  // alt shots: each row opens on the line nearest the projection (or the one on your slip)
  document.querySelectorAll("#view .alt-lad").forEach(r => { if (r.dataset.cen || AT_X[atRailKey(r)] != null) return; r.dataset.cen = 1; const t = r.querySelector(".alt-b.insl") || r.querySelector(".alt-b.near"); if (t) r.scrollLeft = Math.max(0, t.offsetLeft - r.clientWidth / 2 + t.offsetWidth / 2); });
  try { atMood(); } catch (e) {}
  try { atRestoreRails(); } catch (e) {}   // last, after the posters and rows exist
}
