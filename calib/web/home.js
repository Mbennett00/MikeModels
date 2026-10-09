// ---------- 🏠 HOME + 🎖️ SEASON PASS + 💰 COINS ----------
// Shared by both pages. Page hooks (optional): mbQuickPicks() -> [{title, sub, tag, legs:[leg with odds]}],
// mbSportInfo() -> {sport: "NHL"|"NFL", line: "13 games tonight"}.

// ---- season pass: 30 levels, a prize at every one ----
const PASS_MAX = 30;
const RANKS = [[1, "Rookie", "🥉"], [5, "Pro", "🥈"], [10, "All-Star", "🥇"], [20, "MVP", "💎"], [30, "Hall of Fame", "👑"]];
const lvNeed = l => 80 + 20 * l;   // XP from level l to l + 1
function rankOf(l) { let r = RANKS[0]; for (const x of RANKS) if (l >= x[0]) r = x; return r; }
function mbLevel(xp) {
  let l = 1, rest = xp;
  while (l < PASS_MAX && rest >= lvNeed(l)) { rest -= lvNeed(l); l++; }
  return {lvl: l, into: rest, need: l < PASS_MAX ? lvNeed(l) : 0, pct: l < PASS_MAX ? rest / lvNeed(l) : 1, rank: rankOf(l)};
}
function passReward(l) {   // what reaching level l pays
  if (l % 5 === 0) return {cash: 20 * l, tok: l >= 20 ? "boost50" : "boost25", ins: true, big: true};
  return [{cash: 15 + 3 * l}, {tok: "boost25"}, {cash: 20 + 4 * l}, {tok: "ins"}][l % 4];
}
function passRewardText(r) {
  const out = [];
  if (r.cash) out.push(`$${r.cash}`);
  if (r.tok && r.tok.startsWith("boost")) out.push(`🚀 ${r.tok === "boost50" ? "+50%" : "+25%"} boost`);
  if (r.tok === "ins" || r.ins) out.push("🛡️ insurance");
  return out.join(" · ");
}
function passGrant(s, r) {
  if (r.cash) s.bonus = (s.bonus || 0) + r.cash;
  s.tokens = s.tokens || {};
  if (r.tok) s.tokens[r.tok] = (s.tokens[r.tok] || 0) + 1;
  if (r.ins) s.tokens.ins = (s.tokens.ins || 0) + 1;
}
function passCheck() {   // pays every level reached since the last check (first run: just records where you are)
  const s = mbLoad(), L = mbLevel(mbXP(s));
  if (s.lvlSeen == null) { s.lvlSeen = L.lvl; mbSave(s); return; }
  if (L.lvl <= s.lvlSeen) return;
  const got = [];
  for (let l = s.lvlSeen + 1; l <= L.lvl; l++) { const r = passReward(l); passGrant(s, r); got.push([l, r]); }
  s.lvlSeen = L.lvl; mbSave(s);
  const big = got.find(([, r]) => r.big), cash = got.reduce((a, [, r]) => a + (r.cash || 0), 0);
  if (big) setTimeout(() => funBigWin(cash, `LEVEL ${L.lvl} · ${L.rank[2]} ${L.rank[1].toUpperCase()}`, got.map(([, r]) => passRewardText(r)).join(" · ")), 600);
  else { mbToast(`<div class="tbig">⬆️ Level ${L.lvl}</div><div class="tsub">${got.map(([, r]) => passRewardText(r)).join(" · ")}</div>`, "win"); try { funBlip(); } catch (e) {} mbBurst(22, ["⭐", "✨"]); }
}
function passRing(L, size = 54) {
  const R = size / 2 - 4, C = 2 * Math.PI * R;
  return `<div class="pring" style="width:${size}px;height:${size}px"><svg viewBox="0 0 ${size} ${size}"><circle cx="${size / 2}" cy="${size / 2}" r="${R}" class="bg"/><circle cx="${size / 2}" cy="${size / 2}" r="${R}" class="fg" stroke-dasharray="${C * L.pct} ${C}" transform="rotate(-90 ${size / 2} ${size / 2})"/></svg><span><b>${L.lvl}</b><i>LVL</i></span></div>`;
}
function mbOpenPass() {
  const s = mbLoad(), L = mbLevel(mbXP(s)), sh = document.getElementById("sheet");
  const rows = Array.from({length: PASS_MAX}, (_, i) => i + 1).map(l => { const r = passReward(l), st = l <= L.lvl ? "got" : l === L.lvl + 1 ? "next" : "";
    return `<div class="pass-row ${st} ${r.big ? "big" : ""}" ${st === "next" ? 'id="passnext"' : ""}><span class="pr-l">${l}</span><span class="pr-r">${passRewardText(r)}</span><span class="pr-s">${st === "got" ? "✓" : st === "next" ? `${L.need - L.into} XP` : r.big ? rankOf(l)[0] === l ? rankOf(l)[2] : "⭐" : "🔒"}</span></div>`; }).join("");
  sh.innerHTML = `<div class="grab"></div><button class="iconbtn close" id="shx" aria-label="Close">✕</button>
    <div class="pass-top">${passRing(L, 84)}<div><div class="sh-t">Season Pass</div><div class="pass-rank">${L.rank[2]} ${L.rank[1]}</div>
      <div class="pass-xp">${L.lvl < PASS_MAX ? `${L.into} / ${L.need} XP to level ${L.lvl + 1}` : "Max level. Legend."}</div></div></div>
    <div class="pass-how"><span>+10 XP a bet</span><span>+25 a win</span><span>+15 a spin</span><span>missions</span></div>
    <div class="pass-list">${rows}</div>`;
  document.getElementById("shx").onclick = () => closeSheet();
  document.getElementById("scrim").classList.add("open"); sh.classList.add("open");
  setTimeout(() => { const n = document.getElementById("passnext"); if (n) n.scrollIntoView({block: "center"}); }, 60);
}

