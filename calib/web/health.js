// ---------- MODEL HEALTH + RECALIBRATE (calib/) ----------
// H = data.calib (built by calib/health.py). Charts are small inline SVG: one y-axis each, 2px lines,
// 8px markers with hover titles, a gray dashed reference, legend + table view.
const MH_C1 = "#3a6ea5", MH_C2 = "#2e8b57", MH_REF = "#9aa5ad";
let MH_SEG = "home_away";
const mhF = (v, d = 2) => v == null || !isFinite(v) ? "–" : Number(v).toFixed(d);
const mhS = (v, d = 2) => v == null || !isFinite(v) ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d);
function mhScale(vals, pad = 0.08) { let lo = Math.min(...vals), hi = Math.max(...vals); if (lo === hi) { lo -= 1; hi += 1; } const p = (hi - lo) * pad; return [lo - p, hi + p]; }
function mhLine(series, o) {
  // series: [{name, color, pts:[{x, y, t}]}], o: {ref: "diag"|"zero"|null, w, h, xs: [labels]?}
  const W = o.w || 160, Hh = o.h || 92, L = 22, B = 12, T = 4, R = 4;
  const xs = series.flatMap(s => s.pts.map(p => p.x)), ys = series.flatMap(s => s.pts.map(p => p.y)).concat(o.ref === "zero" ? [0] : []);
  if (!xs.length) return `<div class="ct">${esc(o.title)}</div><div class="hint">Not enough graded predictions yet.</div>`;
  let [x0, x1] = o.ref === "diag" ? mhScale(xs.concat(ys)) : mhScale(xs, 0.02), [y0, y1] = o.ref === "diag" ? [x0, x1] : mhScale(ys);
  const X = v => L + (W - L - R) * (v - x0) / (x1 - x0), Y = v => T + (Hh - T - B) * (1 - (v - y0) / (y1 - y0));
  let g = `<line x1="${L}" y1="${Hh - B}" x2="${W - R}" y2="${Hh - B}" stroke="#d8d2c4" stroke-width="1"/>`;
  if (o.ref === "diag") g += `<line x1="${X(x0)}" y1="${Y(x0)}" x2="${X(x1)}" y2="${Y(x1)}" stroke="${MH_REF}" stroke-width="1.5" stroke-dasharray="3 3"/>`;
  if (o.ref === "zero" && y0 < 0 && y1 > 0) g += `<line x1="${L}" y1="${Y(0)}" x2="${W - R}" y2="${Y(0)}" stroke="${MH_REF}" stroke-width="1.5" stroke-dasharray="3 3"/>`;
  g += `<text class="ax" x="${L - 3}" y="${Y(y1) + 6}" text-anchor="end">${mhF(y1, o.yd ?? 1)}</text><text class="ax" x="${L - 3}" y="${Y(y0)}" text-anchor="end">${mhF(y0, o.yd ?? 1)}</text>`;
  if (o.xl) g += `<text class="ax" x="${L}" y="${Hh}">${esc(o.xl[0])}</text><text class="ax" x="${W - R}" y="${Hh}" text-anchor="end">${esc(o.xl[1])}</text>`;
  for (const s of series) {
    if (s.pts.length > 1) g += `<polyline fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" points="${s.pts.map(p => `${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(" ")}"/>`;
    if (s.dots !== false) for (const p of s.pts) g += `<circle cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="4" fill="${s.color}" stroke="#fff" stroke-width="2"><title>${esc(p.t || `${s.name}: ${mhF(p.y)}`)}</title></circle>`;
  }
  const lg = series.length > 1 || o.refName ? `<div class="lg">${series.map(s => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join("")}${o.refName ? `<span><i style="background:${MH_REF}"></i>${esc(o.refName)}</span>` : ""}</div>` : "";
  const tbl = `<details><summary>table</summary><table>${series.map(s => s.pts.map(p => `<tr><td>${esc(s.name)}</td><td>${esc(p.t || "")}</td></tr>`).join("")).join("")}</table></details>`;
  return `<div class="ct">${esc(o.title)}</div><svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="${esc(o.title)}">${g}</svg>${lg}${tbl}`;
}
function mhBars(groups, o) {
  // groups: [{label, a, b}] two series side by side (a = original, b = recalibrated)
  const W = 160, Hh = 92, L = 22, B = 12, T = 4;
  const vals = groups.flatMap(g => [g.a, g.b]).filter(v => v != null);
  if (!vals.length) return `<div class="ct">${esc(o.title)}</div><div class="hint">Shows after the first recalibration run.</div>`;
  const hi = Math.max(...vals) * 1.1, lo = 0, Y = v => T + (Hh - T - B) * (1 - (v - lo) / (hi - lo));
  const gw = (W - L) / groups.length, bw = Math.min(14, gw / 2 - 3);
  let g = `<line x1="${L}" y1="${Hh - B}" x2="${W}" y2="${Hh - B}" stroke="#d8d2c4" stroke-width="1"/><text class="ax" x="${L - 3}" y="${Y(hi) + 6}" text-anchor="end">${mhF(hi, 1)}</text>`;
  groups.forEach((gr, i) => {
    const cx = L + gw * i + gw / 2;
    [[gr.a, MH_C1, -1, o.na], [gr.b, MH_C2, 1, o.nb]].forEach(([v, c, s, nm]) => {
      if (v == null) return;
      const x = s < 0 ? cx - bw - 1 : cx + 1, y = Y(v), h = Hh - B - y;
      g += `<path d="M${x},${Hh - B} v${-(h - 4)} q0,-4 4,-4 h${bw - 8} q4,0 4,4 v${h - 4} z" fill="${c}"><title>${esc(gr.label)} · ${esc(nm)}: ${mhF(v, 3)}</title></path>`;
    });
    g += `<text class="ax" x="${cx}" y="${Hh}" text-anchor="middle">${esc(gr.label)}</text>`;
  });
  return `<div class="ct">${esc(o.title)}</div><svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="${esc(o.title)}">${g}</svg>
    <div class="lg"><span><i style="background:${MH_C1}"></i>${esc(o.na)}</span><span><i style="background:${MH_C2}"></i>${esc(o.nb)}</span></div>
    <details><summary>table</summary><table>${groups.map(gr => `<tr><td>${esc(gr.label)}</td><td>${mhF(gr.a, 3)}</td><td>${mhF(gr.b, 3)}</td></tr>`).join("")}</table></details>`;
}
function healthHtml(H, sport, repo) {
  if (!H) return `<div class="card"><div class="mh-h">🩺 Model health</div><div class="hint">The prediction database is being built. Health shows after the next run.</div></div>`;
  const prim = (H.types || []).find(t => t.home_away) || (H.types || [])[0];
  const W = prim ? prim.windows : {}, all = W.all || {}, cal = H.calibration || {};
  const n = (H.counts || {}).predictions || 0;
  const tile = (k, v, s) => `<div class="mh-tile"><div class="k">${k}</div><div class="n">${v}</div><div class="s">${s || ""}</div></div>`;
  const unit = prim ? prim.unit : "";
  const win = [["Last 25", "last25"], ["Last 50", "last50"], ["Last 100", "last100"], ["Season", "season"], ["All", "all"]];
  const wt = `<table class="mh-t"><tr><th>${esc(prim ? prim.label : "")}</th><th>n</th><th>MAE</th><th>RMSE</th><th>Bias</th></tr>
    ${win.map(([l, k]) => { const s = W[k] || {}; return s.n ? `<tr><td>${l}</td><td>${s.n}</td><td><b>${mhF(s.mae)}</b></td><td>${mhF(s.rmse)}</td><td>${mhS(s.bias)}</td></tr>` : ""; }).join("")}</table>`;
  const biases = (H.biases || []).length ? H.biases.map((b, i) => `<div class="mh-b"><span class="i">${i + 1}</span><span>${esc(b.text)}</span></div>`).join("")
    : `<div class="hint">No statistically meaningful biases right now (a segment needs ${(H.config || {}).min_segment || 25}+ graded predictions and must pass a false-discovery test).</div>`;
  const C = H.charts || {};
  const pva = mhLine([{name: "actual", color: MH_C2, pts: (C.pred_vs_actual || []).map(p => ({x: p.pred, y: p.actual, t: `projected ${mhF(p.pred)} → actual ${mhF(p.actual)} (${p.n})`}))}],
    {title: "Predicted vs actual", ref: "diag", refName: "perfect", xl: ["low projections", "high"]});
  const roll = C.rolling || [];
  const rm = mhLine([{name: "rolling MAE (50)", color: MH_C1, dots: false, pts: roll.map((p, i) => ({x: i, y: p.mae, t: `${p.date}: MAE ${mhF(p.mae)}`}))}],
    {title: "Rolling MAE (last 50)", xl: roll.length ? [roll[0].date.slice(0, 7), roll[roll.length - 1].date.slice(0, 7)] : null});
  const rb = mhLine([{name: "rolling bias (50)", color: MH_C1, dots: false, pts: roll.map((p, i) => ({x: i, y: p.bias, t: `${p.date}: bias ${mhS(p.bias)}`}))}],
    {title: "Rolling bias (last 50)", ref: "zero", refName: "no bias", xl: roll.length ? [roll[0].date.slice(0, 7), roll[roll.length - 1].date.slice(0, 7)] : null});
  const cf = mhLine([{name: "actual win rate", color: MH_C2, pts: (C.confidence || []).map(b => ({x: b.predicted, y: b.actual, t: `${b.bucket}: favourites won ${Math.round(100 * b.actual)}% (${b.n})`}))}],
    {title: "Confidence vs actual", ref: "diag", refName: "calibrated", yd: 2});
  const ovr = mhBars((C.orig_vs_recal || []).map(r => ({label: {last25: "L25", last50: "L50", last100: "L100", all: "All"}[r.window] || r.window, a: r.original, b: r.recalibrated})),
    {title: "Original vs recalibrated (MAE)", na: "published", nb: "recalibrated"});
  const em = C.error_by_month || [];
  const eot = mhLine([{name: "bias by month", color: MH_C1, pts: em.map((p, i) => ({x: i, y: p.bias, t: `${p.month}: bias ${mhS(p.bias)}, MAE ${mhF(p.mae)} (${p.n})`}))}],
    {title: "Error over time (monthly bias)", ref: "zero", refName: "no bias", xl: em.length ? [em[0].month, em[em.length - 1].month] : null});
  // breakdowns
  const segs = [["home_away", "Home / road"], ["confidence", "Confidence"], ["form", "Recent form"], ["teams", "Teams"], ["types", "All projections"], ["players", "Players"]];
  let rows = [];
  if (prim && MH_SEG !== "types" && MH_SEG !== "players") rows = (prim[MH_SEG] || []).slice(0, 10).map(r => [r.key, r.n, r.mae, r.bias]);
  if (MH_SEG === "types") rows = (H.types || []).map(t => [t.label, (t.windows.all || {}).n, (t.windows.all || {}).mae, (t.windows.all || {}).bias]);
  if (MH_SEG === "players") rows = (H.types || []).filter(t => t.players).flatMap(t => t.players.slice(0, 5).map(r => [`${r.key} · ${t.label}`, r.n, r.mae, r.bias]));
  const seg = `<div class="mh-seg">${segs.map(([k, l]) => `<button class="${MH_SEG === k ? "on" : ""}" data-mhs="${k}">${l}</button>`).join("")}</div>
    ${rows.length ? `<table class="mh-t"><tr><th></th><th>n</th><th>MAE</th><th>Bias</th></tr>${rows.map(r => `<tr><td>${esc(r[0])}</td><td>${r[1] ?? "–"}</td><td><b>${mhF(r[2])}</b></td><td>${mhS(r[3])}</td></tr>`).join("")}</table>` : `<div class="hint">Not enough graded predictions in this view yet.</div>`}`;
  // recalibration
  const last = H.last, act = H.active || {};
  const fmtD = t => t ? new Date(t).toLocaleString("en-US", {month: "short", day: "numeric", hour: "numeric", minute: "2-digit"}) : "";
  let rc = `<div class="hint">No recalibration has run yet. It runs automatically every Monday morning, or press the button.</div>`;
  if (last) {
    const ok = last.status === "applied", b = last.before || {}, a = last.after || {};
    rc = `<div class="mh-st ${ok ? "ok" : "no"}">${ok ? "RECALIBRATION COMPLETE" : last.status === "insufficient" ? "NOT ENOUGH DATA YET" : "RECALIBRATION REJECTED"}</div>
      <div class="hint" style="margin-top:2px">${sport} model v${esc(last.from_version)} ${ok ? `→ v${esc(last.version)}` : `stays (attempt v${esc(last.version)} not applied)`} · ${esc(fmtD(last.created_at))}</div>
      ${b.mae != null ? `<div class="mh-kv"><div><span>MAE (walk-forward)</span><b>${mhF(b.mae, 3)} → ${mhF(a.mae, 3)}</b></div><div><span>Bias</span><b>${mhS(b.bias)} → ${mhS(a.bias)}</b></div>
        <div><span>Sample</span><b>${(last.n || 0).toLocaleString()} ${esc(sport)} predictions</b></div><div><span>Held out</span><b>${((last.backtest || {}).all || {}).n || "–"}</b></div></div>` : ""}
      <div class="hint">${esc(last.reason || "")}</div>
      ${ok && last.changes ? `<div class="sec" style="margin-top:8px">Changes</div><ul class="mh-ch">${last.changes.map(c => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}`;
  }
  const url = `https://github.com/${repo || "Mbennett00/NHLModel"}/actions/workflows/recalibrate.yml`;
  const vers = (H.versions || []).slice(0, 6).map(v => `<div class="mh-v"><b>v${esc(v.version)}</b><span class="${esc(v.status)}">${esc(v.status)}</span><span>${esc(fmtD(v.created_at))}${v.n ? ` · ${v.n} obs` : ""}${v.before && v.after && v.before.mae != null ? ` · MAE ${mhF(v.before.mae, 3)}→${mhF(v.after.mae, 3)}` : ""}</span></div>`).join("");
  return `<div class="card"><div class="mh-h">🩺 Model health <span>v${esc(act.version || "1.0")} · ${n.toLocaleString()} predictions stored</span></div>
      <div class="mh-tiles">${tile("MAE", mhF(all.mae), unit)}${tile("RMSE", mhF(all.rmse), unit)}${tile("Bias", mhS(all.bias), all.bias > 0 ? "too high" : all.bias < 0 ? "too low" : "")}${tile("Calibration", cal.n ? mhF(cal.brier, 3) : "–", cal.n ? `Brier · ECE ${mhF(100 * cal.ece, 1)}pt` : "win prob")}</div>
      ${wt}</div>
    <div class="card"><div class="mh-h">Biggest current model biases</div>${biases}</div>
    <div class="card"><div class="mh-h">Calibration charts</div><div class="mh-charts">
      <div class="mh-c">${pva}</div><div class="mh-c">${cf}</div><div class="mh-c">${rm}</div><div class="mh-c">${rb}</div><div class="mh-c">${eot}</div><div class="mh-c">${ovr}</div></div></div>
    <div class="card"><div class="mh-h">Accuracy breakdown</div>${seg}</div>
    <div class="card mh-rc"><div class="mh-h">⚙️ Recalibrate model</div>${rc}
      <a class="mh-btn" href="${esc(url)}" target="_blank" rel="noopener">RECALIBRATE MODEL</a>
      <div class="hint">Opens the recalibration job on GitHub: press <b>Run workflow</b>. It pulls every graded prediction, tests adjustments in a walk-forward backtest, and applies a new version only if it beats the current model. The result shows here a few minutes later.</div>
      ${vers ? `<div class="sec" style="margin-top:10px">Model versions</div>${vers}` : ""}</div>`;
}
function wireHealth(render) {
  document.querySelectorAll("[data-mhs]").forEach(b => b.onclick = () => { MH_SEG = b.dataset.mhs; render(); });
}
