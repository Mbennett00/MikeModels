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
  const info = typeof mbSportInfo === "function" ? mbSportInfo() : {sport: MB_PAGE, line: ""};
  const open = s.bets.filter(b => b.status === "open"), live = open.filter(mbIsLive);
  const done = s.bets.filter(b => b.status !== "open").sort((a, b) => (b.result_ts || b.ts).localeCompare(a.result_ts || a.ts)).slice(0, 10);
  const mb = (s.model || {}).bets || [], me = mbStats(s.bets), ms = mbStats(mb);
  const picks = (() => { try { return typeof mbQuickPicks === "function" ? mbQuickPicks() || [] : []; } catch (e) { return []; } })();
  window.MB_QP = picks;
  const nxt = passRewardText(passReward(Math.min(L.lvl + 1, PASS_MAX))).split(" · ")[0];
  const chip = (attr, icon, top, sub, cls = "") => `<button class="hx-chip ${cls}" ${attr}><span class="hx-ci">${ic(icon)}</span><span class="hx-ct"><b>${top}</b><i>${sub}</i></span></button>`;
  const today = [
    D0.claimed ? chip('data-go="rewards"', "spin", "Spun today", `${D0.streak}-day streak`, "done") : chip('data-spin="1"', "spin", "Free spin", "Up to $250", "gold"),
    chip('data-go="rewards"', "target", `Missions ${mdone}/3`, mdone >= 3 ? "All complete" : esc(M.find(m => !m.claimed).t)),
    chip('data-pass="1"', "star", `Level ${L.lvl}`, L.lvl < PASS_MAX ? `${L.need - L.into} XP to ${esc(nxt)}` : "Max level"),
    mb.length ? chip('data-go="rewards"', "vs", me.pl >= ms.pl ? "Ahead of model" : "Model leads", `${me.pl - ms.pl >= 0 ? "+" : "−"}$${Math.abs(me.pl - ms.pl).toFixed(0)}`) : "",
  ].join("");
  const qp = picks.map((q, i) => { const dec = q.legs.reduce((a, l) => a * mbDec(l.odds), 1), odds = q.legs.length > 1 ? mbAm(dec) : q.legs[0].odds;
    return `<div class="hx-qp"><div class="hx-qtag">${esc(q.tag || (q.legs.length > 1 ? "Parlay" : "Single"))}</div><div class="hx-qt">${esc(q.title)}</div>
      <div class="hx-legs">${q.legs.map(l => `<div class="hx-leg"><span class="hx-dot"></span><span>${esc(l.label)}</span><i>${mbSign(l.odds)}</i></div>`).join("")}</div>
      <div class="hx-qf"><div><b>${mbSign(odds)}</b><i>$10 pays ${mbMoney(10 * dec)}</i></div><button class="hx-add" data-qp="${i}">Add</button></div></div>`; }).join("");
  const sports = [["NHL", "index.html", "https://a.espncdn.com/i/teamlogos/leagues/500-dark/nhl.png", "Hockey"], ["NFL", "nfl.html", "https://a.espncdn.com/i/teamlogos/leagues/500-dark/nfl.png", "Football"]]
    .map(([k, href, img, nm]) => `<a class="hx-sport ${k === info.sport ? "on" : ""}" href="${href}" ${k === info.sport ? 'data-go="games"' : ""}><img src="${img}" alt="" onerror="this.remove()"><span><b>${nm}</b><i>${k === info.sport ? esc(info.line || "") : "Switch sport"}</i></span>${ic("chev")}</a>`).join("");
  return `<div class="hx">
    <section class="hx-hero"><div class="hx-hl"><div class="hx-eye">${hi}, Mike</div><div class="hx-bal">${mbMoney(W.available).replace(/(\.\d\d)$/, '<small>$1</small>')}</div>
      <div class="hx-sub"><span class="${W.pl >= 0 ? "up" : "dn"}">${W.pl >= 0 ? "+" : "−"}${mbMoney(Math.abs(W.pl)).replace("−", "")}</span> all-time${W.risk > 0 ? ` · ${mbMoney(W.risk)} in play` : ""}</div></div>
      <button class="hx-lvl" data-pass="1">${passRing(L, 56)}<i>${L.rank[1]}</i></button>${typeof mbSpark === "function" ? mbSpark(s.bets) : ""}</section>
    <div class="hx-chips">${today}</div>
    ${typeof mbSharpCard === "function" ? mbSharpCard() : ""}
    ${live.length ? `<div class="hx-h"><b><span class="livedot"></span>Live</b><button data-go="check">All bets</button></div><div class="hx-list">${live.slice(0, 3).map(b => { const P = mbWinProb(b);
      return `<button class="hx-row" data-go="check"><span class="hx-rt"><b>${esc(b.label)}</b><i>${esc(b.legs.map(l => (mbSweat(l) || {}).text || "").filter(Boolean)[0] || "")}</i></span>${P != null ? `<span class="hx-pc ${P >= 0.6 ? "hi" : P >= 0.35 ? "md" : "lo"}">${Math.round(100 * P)}%</span>` : ""}</button>`; }).join("")}</div>`
      : open.length ? `<button class="hx-row solo" data-go="check"><span class="hx-rt"><b>${open.length} open bet${open.length > 1 ? "s" : ""}</b><i>${mbMoney(W.risk)} riding · to win ${mbMoney(open.reduce((a, b) => a + b.stake * (mbDec(b.odds) - 1) * (1 + (b.boost || 0)), 0))}</i></span>${ic("chev")}</button>` : ""}
    ${qp ? `<div class="hx-h"><b>Quick picks</b><span>by the model</span></div><div class="hx-qps">${qp}</div>` : ""}
    <div class="hx-h"><b>Sports</b></div><div class="hx-list">${sports}</div>
    ${typeof mbInstallHtml === "function" ? mbInstallHtml() : ""}
    ${done.length ? `<div class="hx-h"><b>Recent</b><button data-go="check">History</button></div><div class="hx-rec">${done.map(b => `<span class="hx-r ${b.status === "won" || b.status === "cashout" ? "w" : b.status === "lost" ? "l" : "p"}" title="${esc(b.label)}"></span>`).join("")}<em>${me.n ? `${s.bets.filter(b => b.status === "won").length}–${s.bets.filter(b => b.status === "lost").length}` : ""}</em></div>` : ""}
  </div>`;
}
function mbWireHome(render) {
  document.querySelectorAll("[data-pass]").forEach(b => b.onclick = e => { e.stopPropagation(); mbHaptic(); mbOpenPass(); });
  document.querySelectorAll("#view [data-go]").forEach(b => b.onclick = e => { e.preventDefault(); mbHaptic(); TAB = b.dataset.go; if (TAB === "check") MB_VIEW = "bets"; render(); window.scrollTo(0, 0); });
  document.querySelectorAll("[data-qp]").forEach(b => b.onclick = () => { const q = (window.MB_QP || [])[Number(b.dataset.qp)]; if (!q) return;
    q.legs.forEach(l => slipAdd(Object.assign({}, l))); if (q.legs.length > 1) SLIP_MODE = "parlay"; mbHaptic("success"); try { funBlip(); } catch (e) {} mbOpenSlip(); });
}