// ---- 💰 coins fly into the balance; the nav balance counts ----
function mbCoins(fromEl, n = 10) {
  const to = document.querySelector('#nav [data-k="check"]'); if (!fromEl || !to) return;
  const a = fromEl.getBoundingClientRect(), b = to.getBoundingClientRect();
  for (let i = 0; i < n; i++) {
    const c = document.createElement("i"); c.className = "coin"; c.textContent = "🪙"; document.body.appendChild(c);
    const x0 = a.left + a.width / 2 + (Math.random() - 0.5) * a.width * 0.6, y0 = a.top + a.height / 2, x1 = b.left + b.width / 2, y1 = b.top + b.height / 2;
    const mx = (x0 + x1) / 2 + (Math.random() - 0.5) * 120, my = Math.min(y0, y1) - 80 - Math.random() * 80;
    c.animate([{transform: `translate(${x0}px, ${y0}px) scale(.6)`, opacity: 0}, {transform: `translate(${mx}px, ${my}px) scale(1.15)`, opacity: 1, offset: .45},
      {transform: `translate(${x1}px, ${y1}px) scale(.5)`, opacity: .9}], {duration: 750 + Math.random() * 250, delay: i * 45, easing: "cubic-bezier(.4,0,.2,1)", fill: "forwards"})
      .onfinish = () => { c.remove(); to.classList.remove("bump"); void to.offsetWidth; to.classList.add("bump"); };
  }
}
let MB_NAV_SHOWN = null;
function mbNavBalance(el, value) {   // tween the nav balance from what it showed last
  const from = MB_NAV_SHOWN == null ? value : MB_NAV_SHOWN; MB_NAV_SHOWN = value;
  const sp = el && el.querySelector("span"); if (!sp) return;
  if (Math.abs(from - value) < 0.5) { sp.textContent = mbShort(value); return; }
  const t0 = performance.now(), dur = 900;
  const step = now => { const k = Math.min((now - t0) / dur, 1), e = 1 - Math.pow(1 - k, 3); sp.textContent = mbShort(from + (value - from) * e); if (k < 1) requestAnimationFrame(step); };
  sp.classList.add(value > from ? "up" : "down"); setTimeout(() => sp.classList.remove("up", "down"), 1100); requestAnimationFrame(step);
}

