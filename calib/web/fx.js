// ===== 🎬 production layer: confetti, ticket print, goal flashes, rolling numbers, cinematic splash =====

// ---- confetti (canvas, no library) ----
function fxConfetti(n = 140, colors = ["#6f8dff", "#a77bff", "#34d17b", "#ffffff", "#ffd166"], origin) {
  if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const c = document.createElement("canvas"), dpr = Math.min(2, window.devicePixelRatio || 1), W = innerWidth, H = innerHeight;
  c.className = "fx-confetti"; c.width = W * dpr; c.height = H * dpr; document.body.appendChild(c);
  const x = c.getContext("2d"); x.scale(dpr, dpr);
  const ox = origin ? origin.x : W / 2, oy = origin ? origin.y : H * .38;
  const P = Array.from({length: n}, () => { const a = -Math.PI / 2 + (Math.random() - .5) * Math.PI * 1.1, v = 7 + Math.random() * 9;
    return {x: ox, y: oy, vx: Math.cos(a) * v, vy: Math.sin(a) * v, r: Math.random() * 6.28, vr: (Math.random() - .5) * .4, w: 5 + Math.random() * 6, h: 8 + Math.random() * 8,
      c: colors[Math.floor(Math.random() * colors.length)], life: 0}; });
  const t0 = performance.now();
  const step = now => {
    const t = now - t0; x.clearRect(0, 0, W, H);
    for (const p of P) { p.vy += .32; p.vx *= .985; p.vy *= .985; p.x += p.vx; p.y += p.vy; p.r += p.vr;
      x.save(); x.translate(p.x, p.y); x.rotate(p.r); x.globalAlpha = Math.max(0, 1 - t / 2600); x.fillStyle = p.c;
      x.fillRect(-p.w / 2, -p.h / 2 * Math.abs(Math.cos(p.r * 2)), p.w, p.h * Math.abs(Math.cos(p.r * 2)) + 1); x.restore(); }
    if (t < 2600) requestAnimationFrame(step); else c.remove();
  };
  requestAnimationFrame(step);
}

// ---- rolling numbers ----
function fxRoll(el, from, to, ms = 900, fmt) {
  if (!el || !isFinite(from) || !isFinite(to) || Math.abs(to - from) < .005) return;
  const t0 = performance.now(), f = fmt || (v => mbMoney(v).replace(/(\.\d\d)$/, "<small>$1</small>"));
  el.classList.add("fx-rolling", to > from ? "fx-up" : "fx-dn");
  const step = now => { const k = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - k, 4); el.innerHTML = f(from + (to - from) * e);
    if (k < 1) requestAnimationFrame(step); else setTimeout(() => el.classList.remove("fx-rolling", "fx-up", "fx-dn"), 400); };
  requestAnimationFrame(step);
}
function fxBalance() {   // the Home balance rolls from what you last saw
  const el = document.querySelector(".hx-bal"); if (!el) return;
  const now = mbWallet().available; let was = null;
  try { was = Number(sessionStorage.getItem("fx_bal")); sessionStorage.setItem("fx_bal", String(now)); } catch (e) {}
  if (was != null && isFinite(was) && was > 0 && Math.abs(was - now) >= .01 && !el.dataset.rolled) { el.dataset.rolled = "1"; fxRoll(el, was, now, 1200); }
}

// ---- live game cards: goal flash, score flip, ribbon ----
const FX_SC = {};
function fxGoals() {
  document.querySelectorAll(".gc2[data-gid]").forEach(card => {
    const sc = card.querySelectorAll(".vs-score > span"); if (sc.length !== 2) return;
    const a = Number(sc[0].textContent), h = Number(sc[1].textContent), gid = card.dataset.gid, was = FX_SC[gid];
    FX_SC[gid] = [a, h];
    if (!was || (a <= was[0] && h <= was[1])) return;
    const home = h > was[1], col = getComputedStyle(card).getPropertyValue(home ? "--ch" : "--ca").trim() || "#ff5a5f";
    const nm = card.querySelector(`.vs-team.${home ? "h" : "a"} .gtn b`);
    sc[home ? 1 : 0].classList.add("fx-flip");
    card.style.setProperty("--goal", col); card.classList.remove("fx-goal"); void card.offsetWidth; card.classList.add("fx-goal");
    const r = document.createElement("div"); r.className = "fx-ribbon"; r.innerHTML = `<b>GOAL</b><span>${esc(nm ? nm.textContent : "")}</span>`;
    card.appendChild(r); setTimeout(() => { r.remove(); card.classList.remove("fx-goal"); }, 3200);
  });
}

// ---- price taps: a ripple where you touched ----
function fxRipple(e) {
  const b = e.target.closest(".pxb, .hx-add, .hl-add, .sp-btn, .placebet, .stk-go"); if (!b) return;
  const r = b.getBoundingClientRect(), s = document.createElement("span"), d = Math.max(r.width, r.height) * 2.2;
  s.className = "fx-rip"; s.style.cssText = `width:${d}px;height:${d}px;left:${e.clientX - r.left - d / 2}px;top:${e.clientY - r.top - d / 2}px`;
  b.appendChild(s); setTimeout(() => s.remove(), 600);
}
document.addEventListener("pointerdown", fxRipple, {passive: true});

// ---- the splash gets its moment: hold it ~1.2s, then open like a curtain ----
const FX_T0 = performance.now();
function fxSplash() {
  const sp = document.getElementById("splash"); if (!sp || sp.dataset.fx) return;
  sp.dataset.fx = "1"; sp.classList.add("fx-hold");
  const wait = Math.max(0, 1250 - (performance.now() - FX_T0));
  setTimeout(() => { sp.classList.add("fx-open"); setTimeout(() => sp.remove(), 700); }, wait);
}

function fxAfterRender() {
  try { fxSplash(); } catch (e) {}
  try { fxGoals(); } catch (e) {}
  try { fxBalance(); } catch (e) {}
}
