// ---------- 📊 NIGHTLY RECAP: today's record and result, in dollars or units (Action Network style) ----------
// A "night" runs 6am to 6am, so a game that ends after midnight still counts for the night it was played.
// Unit size defaults to $100 (1u) and is set in Account; tap any recap number to flip between $ and units.
const rcUnit = (s = mbLoad()) => Number(s.unitSize) > 0 ? Number(s.unitSize) : 100;
const rcShowU = (s = mbLoad()) => !!s.showUnits;
function rcNight(ts) { const d = new Date(new Date(ts).getTime() - 6 * 36e5); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
function rcFmt(v, s = mbLoad(), forceU) {
  const u = forceU != null ? forceU : rcShowU(s), sign = v > 0.004 ? "+" : v < -0.004 ? "−" : "";
  return u ? `${sign}${(Math.abs(v) / rcUnit(s)).toFixed(2)}u` : `${sign}${mbMoney(Math.abs(v)).replace("−", "")}`;
}
function rcNights(s = mbLoad()) {
  const by = {};
  for (const b of s.bets) { if (b.status === "open") continue;
    const k = rcNight(b.result_ts || b.ts), n = by[k] = by[k] || {k, w: 0, l: 0, p: 0, net: 0, risk: 0, bets: []};
    const pl = mbProfit(b); n.net += pl; n.bets.push(b);
    if (b.status === "push" || (b.status === "lost" && mbInsured(b))) n.p++; else if (pl > 0) n.w++; else n.l++;
    if (b.status !== "push") n.risk += b.stake; }
  return Object.values(by).sort((a, b) => b.k.localeCompare(a.k));
}
function rcLabel(k) { const t = rcNight(Date.now()), y = rcNight(Date.now() - 864e5); if (k === t) return "Tonight"; if (k === y) return "Last night";
  const [Y, M, D] = k.split("-").map(Number); return new Date(Y, M - 1, D).toLocaleDateString("en-US", {weekday: "short", month: "short", day: "numeric"}); }
function rcRecord(n) { return `${n.w}–${n.l}${n.p ? `–${n.p}` : ""}`; }

// the card: tonight (or the last night you bet), the last 7 nights, and the running total
function rcCardHtml(compact) {
  const s = mbLoad(), N = rcNights(s), t = rcNight(Date.now()), open = s.bets.filter(b => b.status === "open");
  if (!N.length && !open.length) return "";
  const cur = N.find(n => n.k === t) || N[0], live = open.filter(b => rcNight(Date.now()) === t);
  const wk = N.filter(n => n.k >= rcNight(Date.now() - 6 * 864e5)), all = N;
  const sum = arr => arr.reduce((a, n) => ({w: a.w + n.w, l: a.l + n.l, p: a.p + n.p, net: a.net + n.net, risk: a.risk + n.risk}), {w: 0, l: 0, p: 0, net: 0, risk: 0});
  const W7 = sum(wk), AL = sum(all), u = rcShowU(s);
  const max = Math.max(1, ...wk.map(n => Math.abs(n.net)));
  return `<section class="rc-card" data-rc="1">
    <div class="rc-top"><div><span class="rc-k">${cur ? rcLabel(cur.k) : "Tonight"}</span><div class="rc-rec">${cur ? rcRecord(cur) : "0–0"}</div></div>
      <button class="rc-net ${cur && cur.net > 0 ? "up" : cur && cur.net < 0 ? "dn" : ""}" data-rcflip="1"><b>${cur ? rcFmt(cur.net, s) : rcFmt(0, s)}</b><i>${cur ? rcFmt(cur.net, s, !u) : ""}</i></button></div>
    ${open.length ? `<div class="rc-open"><span class="livedot"></span>${open.length} still running · ${rcFmt(open.reduce((a, b) => a + b.stake, 0), s).replace("+", "")} at risk</div>` : ""}
    ${compact ? "" : `<div class="rc-bars">${wk.slice().reverse().map(n => `<div class="rc-bar ${n.net >= 0 ? "up" : "dn"}"><i style="--h:${Math.max(6, Math.round(100 * Math.abs(n.net) / max))}%"></i><span>${rcLabel(n.k).replace("Last night", "Yest").replace("Tonight", "Tdy").split(",")[0].slice(0, 4)}</span></div>`).join("")}</div>`}
    <div class="rc-sum"><div><span>Last 7</span><b>${rcRecord(W7)}</b><em class="${W7.net >= 0 ? "pos" : "neg"}">${rcFmt(W7.net, s)}</em></div>
      <div><span>All-time</span><b>${rcRecord(AL)}</b><em class="${AL.net >= 0 ? "pos" : "neg"}">${rcFmt(AL.net, s)}</em></div>
      <div><span>ROI</span><b class="${AL.net >= 0 ? "pos" : "neg"}">${AL.risk ? (AL.net >= 0 ? "+" : "") + (100 * AL.net / AL.risk).toFixed(1) + "%" : "–"}</b><em>1u = ${mbShort(rcUnit(s))}</em></div></div>
    <div class="rc-acts"><button data-rcopen="1">Full recap ›</button><button data-rcshare="1">Share recap</button></div></section>`;
}
// full recap sheet: every night with its tickets
function rcOpen() {
  const s = mbLoad(), N = rcNights(s).slice(0, 30), sh = document.getElementById("sheet");
  sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>
    <div class="sh-t">Recap</div>
    <div class="rc-unit"><span>Show in</span><div class="gseg c"><button class="${rcShowU(s) ? "" : "on"}" data-rcu="0">Dollars</button><button class="${rcShowU(s) ? "on" : ""}" data-rcu="1">Units</button></div>
      <label>1u = $<input id="rcsize" inputmode="decimal" value="${rcUnit(s)}"></label></div>
    ${N.length ? N.map(n => `<div class="rc-night"><div class="rc-nh"><b>${rcLabel(n.k)}</b><span>${rcRecord(n)}</span><em class="${n.net >= 0 ? "pos" : "neg"}">${rcFmt(n.net, s)}</em></div>
      ${n.bets.map(b => { const pl = mbProfit(b), st = b.status === "push" ? "p" : pl > 0 ? "w" : "l";
        return `<div class="rc-b ${st}" data-tk="${esc(b.id)}"><span class="rc-r">${st === "w" ? "W" : st === "l" ? "L" : "P"}</span><span class="rc-bt"><b>${esc(b.kind === "parlay" ? `${b.legs.length}-leg parlay` : b.label)}</b><i>${mbSign(b.odds)} · ${rcFmt(b.stake, s).replace("+", "")}</i></span><em class="${pl >= 0 ? "pos" : "neg"}">${rcFmt(pl, s)}</em></div>`; }).join("")}</div>`).join("")
      : `<div class="note">No settled bets yet.</div>`}`;
  document.getElementById("shx").onclick = () => { closeSheet(); MB_RENDER && MB_RENDER(); };
  sh.querySelectorAll("[data-rcu]").forEach(b => b.onclick = () => { const s2 = mbLoad(); s2.showUnits = b.dataset.rcu === "1"; mbSave(s2); mbHaptic(); rcOpen(); });
  document.getElementById("rcsize").onchange = e => { const v = Number(e.target.value.replace(/[^0-9.]/g, "")); if (v > 0) { const s2 = mbLoad(); s2.unitSize = v; mbSave(s2); } rcOpen(); };
  sh.querySelectorAll("[data-tk]").forEach(r => r.onclick = () => mbOpenTicket(r.dataset.tk));
  document.getElementById("scrim").classList.add("open"); sh.classList.add("open");
}
// a shareable recap image: tonight's record and result plus each ticket (units by default, like the apps people post)
async function rcShare() {
  const s = mbLoad(), N = rcNights(s), n = N.find(x => x.k === rcNight(Date.now())) || N[0];
  if (!n) { mbToast(`<div class="tsub">Nothing settled yet</div>`); return; }
  try { await Promise.all(["800 40px 'Inter Tight'", "600 28px 'Inter'", "italic 900 40px 'Barlow Condensed'"].map(f => document.fonts.load(f))); } catch (e) {}
  const W = 1080, P = 64, rows = n.bets.slice(0, 12), H = 520 + rows.length * 96 + 110, u = rcShowU(s);
  const F = (w, px, fam) => `${w} ${px}px ${fam === "c" ? "'Barlow Condensed'" : fam === "b" ? "'Inter'" : "'Inter Tight'"}, system-ui, sans-serif`;
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H; const x = cv.getContext("2d");
  const g = x.createLinearGradient(0, 0, W, H); g.addColorStop(0, "#0d0f0b"); g.addColorStop(1, "#050605"); x.fillStyle = g; x.fillRect(0, 0, W, H);
  const up = n.net >= 0, glow = x.createRadialGradient(W / 2, 260, 0, W / 2, 260, 620); glow.addColorStop(0, up ? "rgba(198,255,46,.2)" : "rgba(255,90,90,.16)"); glow.addColorStop(1, "rgba(0,0,0,0)"); x.fillStyle = glow; x.fillRect(0, 0, W, H);
  const mark = await new Promise(r => { const im = new Image(); im.onload = () => r(im); im.onerror = () => r(null); im.src = "bmark.png"; });
  x.textBaseline = "middle"; if (mark) x.drawImage(mark, P, 70, 54 * mark.width / mark.height, 54);
  x.fillStyle = "#fff"; x.font = F("italic 900", 50, "c"); x.fillText("BLITZED", P + (mark ? 54 * mark.width / mark.height + 18 : 0), 99);
  x.fillStyle = "rgba(255,255,255,.55)"; x.font = F(600, 26, "b"); x.textAlign = "right"; x.fillText(rcLabel(n.k) === "Tonight" ? new Date().toLocaleDateString("en-US", {weekday: "long", month: "short", day: "numeric"}) : rcLabel(n.k), W - P, 99);
  x.textAlign = "center"; x.fillStyle = "#c6ff2e"; x.font = F(800, 22, "b"); x.letterSpacing = "6px"; x.fillText("NIGHT RECAP", W / 2, 200); x.letterSpacing = "0px";
  x.fillStyle = "#fff"; x.font = F(800, 120); x.fillText(rcRecord(n), W / 2, 300);
  x.fillStyle = up ? "#c6ff2e" : "#ff6b6b"; x.font = F(800, 64); x.fillText(rcFmt(n.net, s, true), W / 2, 400);
  x.fillStyle = "rgba(255,255,255,.45)"; x.font = F(600, 26, "b"); x.fillText(`${n.risk ? (up ? "+" : "") + (100 * n.net / n.risk).toFixed(1) + "% ROI · " : ""}1u = ${mbShort(rcUnit(s))}`, W / 2, 452); x.textAlign = "left";
  let y = 520;
  for (const b of rows) { const pl = mbProfit(b), st = b.status === "push" ? "P" : pl > 0 ? "W" : "L", c = st === "W" ? "#3ee08f" : st === "L" ? "#ff6b6b" : "#9aa";
    x.fillStyle = "rgba(255,255,255,.045)"; x.beginPath(); x.roundRect ? x.roundRect(P, y, W - 2 * P, 80, 20) : x.rect(P, y, W - 2 * P, 80); x.fill();
    x.fillStyle = c; x.beginPath(); x.arc(P + 44, y + 40, 22, 0, 7); x.fill(); x.fillStyle = "#050605"; x.font = F(800, 24); x.textAlign = "center"; x.fillText(st, P + 44, y + 41); x.textAlign = "left";
    let t = b.kind === "parlay" ? `${b.legs.length}-leg parlay` : b.label; x.font = F(700, 30); x.fillStyle = "#fff"; while (x.measureText(t).width > 560 && t.length > 4) t = t.slice(0, -2); if (t !== (b.kind === "parlay" ? `${b.legs.length}-leg parlay` : b.label)) t += "…";
    x.fillText(t, P + 86, y + 30); x.fillStyle = "rgba(255,255,255,.45)"; x.font = F(500, 22, "b"); x.fillText(`${mbSign(b.odds)} · ${rcFmt(b.stake, s, true).replace("+", "")}`, P + 86, y + 58);
    x.fillStyle = pl >= 0 ? "#3ee08f" : "#ff6b6b"; x.font = F(800, 30); x.textAlign = "right"; x.fillText(rcFmt(pl, s, true), W - P - 28, y + 40); x.textAlign = "left";
    y += 96; }
  x.fillStyle = "rgba(255,255,255,.3)"; x.font = F(600, 22, "b"); x.fillText(u ? "" : `${rcFmt(n.net, s, false)} on the night`, P, H - 60);
  x.fillStyle = "#c6ff2e"; x.font = F("italic 900", 30, "c"); x.textAlign = "right"; x.fillText("BLITZED", W - P, H - 60);
  cv.toBlob(blob => { if (!blob) return; const url = URL.createObjectURL(blob), file = new File([blob], `blitzed-recap-${n.k}.png`, {type: "image/png"});
    const canShare = navigator.canShare && navigator.canShare({files: [file]}), d = document.createElement("div"); d.className = "shx act";
    d.innerHTML = `<div class="shx-in"><img src="${url}" alt="Night recap"><div class="shx-b">${canShare ? `<button class="shx-go" data-x="share">Share</button>` : ""}<a class="shx-go ${canShare ? "alt" : ""}" href="${url}" download="${file.name}">Save image</a><button class="shx-go alt" data-x="close">Close</button></div></div>`;
    document.body.appendChild(d); requestAnimationFrame(() => d.classList.add("in")); mbHaptic("success");
    const close = () => { d.classList.remove("in"); setTimeout(() => { d.remove(); URL.revokeObjectURL(url); }, 250); };
    d.onclick = e => { if (e.target === d || e.target.dataset.x === "close") close(); };
    const sb = d.querySelector('[data-x="share"]'); if (sb) sb.onclick = () => navigator.share({files: [file], title: "My night on Blitzed"}).catch(() => {});
  }, "image/png");
}
function rcAfterRender() {
  try {
    const hx = document.querySelector("#view .hx2");
    if (hx && !hx.querySelector(".rc-card")) { const h = rcCardHtml(true); if (h) { const d = document.createElement("div"); d.innerHTML = h; const w = hx.querySelector(".w-card"); w ? w.after(d.firstElementChild) : hx.prepend(d.firstElementChild); } }
    const sv = document.querySelector("body.tab-check #view");
    if (sv && typeof MB_BTAB !== "undefined" && MB_BTAB === "settled" && typeof MB_VIEW !== "undefined" && MB_VIEW === "bets" && !sv.querySelector(".rc-card")) { const h = rcCardHtml(false); if (h) { const d = document.createElement("div"); d.innerHTML = h; const tabs = sv.querySelector(".mbtabs"); tabs ? tabs.after(d.firstElementChild) : sv.prepend(d.firstElementChild); } }
  } catch (e) {}
  document.querySelectorAll("[data-rcflip]").forEach(b => b.onclick = e => { e.stopPropagation(); const s = mbLoad(); s.showUnits = !s.showUnits; mbSave(s); mbHaptic(); document.querySelectorAll(".rc-card").forEach(c => c.remove()); rcAfterRender(); });
  document.querySelectorAll("[data-rcopen]").forEach(b => b.onclick = () => { mbHaptic(); rcOpen(); });
  document.querySelectorAll("[data-rcshare]").forEach(b => b.onclick = () => { mbHaptic(); rcShare(); });
}