// ---- 🏠 home: the lobby ----
const IC = {   // small line icons for the home screen
  spin: '<circle cx="12" cy="12" r="8"/><path d="M12 4v8l5.5 5.5M12 12 6.5 17.5M12 12H4"/>',
  target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".8" fill="currentColor"/>',
  star: '<path d="m12 4 2.4 4.9 5.4.8-3.9 3.8.9 5.4L12 16.4 7.2 18.9l.9-5.4-3.9-3.8 5.4-.8z"/>',
  vs: '<path d="M5 6l4 12 4-12M15 17.5c.7.6 1.6 1 2.6 1 1.6 0 2.4-.9 2.4-2s-.9-1.6-2.4-2.1c-1.5-.5-2.4-1-2.4-2.1s.8-1.8 2.3-1.8c.9 0 1.7.3 2.3.8"/>',
  bolt: '<path d="M13 3 5 13.5h6L10 21l8-10.5h-6z"/>',
  chev: '<path d="m9 6 6 6-6 6"/>',
};
const ic = (k, cls = "") => `<svg class="hic ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${IC[k]}</svg>`;
function mbHomeHtml() {
  const s = mbLoad(), W = mbWallet(s), L = mbLevel(mbXP(s)), D0 = mbDaily(s), M = funMissions(s), mdone = M.filter(m => m.claimed).length;
  const h = new Date().getHours(), hi = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  const open = s.bets.filter(b => b.status === "open"), live = open.filter(mbIsLive);
  const done = s.bets.filter(b => b.status !== "open").sort((a, b) => (b.result_ts || b.ts).localeCompare(a.result_ts || a.ts)).slice(0, 12);
  const me = mbStats(s.bets);
  const picks = (() => { try { return typeof mbQuickPicks === "function" ? mbQuickPicks() || [] : []; } catch (e) { return []; } })();
  window.MB_QP = picks;
  const nxt = passRewardText(passReward(Math.min(L.lvl + 1, PASS_MAX))).split(" · ")[0];
  const run = (() => { try { return stkTrack(); } catch (e) { return null; } })();
  const act = (attr, icon, top, sub, cls = "") => `<button class="w-act ${cls}" ${attr}><span class="w-ai">${icon}</span><b>${top}</b><i>${sub}</i></button>`;
  const wallet = `<section class="w-card">
      <div class="w-top"><span class="w-k">${hi}, Mike</span>${run ? `<span class="w-run">Run #${run.run.n} · ${run.off >= 0.01 ? `<em class="dn">${Math.round(100 * run.off)}% off peak</em>` : `<em class="up">at peak</em>`}</span>` : ""}</div>
      <div class="w-bal">${mbMoney(W.available).replace(/(\.\d\d)$/, "<small>$1</small>")}</div>
      <div class="w-sub"><span class="w-pl ${W.pl >= 0 ? "up" : "dn"}">${W.pl >= 0 ? "▲" : "▼"} ${mbMoney(Math.abs(W.pl)).replace("−", "")}</span><span>all-time</span>${W.risk > 0 ? `<span class="w-ip">${mbMoney(W.risk)} in play</span>` : ""}</div>
      <div class="w-spark">${typeof mbSpark === "function" ? mbSpark(s.bets, 360, 70) : ""}</div>
      <div class="w-acts">
        ${D0.claimed ? act('data-go="rewards"', ic("spin"), "Spun", `${D0.streak}-day streak`, "done") : act('data-spin="1"', ic("spin"), "Free spin", "Up to $250", "hot")}
        ${act('data-go="rewards"', ic("target"), `Missions`, `${mdone}/3 done`)}
        <button class="w-act hx-lvl" data-pass="1"><span class="w-ai">${passRing(L, 30)}</span><b>${L.rank[1]}</b><i>${L.lvl < PASS_MAX ? `${esc(nxt)} next` : "Max level"}</i></button>
      </div></section>`;
  // featured: one swipeable rail of same-sized cards (odds boost, the headliner, the model's picks)
  // every card shares one frame: tag + model chip, headline, detail, and a full-width add bar with the price
  const feat = [], card = (kind, attr, tag, chip, title, sub, mid, cl, cp, art, style = "") => `<div class="fc fc-${kind}" ${style}>${art || ""}
      <div class="fc-hd"><span class="fc-tag">${tag}</span>${chip ? `<span class="fc-chip">${chip}</span>` : ""}</div>
      <b class="fc-t">${title}</b>${sub ? `<i class="fc-s">${sub}</i>` : ""}${mid || ""}
      <button class="fc-cta" ${attr}><span class="fc-cl">${cl}</span><span class="fc-cp">${cp}</span></button></div>`;
  let boostLeg = null;
  try { const ob = typeof mbOddsBoost === "function" ? mbOddsBoost() : null;
    if (ob) { let A = null; try { A = mbArtFor(ob.leg); } catch (e) {} boostLeg = ob.leg.label;
      feat.push(card("boost", 'data-boost="1"', "⚡ Odds boost", ob.leg.p ? `model ${Math.round(100 * ob.leg.p)}% · max $25` : "max $25", esc(ob.leg.label), esc(ob.leg.sub || ""), "",
        `<s>${mbSign(ob.was)}</s> boosted`, mbSign(ob.odds), fcArt(A))); } } catch (e) {}
  const head = mbHeadliner(picks);
  if (head) { const {l, A, first, last, what} = head;
    feat.push(card("head", 'data-head="1"', "★ Tonight's headliner", l.p ? `model ${Math.round(100 * l.p)}%` : "", `<small>${esc(first)}</small>${esc(last || first)}`, esc(what), "",
      "Add to slip", mbSign(l.odds), (A.logo ? `<img class="fc-wm" src="${esc(A.logo)}" alt="" onerror="this.remove()">` : "") + (A.img ? `<img class="fc-cut" src="${esc(A.img)}" alt="" onerror="this.remove()">` : ""),
      `style="--tc:${esc(A.color || "#ff7a45")}"`)); }
  picks.forEach((q, i) => { if (feat.length >= 4 || (q.legs.length === 1 && q.legs[0].label === boostLeg)) return;
    const dec = q.legs.reduce((a, l) => a * mbDec(l.odds), 1), odds = q.legs.length > 1 ? mbAm(dec) : q.legs[0].odds;
    feat.push(card("pick", `data-qp="${i}"`, esc(q.tag || (q.legs.length > 1 ? "Parlay" : "Single")), q.legs.length > 1 ? `${q.legs.length} legs` : "", esc(q.title), "",
      `<div class="fc-legs">${q.legs.slice(0, 3).map(l => `<span><span class="fc-pic">${mbPic(l)}</span><em>${esc(l.label)}</em><i>${mbSign(l.odds)}</i></span>`).join("")}</div>`,
      `$10 pays <b>${mbMoney(10 * dec)}</b>`, mbSign(odds))); });
  let G = []; try { G = typeof mbMiniGames === "function" ? mbMiniGames(true) : []; } catch (e) {}
  const lg = t => `<img src="${esc(t.logo || "")}" alt="" onerror="this.outerHTML='<i>${esc(t.abbr)}</i>'">`;
  const games = G.slice(0, 6).map(g => `<div class="gl-r gs-${g.st}">
      <button class="gl-m" data-go="games"><span class="gl-st">${g.st === "live" ? `<b class="gl-live">LIVE</b>${esc(g.detail || "")}` : g.st === "final" ? "Final" : esc(g.detail || "")}</span>
        <span class="gl-t">${lg(g.a)}<b>${esc(g.a.name || g.a.abbr)}</b>${g.st === "pre" ? `<em>${Math.round(100 * (1 - g.ph))}%</em>` : `<strong>${g.as ?? 0}</strong>`}</span>
        <span class="gl-t">${lg(g.h)}<b>${esc(g.h.name || g.h.abbr)}</b>${g.st === "pre" ? `<em>${Math.round(100 * g.ph)}%</em>` : `<strong>${g.hs ?? 0}</strong>`}</span></button>
      ${g.btnA && g.st === "pre" ? `<span class="gl-px">${g.btnA}${g.btnH}</span>`
        : g.st === "live" && g.lph != null ? `<span class="gl-lv"><em>${Math.round(100 * (1 - g.lph))}%</em><em>${Math.round(100 * g.lph)}%</em><i>live win</i></span>`
        : g.st === "final" ? `<span class="gl-fin">${(g.hs ?? 0) > (g.as ?? 0) ? esc(g.h.abbr) : esc(g.a.abbr)} win</span>` : ""}</div>`).join("");
  return `<div class="hx hx2">
    ${wallet}
    ${live.length ? `<div class="hx-h"><b><span class="livedot"></span>Sweating now</b><button data-sweat="1">Sweat room ›</button></div><div class="hx-list">${live.slice(0, 3).map(b => { const P = mbWinProb(b);
      return `<button class="hx-row" data-go="check"><span class="hx-rt"><b>${esc(b.label)}</b><i>${esc(b.legs.map(l => (mbSweat(l) || {}).text || "").filter(Boolean)[0] || "")}</i></span>${P != null ? `<span class="hx-pc ${P >= 0.6 ? "hi" : P >= 0.35 ? "md" : "lo"}">${Math.round(100 * P)}%</span>` : ""}</button>`; }).join("")}</div>`
      : open.length ? `<button class="hx-row solo" data-go="check"><span class="hx-rt"><b>${open.length} open bet${open.length > 1 ? "s" : ""}</b><i>${mbMoney(W.risk)} riding · to win ${mbMoney(open.reduce((a, b) => a + b.stake * (mbDec(b.odds) - 1) * (1 + (b.boost || 0)), 0))}</i></span>${ic("chev")}</button>` : ""}
    ${feat.length ? `<div class="hx-h"><b>Featured</b><span class="fz-dots">${feat.map((_, i) => `<i class="${i ? "" : "on"}"></i>`).join("")}</span></div><div class="fz" id="fz">${feat.join("")}</div>` : ""}
    ${games ? `<div class="hx-h"><b>${G.some(g => g.st === "live") ? "Tonight · live" : "Tonight's games"}</b><button data-go="games">All ${G.length} ›</button></div><div class="gl">${games}</div>` : ""}
    ${typeof mbSharpCard === "function" ? mbSharpCard() : ""}
    ${done.length ? `<div class="hx-h"><b>Your form</b><button data-go="check">History ›</button></div><div class="hx-rec">${done.map(b => `<span class="hx-r ${b.status === "won" || b.status === "cashout" ? "w" : b.status === "lost" ? "l" : "p"}" title="${esc(b.label)}"></span>`).join("")}<em>${me.n ? `${s.bets.filter(b => b.status === "won").length}–${s.bets.filter(b => b.status === "lost").length}` : ""}</em></div>` : ""}
    ${typeof mbInstallHtml === "function" ? mbInstallHtml() : ""}
  </div>`;
}
function fcArt(A) {
  if (!A) return "";
  if (A.img) return `<img class="fc-cut" src="${esc(A.img)}" alt="" onerror="this.remove()">`;
  if (A.logos) return `<span class="fc-duo"><img src="${esc(A.logos[0])}" alt="" onerror="this.remove()"><img src="${esc(A.logos[1])}" alt="" onerror="this.remove()"></span>`;
  return "";
}
// the model's likeliest scorer among the quick picks, for the Featured rail
function mbHeadliner(picks) {
  let best = null;
  for (const q of picks) for (const l of q.legs) { if (!l.key || l.key.t !== "prop") continue; let A = {}; try { A = Object.assign({}, l, mbArtFor(l) || {}); } catch (e) {}
    if (!best || (l.p || 0) > (best.l.p || 0)) best = {l, A}; }
  if (!best) return null;
  const {l, A} = best, nm = A.name || l.label.replace(/ (to score|anytime TD).*$/i, ""), parts = nm.split(" ");
  try { const t = (D.games || []).flatMap(g => [g.home, g.away]).find(t => t.abbr === (A.team || (l.key || {}).team)); if (t) A.color = t.color; } catch (e) {}
  window.MB_HEAD = l;
  const t = l.label.replace(nm, "").trim();
  return {l, A, first: parts[0], last: parts.slice(1).join(" "), what: t ? t[0].toUpperCase() + t.slice(1) : l.label};
}
function mbWireHome(render) {
  const fz = document.getElementById("fz"); if (fz) fz.onscroll = () => { const c = fz.firstElementChild; if (!c) return; const k = Math.round(fz.scrollLeft / (c.offsetWidth + 12));
    document.querySelectorAll(".fz-dots i").forEach((d, j) => d.classList.toggle("on", j === k)); };
  document.querySelectorAll("[data-head]").forEach(b => b.onclick = e => { e.stopPropagation(); const l = window.MB_HEAD; if (!l) return; slipAdd(Object.assign({}, l)); mbHaptic("success"); try { funBlip(); } catch (er) {} mbOpenSlip(); });
  document.querySelectorAll("[data-pass]").forEach(b => b.onclick = e => { e.stopPropagation(); mbHaptic(); mbOpenPass(); });
  document.querySelectorAll("#view [data-go]").forEach(b => b.onclick = e => { e.preventDefault(); mbHaptic(); TAB = b.dataset.go; if (TAB === "check") MB_VIEW = "bets"; render(); window.scrollTo(0, 0); });
  document.querySelectorAll("[data-qp]").forEach(b => b.onclick = () => { const q = (window.MB_QP || [])[Number(b.dataset.qp)]; if (!q) return;
    q.legs.forEach(l => slipAdd(Object.assign({}, l))); if (q.legs.length > 1) SLIP_MODE = "parlay"; mbHaptic("success"); try { funBlip(); } catch (e) {} mbOpenSlip(); });
}

