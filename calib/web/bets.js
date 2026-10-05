// ---------- 📝 PAPER BETS (shared by the NHL and NFL pages) ----------
// Bets live in this browser (localStorage, same origin for both sports, so one bankroll). Nothing is sent anywhere.
// A bet: {id, ts, sport, kind: "single"|"parlay", label, odds (American), stake, legs: [{label, sub, gid, start, key, p}],
//         status: "open"|"won"|"lost"|"push", result_ts, manual}
// leg.key tells the page how to grade it: {t: "game", m, s, l} or {t: "prop", pid, name, team, mk, l, dir}.
const MB_KEY = "mm_paper_v1";
let MB_VIEW = "bets", MB_SPORT = "all", MB_MSG = "";
function mbLoad() {
  try { const s = JSON.parse(localStorage.getItem(MB_KEY) || "null"); if (s && Array.isArray(s.bets)) return Object.assign({start: 1000, unit: 10}, s); } catch (e) {}
  return {start: 1000, unit: 10, bets: []};
}
function mbSave(s) { try { localStorage.setItem(MB_KEY, JSON.stringify(s)); return true; } catch (e) { return false; } }
const mbDec = a => a > 0 ? 1 + a / 100 : 1 + 100 / -a;
const mbAm = d => d >= 2 ? Math.round(100 * (d - 1)) : Math.round(-100 / (d - 1));
const mbSign = a => (a > 0 ? "+" : "") + Math.round(a);
const mbMoney = x => (x < 0 ? "−$" : "$") + Math.abs(x).toFixed(2);
function mbProfit(b) {
  if (b.status === "won") return b.stake * (mbDec(b.odds) - 1);
  if (b.status === "lost") return -b.stake;
  return 0;
}
function mbAdd(bet) {
  const s = mbLoad();
  bet.id = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  bet.ts = new Date().toISOString(); bet.status = "open";
  s.bets.push(bet); s.unit = bet.stake;
  return mbSave(s) ? bet : null;
}
function mbUpdate(id, f) { const s = mbLoad(), b = s.bets.find(x => x.id === id); if (b) { f(b, s); mbSave(s); } }

