// ---------- 💎 ATELIER: the premium layer for Obsidian ----------
// Cinematic matchup posters on Games, smooth tab transitions,
// and an aurora that leans green or red with today's results.

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
  try { const v = document.querySelector("body.tab-games #view"); if (v && !v.querySelector(".spot")) { const h = atPosters(); if (h) { const d = document.createElement("div"); d.innerHTML = h; const anchor = v.querySelector(".pmode, .gmode"); anchor ? anchor.before(d.firstElementChild) : v.prepend(d.firstElementChild); } } atWirePosters(); } catch (e) {}
  try { atNavTransitions(); } catch (e) {}
  // alt shots: each row opens on the line nearest the projection (or the one on your slip)
  document.querySelectorAll("#view .alt-lad").forEach(r => { if (r.dataset.cen || AT_X[atRailKey(r)] != null) return; r.dataset.cen = 1; const t = r.querySelector(".alt-b.insl") || r.querySelector(".alt-b.near"); if (t) r.scrollLeft = Math.max(0, t.offsetLeft - r.clientWidth / 2 + t.offsetWidth / 2); });
  try { atMood(); } catch (e) {}
  try { atRestoreRails(); } catch (e) {}   // last, after the posters and rows exist
}