// 🆚 face-off game card: teams across from each other, a win-probability tug bar, markets as labelled rows.
// o = {a, h, ph, aSub, hSub, state: pre|live|final, time, proj, detail, as, hs, rows: [[label, btnAway, btnHome]]}
function mbVersus(o) {
  if (typeof FX_GMODE === "undefined" || FX_GMODE !== "feed") return mbBoard(o);
  const team = (t, side, sub, p) => `<div class="vs-team ${side}" style="--tc:${esc(t.color || "#556")}">
      <div class="vs-logo"><img src="${esc(t.logo || "")}" alt="" onerror="this.outerHTML='<i>${esc(t.abbr)}</i>'"></div>
      <div class="gtn"><b>${esc(t.name)}</b><span>${sub}</span></div>
      ${o.state === "pre" ? `<em class="vs-pct">${Math.round(100 * p)}%</em>` : ""}</div>`;
  const mid = o.state === "pre" ? `<span class="vs-time">${esc(o.time || "")}</span><b class="vs-at">VS</b><span class="vs-proj">${esc(o.proj || "")}</span>`
    : `<span class="${o.state === "live" ? "live" : "final"}">${o.state === "live" ? "LIVE" : "FINAL"}</span>
       <b class="vs-score"><span class="${o.state === "final" && o.as < o.hs ? "lose" : ""}">${o.as ?? 0}</span><i>–</i><span class="${o.state === "final" && o.hs < o.as ? "lose" : ""}">${o.hs ?? 0}</span></b>
       <span class="vs-proj">${esc(o.state === "live" ? o.detail || "" : "")}</span>`;
  const pa = Math.round(100 * (1 - o.ph)), lpa = o.lph == null ? null : Math.round(100 * (1 - o.lph));
  if (o.state === "live") return `<div class="vs-top">${team(o.a, "a", o.aSub, 1 - o.ph)}<div class="vs-mid">${mid}</div>${team(o.h, "h", o.hSub, o.ph)}</div>
    <div class="vs-tug"><i style="width:${lpa ?? pa}%;background:${esc(o.a.color || "#556")}"></i><i style="width:${100 - (lpa ?? pa)}%;background:${esc(o.h.color || "#556")}"></i></div>
    <div class="vs-live">${lpa == null ? `<span>Betting closed · game in progress</span>` : `<b>${lpa}%</b><span>Live win chance</span><b>${100 - lpa}%</b>`}</div>`;
  return `<div class="vs-top">${team(o.a, "a", o.aSub, 1 - o.ph)}<div class="vs-mid">${mid}</div>${team(o.h, "h", o.hSub, o.ph)}</div>
    <div class="vs-tug"><i style="width:${pa}%;background:${esc(o.a.color || "#556")}"></i><i style="width:${100 - pa}%;background:${esc(o.h.color || "#556")}"></i></div>
    <div class="vs-mks">${o.rows.map(([lab, x, y]) => `<div class="vs-mk"><span class="vs-lab">${lab}</span>${x}${y}</div>`).join("")}</div>`;
}