// stake row inside a bet sheet. getOdds() -> American odds typed in the sheet (or NaN); getBet() -> bet without stake/odds
function mbTrackHtml(defOdds) {
  const s = mbLoad();
  return `<div class="mbt"><div class="sh-s" style="margin:12px 0 6px">📝 Paper bet</div>
    <div class="mbrow"><span class="mbcur">$</span><input class="odds mbstake" id="mbstake" inputmode="decimal" value="${s.unit}">
    <button class="mbgo" id="mbgo">Place at <b id="mbodds">${isFinite(defOdds) ? mbSign(defOdds) : "–"}</b></button></div>
    <div class="hint" id="mbmsg">Uses the odds above (or the ${isFinite(defOdds) ? "fair" : ""} price if you leave them blank). Track it under 🎟️ Bets.</div></div>`;
}
function mbWireTrack(getOdds, defOdds, getBet) {
  const go = document.getElementById("mbgo"); if (!go) return;
  const cur = () => { const o = getOdds(); return isFinite(o) && Math.abs(o) >= 100 ? o : defOdds; };
  const odds = document.getElementById("odds");
  const show = () => setTimeout(() => { const o = cur(), el = document.getElementById("mbodds"); if (el) el.textContent = isFinite(o) ? mbSign(o) : "–"; }, 0);
  if (odds) odds.addEventListener("input", show);
  document.querySelectorAll("#sheet [data-s], #sheet [data-ms]").forEach(x => x.addEventListener("click", show));
  show();
  go.onclick = () => {
    const stake = Number(String(document.getElementById("mbstake").value).replace(/[^0-9.]/g, "")), o = cur();
    if (!(stake > 0) || !isFinite(o)) { document.getElementById("mbmsg").textContent = "Enter a stake and odds first."; return; }
    const bet = getBet();
    if (bet.legs.some(l => l.start && new Date(l.start).getTime() <= Date.now())) {
      document.getElementById("mbmsg").textContent = "That game has already started: paper bets lock at puck drop / kickoff."; return; }
    const b = mbAdd(Object.assign(bet, {odds: Math.round(o), stake}));
    document.getElementById("mbmsg").innerHTML = b ? `✅ Placed ${mbMoney(stake)} at ${mbSign(o)}. To win ${mbMoney(stake * (mbDec(o) - 1))}.`
      : "Couldn't save (private browsing blocks storage).";
    go.disabled = !!b;
  };
}
// a standalone slip (parlays): shows legs, lets you set odds and stake
function mbOpenSlip(bet, defOdds, close) {
  const sh = document.getElementById("sheet"), s = mbLoad();
  sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>
    <div class="sh-t">📝 ${esc(bet.label)}</div><div class="sh-s">${bet.legs.length} legs · paper bet</div>
    <div class="mbslip">${bet.legs.map((l, i) => `<div class="mbleg"><span class="lg-n">${i + 1}</span><span><b>${esc(l.label)}</b><i>${esc(l.sub || "")}</i></span></div>`).join("")}</div>
    <div class="sh-s" style="margin:10px 0 6px">Odds you got (American)</div>
    <div class="oddsrow"><div class="sign"><button data-ms="1" class="${defOdds > 0 ? "on" : ""}">+</button><button data-ms="-1" class="${defOdds < 0 ? "on" : ""}">−</button></div>
      <input class="odds" id="odds" inputmode="numeric" pattern="[0-9]*" value="${Math.abs(Math.round(defOdds))}"></div>
    ${mbTrackHtml(defOdds)}`;
  let sign = defOdds < 0 ? -1 : 1;
  const get = () => { const v = Number(String(document.getElementById("odds").value).replace(/[^0-9]/g, "")); return v ? sign * v : NaN; };
  sh.querySelectorAll("[data-ms]").forEach(x => x.onclick = () => { sign = Number(x.dataset.ms); sh.querySelectorAll("[data-ms]").forEach(y => y.classList.toggle("on", y === x));
    document.getElementById("odds").dispatchEvent(new Event("input")); });
  document.getElementById("shx").onclick = close;
  mbWireTrack(get, defOdds, () => bet);
  document.getElementById("scrim").classList.add("open"); sh.classList.add("open");
}

// grading: the page passes gradeLeg(leg) -> true | false | "push" | undefined (not decided / can't tell)
function mbAutoSettle(sport, gradeLeg) {
  const s = mbLoad(); let changed = false;
  for (const b of s.bets) {
    if (b.status !== "open" || b.sport !== sport || b.manual) continue;
    const r = b.legs.map(l => { try { return gradeLeg(l); } catch (e) { return undefined; } });
    b.legs.forEach((l, i) => { if (r[i] !== undefined) l.res = r[i]; });
    let st;
    if (r.some(x => x === false)) st = "lost";
    else if (r.every(x => x !== undefined)) {
      if (r.every(x => x === "push")) st = "push";
      else { st = "won"; if (b.kind === "parlay" && r.some(x => x === "push")) {   // pushed legs drop out of the parlay
        const keep = b.legs.filter((l, i) => r[i] !== "push"); const d = keep.reduce((a, l) => a * (l.dec || mbDec(l.odds || -110)), 1);
        if (keep.every(l => l.dec || l.odds)) b.odds = mbAm(d); } }
    }
    if (st) { b.status = st; b.result_ts = new Date().toISOString(); changed = true; }
  }
  if (changed) mbSave(s);
}

function mbSummary(bets) {
  const done = bets.filter(b => b.status !== "open"), staked = done.filter(b => b.status !== "push").reduce((a, b) => a + b.stake, 0);
  const pl = done.reduce((a, b) => a + mbProfit(b), 0);
  return {w: done.filter(b => b.status === "won").length, l: done.filter(b => b.status === "lost").length, p: done.filter(b => b.status === "push").length,
          pl, roi: staked ? pl / staked : 0, open: bets.filter(b => b.status === "open"), risk: bets.filter(b => b.status === "open").reduce((a, b) => a + b.stake, 0)};
}
function mbCard(b) {
  const st = {open: ["⏳", "Open"], won: ["✅", "Won"], lost: ["❌", "Lost"], push: ["➖", "Push"]}[b.status];
  const toWin = b.stake * (mbDec(b.odds) - 1), legRes = l => l.res === true ? "✅" : l.res === false ? "❌" : l.res === "push" ? "➖" : "·";
  const legs = b.kind === "parlay" ? `<div class="mbl">${b.legs.map(l => `<div>${legRes(l)} ${esc(l.label)}</div>`).join("")}</div>` : (b.legs[0] && b.legs[0].sub ? `<div class="mbsub">${esc(b.legs[0].sub)}</div>` : "");
  const when = new Date(b.ts).toLocaleDateString("en-US", {month: "short", day: "numeric"});
  return `<div class="mbc ${b.status}"><div class="mbh"><span class="mbtag">${b.sport}</span><b>${esc(b.label)}</b><span class="mbst">${st[0]} ${st[1]}</span></div>${legs}
    <div class="mbf"><span>${when} · ${mbMoney(b.stake)} at ${mbSign(b.odds)}</span><span class="${b.status === "won" ? "pos" : b.status === "lost" ? "neg" : ""}">${b.status === "open" ? "to win " + mbMoney(toWin) : b.status === "push" ? "refunded" : (b.status === "won" ? "+" : "") + mbMoney(mbProfit(b))}</span></div>
    ${b.status === "open" ? `<div class="mbx"><button data-mbs="${b.id}|won">Won</button><button data-mbs="${b.id}|lost">Lost</button><button data-mbs="${b.id}|push">Push</button><button data-mbd="${b.id}" class="del">Delete</button></div>`
      : `<div class="mbx"><button data-mbs="${b.id}|open">Reopen</button><button data-mbd="${b.id}" class="del">Delete</button></div>`}</div>`;
}
function mbChart(bets, start) {
  const done = bets.filter(b => b.status !== "open").sort((a, b) => (a.result_ts || a.ts).localeCompare(b.result_ts || b.ts));
  if (done.length < 2) return "";
  let run = 0; const pts = [{x: 0, y: 0, t: "Start: $0"}];
  done.forEach((b, i) => { run += mbProfit(b); pts.push({x: i + 1, y: run, t: `${b.label}: ${(run >= 0 ? "+" : "") + mbMoney(run)}`}); });
  return `<div class="card mbchart">${mhLine([{name: "Profit", color: run >= 0 ? MH_C2 : "#c0504d", pts}], {title: "Profit ($) after each settled bet", w: 320, h: 120, ref: "zero", yd: 0, L: 36, xl: ["first", "latest"]})}</div>`;
}
function mbView() {
  const s = mbLoad(), bets = s.bets.filter(b => MB_SPORT === "all" || b.sport === MB_SPORT), S = mbSummary(bets);
  const chips = [["all", "All"], ["NHL", "🏒 NHL"], ["NFL", "🏈 NFL"]].map(([k, n]) => `<button class="chip ${MB_SPORT === k ? "on" : ""}" data-mbsp="${k}">${n}</button>`).join("");
  const open = [...S.open].sort((a, b) => b.ts.localeCompare(a.ts)), done = bets.filter(b => b.status !== "open").sort((a, b) => (b.result_ts || b.ts).localeCompare(a.result_ts || a.ts));
  return `<div class="strip" style="padding:0 0 8px">${chips}</div>
    <div class="card mbsum"><div class="mbtiles">
      <div class="big"><span>Bankroll</span><b>${mbMoney(s.start + S.pl)}</b></div>
      <div><span>Profit</span><b class="${S.pl > 0 ? "pos" : S.pl < 0 ? "neg" : ""}">${(S.pl > 0 ? "+" : "") + mbMoney(S.pl)}</b></div>
      <div><span>Record</span><b>${S.w}-${S.l}${S.p ? "-" + S.p : ""}</b></div>
      <div><span>ROI</span><b>${(S.roi >= 0 ? "+" : "") + (100 * S.roi).toFixed(1)}%</b></div></div>
      <div class="hint">${S.open.length} open · ${mbMoney(S.risk)} at risk · start ${mbMoney(s.start)}. Paper money only, saved on this device.</div>${MB_MSG ? `<div class="hint"><b>${esc(MB_MSG)}</b></div>` : ""}</div>
    ${mbChart(bets, s.start)}
    <div class="sec mbsec">Open bets</div>${open.length ? open.map(mbCard).join("") : `<div class="note">No open bets. Tap any price, prop or parlay and use 📝 Paper bet.</div>`}
    ${done.length ? `<div class="sec mbsec">Settled</div>${done.slice(0, 40).map(mbCard).join("")}` : ""}
    <details class="card mbset"><summary>⚙️ Bankroll &amp; backup</summary>
      <label class="f">Starting bankroll ($)</label><input id="mbstart" inputmode="decimal" value="${s.start}">
      <div class="mbx" style="margin-top:10px"><button id="mbexp">Copy backup</button><button id="mbimp">Restore backup</button><button id="mbreset" class="del">Reset all</button></div>
      <div class="hint">Bets are stored in this browser only. On iPhone, the home-screen app and Safari keep separate copies: use Copy backup / Restore backup to move them.</div></details>`;
}
function mbWire(render) {
  document.querySelectorAll("[data-mbsp]").forEach(b => b.onclick = () => { MB_SPORT = b.dataset.mbsp; render(); });
  document.querySelectorAll("[data-mbs]").forEach(b => b.onclick = () => { const [id, st] = b.dataset.mbs.split("|");
    mbUpdate(id, x => { x.status = st; x.manual = st !== "open"; x.result_ts = st === "open" ? null : new Date().toISOString(); }); render(); });
  document.querySelectorAll("[data-mbd]").forEach(b => b.onclick = () => { if (!confirm("Delete this bet?")) return;
    const s = mbLoad(); s.bets = s.bets.filter(x => x.id !== b.dataset.mbd); mbSave(s); render(); });
  const st = document.getElementById("mbstart");
  if (st) st.onchange = () => { const v = Number(st.value.replace(/[^0-9.]/g, "")); if (v > 0) { const s = mbLoad(); s.start = v; mbSave(s); render(); } };
  const ex = document.getElementById("mbexp");
  if (ex) ex.onclick = async () => { const txt = JSON.stringify(mbLoad());
    try { await navigator.clipboard.writeText(txt); MB_MSG = "Backup copied. Paste it somewhere safe (Notes works)."; }
    catch (e) { prompt("Copy this backup:", txt); MB_MSG = ""; } render(); };
  const im = document.getElementById("mbimp");
  if (im) im.onclick = () => { const txt = prompt("Paste a backup (replaces the bets on this device):"); if (!txt) return;
    try { const s = JSON.parse(txt); if (!Array.isArray(s.bets)) throw 0; mbSave(s); MB_MSG = `Restored ${s.bets.length} bets.`; } catch (e) { MB_MSG = "That backup didn't read. Copy it again."; } render(); };
  const rs = document.getElementById("mbreset");
  if (rs) rs.onclick = () => { if (confirm("Delete every paper bet and reset the bankroll?")) { mbSave({start: mbLoad().start, unit: 10, bets: []}); MB_MSG = "Reset."; render(); } };
}
