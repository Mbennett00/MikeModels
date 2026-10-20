// ---------- PIKT price helpers (shared by the NHL, NFL and NBA pages) ----------
// A selection is one side of a market (a game line or a player prop) with the model's chance and, where the market has
// one, the books' price. Prices are shown read-only: Pikt is projections and sims, there is no betting.
const BK = {hold: 0.045};
const BK_REG = {};
const bkDay = (t = Date.now()) => new Date(t).toLocaleDateString("en-CA", {timeZone: "America/New_York"});
const bkImp = p => Math.min(0.97, Math.max(0.03, p) * (1 + BK.hold));
const bkDec = p => Math.round(1e4 / bkImp(p)) / 1e4;
const bkAm = d => d >= 2 ? "+" + Math.round(100 * (d - 1)) : "−" + Math.round(100 / (d - 1));
const bkEvDate = s => bkDay(new Date(s).getTime()).replace(/-/g, "");
const bkHalf = x => Math.floor(x) + 0.5;   // the nearest hook below: lines never push
const bkN = n => Math.round(n).toLocaleString("en-US");

function bkSel(o) {
  const s = Object.assign({}, o);
  s.key = [s.sport, s.gid, s.kind, s.side, s.line ?? "", s.pl ? s.pl.id + ":" + s.pl.stat : ""].join("|");
  s.open = s.open !== false && (!s.start || new Date(s.start) > Date.now());
  s.dec = o.dec || bkDec(s.p);   // a market price comes in as dec; otherwise price the chance
  BK_REG[s.key] = s;
  return s;
}
function bkArt(s, cls = "") {
  const im = (src, c = "") => src ? `<img class="${c}" src="${esc(src)}" alt="" loading="lazy" onerror="this.remove()">` : "";
  if (s.img) return `<span class="bk-art pl ${cls}" style="--tc:${esc(s.color || "#345")}"><span>${esc(String(s.pl ? s.pl.name : s.pick).split(" ").map(w => w[0]).slice(0, 2).join(""))}</span>${im(s.img, "hs")}${im(s.logo, "lg")}</span>`;
  if (s.logos) return `<span class="bk-art duo ${cls}">${im(s.logos[0])}${im(s.logos[1])}</span>`;
  return `<span class="bk-art ${cls}" style="--tc:${esc(s.color || "#345")}">${s.logo ? im(s.logo) : `<b>${esc(String(s.pick).slice(0, 3))}</b>`}</span>`;
}
// a price: line on top (spread / total), odds below (read-only)
function bkBtn(s, top = "") {
  if (!s || s.p == null || !isFinite(s.p)) return `<span class="bk-px off">–</span>`;
  return `<span class="bk-px ${s.src === "fd" ? "fd" : ""}">${top ? `<i>${esc(top)}</i>` : ""}<b>${bkAm(s.dec)}</b></span>`;
}
const BK_ESPN = {NHL: ["hockey/nhl", {LA: "LAK", NJ: "NJD", SJ: "SJS", TB: "TBL", UTAH: "UTA", WAS: "WSH"}],
                 NFL: ["football/nfl", {LAR: "LA", WSH: "WAS"}], NBA: ["basketball/nba", {}]};
const bkNm = s => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\b(jr|sr|ii|iii|iv)\b/g, "").replace(/[^a-z]/g, "");