// 📋 board card: the classic sportsbook grid. Two team rows, three price columns (line · total · moneyline).
function mbBoard(o) {
  const ml = o.rows[0], ln = o.rows[1], to = o.rows[2], tl = (String(to[0]).match(/[\d.]+/) || [""])[0];
  const tot = (b, k) => String(b).replace(/<span class="pt">(Over|Under)<\/span>/, `<span class="pt">${k} ${tl}</span>`);
  const head = String(ln[0]).replace("Puck line", "Puck");
  const team = (t, sub, p, sc, other) => `<div class="bx-tm" style="--tc:${esc(t.color || "#556")}"><span class="bx-lg"><img src="${esc(t.logo || "")}" alt="" onerror="this.outerHTML='<i>${esc(t.abbr)}</i>'"></span>
      <span class="bx-nm"><b>${esc(t.name)}</b><i>${o.state === "pre" ? `<em class="bx-p">${Math.round(100 * p)}%</em>` : ""}${sub}</i></span>${o.state === "pre" ? "" : `<strong class="bx-sc ${o.state === "final" && sc < other ? "lose" : ""}">${sc ?? 0}</strong>`}</div>`;
  const st = o.state === "live" ? `<span class="bx-live">LIVE</span><span>${esc(o.detail || "")}</span>` : o.state === "final" ? `<span class="bx-fin">FINAL</span>` : `<span class="bx-time">${esc(o.time || "")}</span><span class="bx-proj">${esc(o.proj || "")}</span>`;
  const pa = Math.round(100 * (1 - o.ph));
  if (o.state === "live") {   // prices are closed once the game starts: show the score and the model's live win chance instead
    const lp = o.lph, lv = (t, p, sc, other) => `<div class="bx-row lv">${team(t, o.aSub === undefined ? "" : (t === o.a ? o.aSub : o.hSub), 0, sc, other)}
      <div class="bx-lv" style="--tc:${esc(t.color || "#556")}">${lp == null ? `<span class="bx-lvn">${sc > other ? "Leading" : sc < other ? "Trailing" : "Tied"}</span>` : `<i style="width:${Math.max(3, Math.round(100 * p))}%"></i><b>${Math.round(100 * p)}%</b>`}</div></div>`;
    return `<div class="bx bx-on">
      <div class="bx-top"><span class="bx-st">${st}</span><span class="bx-h wide">${lp == null ? "Prices closed" : "Live win chance"}</span></div>
      ${lv(o.a, lp == null ? 0 : 1 - lp, o.as ?? 0, o.hs ?? 0)}${lv(o.h, lp == null ? 0 : lp, o.hs ?? 0, o.as ?? 0)}
      <div class="bx-note">Pregame betting closed · pregame model ${esc(o.a.abbr)} ${pa}% · ${esc(o.h.abbr)} ${100 - pa}%</div></div>`;
  }
  return `<div class="bx bx-${o.state}">
    <div class="bx-top"><span class="bx-st">${st}</span><span class="bx-h">${o.state === "final" ? "" : esc(head)}</span><span class="bx-h">${o.state === "final" ? "Result" : "Total"}</span><span class="bx-h">${o.state === "final" ? "" : "Money"}</span></div>
    <div class="bx-row">${team(o.a, o.aSub, 1 - o.ph, o.as, o.hs)}${ln[1]}${tot(to[1], "O")}${ml[1]}</div>
    <div class="bx-row">${team(o.h, o.hSub, o.ph, o.hs, o.as)}${ln[2]}${tot(to[2], "U")}${ml[2]}</div>
    <div class="bx-tug" title="Model win chance"><i style="width:${pa}%;background:${esc(o.a.color || "#556")}"></i><i style="width:${100 - pa}%;background:${esc(o.h.color || "#556")}"></i></div></div>`;
}
