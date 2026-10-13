// ---------- 🧭 APP SHELL: app bar (wallet + level), league tabs, docked tab bar with the bet slip in the middle ----------
// Shared by both pages. Pages call shNav(render) from nav(); shAfterRender() runs after every render.
document.body.classList.add("shell");
// the date / last-update line sits on the league-tab row so the title row has room for the wallet
(() => { const sub = document.getElementById("sub"), hb2 = document.querySelector(".hb2"); if (sub && hb2) hb2.insertBefore(sub, hb2.querySelector(".iconbtn")); })();
// image fallbacks: a headshot that fails to load swaps to its alternate photo before the page's own fallback (initials) kicks in
const MB_IMG_ALT = {};
document.addEventListener("error", e => { const im = e.target; if (!im || im.tagName !== "IMG" || im.dataset.alt) return;
  const alt = MB_IMG_ALT[im.getAttribute("src")]; if (!alt) return; im.dataset.alt = "1"; e.stopImmediatePropagation(); im.src = alt; }, true);
function shImgAlts() { try { for (const d of [typeof TODAY !== "undefined" && TODAY, typeof D !== "undefined" && D]) if (d && d.players && !d._alts) {
  d._alts = 1; for (const p of d.players) { if (!p.headshot) continue;
    const alt = p.headshot_alt || (/\/mugs\/nhl\/\d+\/[A-Z]+\//.test(p.headshot) ? p.headshot.replace(/\/mugs\/nhl\/\d+\/[A-Z]+\//, "/mugs/nhl/latest/") : null);   // NHL: this season's mug, else the latest one
    if (alt) MB_IMG_ALT[p.headshot] = alt; } } } catch (e) {} }
const SH_TABS = [["home", "Home"], ["games", "Games"], ["slip", "Bet slip"], ["props", "Props"], ["check", "My Bets"]];
const SH_SLIP_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3.5h12v17l-2-1.4-2 1.4-2-1.4-2 1.4-2-1.4-2 1.4z"/><path d="M9 8.5h6M9 12h6M9 15.5h3.5"/></svg>';
function shNav(render) {
  const el = document.getElementById("nav"); if (!el) return;
  el.style.setProperty("--n", SH_TABS.length);
  el.innerHTML = SH_TABS.map(([k, n]) => k === "slip"
    ? `<button id="slipfab" class="sh-slip" aria-label="Bet slip"><span class="sh-sb">${SH_SLIP_IC}<b class="sh-n"></b></span><span class="sh-sl">${n}</span><i class="sh-odds"></i></button>`
    : `<button class="${TAB === k ? "on" : ""}" data-k="${k}">${mbIcon(k)}<span>${n}</span></button>`).join("");
  el.querySelectorAll("[data-k]").forEach(b => b.onclick = () => { if (TAB !== b.dataset.k) mbHaptic(); TAB = b.dataset.k; if (TAB === "check") MB_VIEW = "bets"; render(); window.scrollTo(0, 0); });
  el.querySelector("#slipfab").onclick = () => { mbHaptic(); mbOpenSlip(); };
}
// the centre button: slip count, and the parlay price riding above it
function shSlipBtn(pop) {
  const f = document.getElementById("slipfab"); if (!f || !f.classList.contains("sh-slip")) return false;
  const v = slipLoad(), n = v.length, dec = v.reduce((a, x) => a * mbDec(x.odds), 1);
  f.classList.toggle("has", n > 0);
  f.querySelector(".sh-n").textContent = n || "";
  f.querySelector(".sh-odds").textContent = !n ? "" : n > 1 && slipParlayOk(v) ? mbSign(mbAm(dec)) : n > 1 ? `${n} bets` : mbSign(v[0].odds);
  if (pop) { f.classList.remove("pop"); void f.offsetWidth; f.classList.add("pop"); }
  document.body.classList.toggle("hasslip", n > 0);
  return true;
}
// app bar: wallet pill (tap → My Bets) and level ring (tap → Rewards)
function shHeader(render) {
  const h = document.querySelector(".hdr"); if (!h) return;
  let r = h.querySelector(".sh-right");
  if (!r) { r = document.createElement("div"); r.className = "sh-right"; const t = h.querySelector(".hb1") || h; t.appendChild(r); }
  const s = mbLoad(), W = mbWallet(s), L = mbLevel(mbXP(s)), live = s.bets.filter(b => b.status === "open" && mbIsLive(b)).length;
  r.innerHTML = `<button class="sh-wal ${TAB === "check" ? "on" : ""}" data-shgo="check"><i class="sh-wd ${live ? "live" : W.pl >= 0 ? "up" : "dn"}"></i><b>${mbMoney(W.available).replace(/\.\d\d$/, "")}</b>${W.risk > 0 ? `<em>${mbShort(W.risk)} in play</em>` : ""}</button>
    <button class="sh-lvl ${TAB === "rewards" ? "on" : ""}" data-shgo="rewards" aria-label="Rewards · level ${L.lvl}">${passRing(L, 38)}${mbDaily(s).claimed ? "" : '<i class="sh-dot"></i>'}</button>`;
  r.querySelectorAll("[data-shgo]").forEach(b => b.onclick = () => { mbHaptic(); TAB = TAB === b.dataset.shgo ? "home" : b.dataset.shgo; if (TAB === "check") MB_VIEW = "bets"; render(); window.scrollTo(0, 0); });
}
function shAfterRender(render) {
  shImgAlts();
  const b = document.body;
  [...b.classList].filter(c => c.startsWith("tab-")).forEach(c => b.classList.remove(c));
  b.classList.add("tab-" + (typeof TAB !== "undefined" ? TAB : "home"));
  try { shHeader(render); } catch (e) {}
  const h = document.querySelector(".hdr"); if (h) document.documentElement.style.setProperty("--hdrh", h.offsetHeight + "px");   // for the sticky Games switch + feed snapping
  shSlipBtn();
}
