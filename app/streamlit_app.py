"""NHL Model dashboard (Streamlit). Designed for phone and desktop browsers.

Data comes from the `data-latest` GitHub release written by the daily workflow.
Settings (Streamlit secrets or environment variables):
  NHLMODEL_REPO       owner/repo (default Mbennett00/NHLModel)
  GITHUB_TOKEN        only needed if the repository is private
  NHLMODEL_SITE_DIR   read files from a local folder instead (development)
"""
from __future__ import annotations

import html
import io
import json
import os
import pickle
import sys

import altair as alt
import numpy as np
import pandas as pd
import requests
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from nhlmodel.pricing import format_american  # noqa: E402

st.set_page_config(page_title="NHL Model", page_icon="🏒", layout="wide", initial_sidebar_state="collapsed")

TAG = "data-latest"
ET = "America/New_York"
ACCENT = "#2a78d6"

# ---------------------------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------------------------
st.markdown("""
<style>
:root {
  --bg: #f7f7f5; --surface: #ffffff; --border: #e6e5e1; --border-strong: #d6d5d0;
  --text: #0b0b0b; --text-2: #52514e; --muted: #8a8984; --accent: #2a78d6; --accent-soft: #eaf2fc;
  --good: #0ca30c; --good-text: #006300; --good-soft: #e8f5e8;
  --warn: #fab219; --warn-text: #7a5200; --warn-soft: #fff6e0;
  --bad: #d03b3b; --bad-soft: #fbeaea;
}
html, body, [data-testid="stAppViewContainer"] { background: var(--bg); }
[data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer,
[data-testid="stDecoration"], [data-testid="stStatusWidget"] { display: none !important; }
.block-container { max-width: 1080px; padding: 1.25rem 1rem 4rem; }
h1, h2, h3 { letter-spacing: -0.01em; }

/* header */
.hdr { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; flex-wrap: wrap;
       margin: 4px 0 14px; }
.hdr .brand { font-size: 26px; font-weight: 700; color: var(--text); line-height: 1.1; }
.hdr .brand span { color: var(--accent); }
.hdr .sub { color: var(--text-2); font-size: 14px; margin-top: 4px; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.chip { font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--border);
        background: var(--surface); color: var(--text-2); white-space: nowrap; }
.chip.ok { background: var(--good-soft); border-color: transparent; color: var(--good-text); }
.chip.warn { background: var(--warn-soft); border-color: transparent; color: var(--warn-text); }
.chip.info { background: var(--accent-soft); border-color: transparent; color: #1c5aa6; }

/* tabs as a segmented control */
[data-testid="stTabs"] [role="tablist"] { gap: 2px; background: #efeeea; padding: 4px; border-radius: 12px;
    overflow-x: auto; scrollbar-width: none; border: 0; box-shadow: none; }
[data-testid="stTabs"] [role="tablist"]::-webkit-scrollbar { display: none; }
[data-testid="stTab"] { height: 34px; padding: 0 14px; border-radius: 9px; background: transparent; flex: 0 0 auto;
    display: flex; align-items: center; cursor: pointer; }
[data-testid="stTab"] p { font-weight: 600; color: var(--text-2); font-size: 14px; white-space: nowrap; }
[data-testid="stTab"][aria-selected="true"] { background: var(--surface); box-shadow: 0 1px 2px rgba(0,0,0,.08); }
[data-testid="stTab"][aria-selected="true"] p { color: var(--text); }
[data-testid="stTabs"] .react-aria-SelectionIndicator { display: none !important; }
[data-testid="stTabs"] [role="tablist"]::after, [data-testid="stTabs"] [role="tablist"]::before { display: none; }

/* cards */
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr)); gap: 10px; }
.grid .card { margin-bottom: 0; }
@media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
        padding: 14px 16px; margin-bottom: 10px; }
.card.muted { background: #fbfbfa; }
.play { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.play .title { font-size: 16px; font-weight: 650; color: var(--text); line-height: 1.3; }
.play .meta { font-size: 13px; color: var(--text-2); margin-top: 2px; }
.edge { font-size: 15px; font-weight: 700; padding: 5px 10px; border-radius: 10px; white-space: nowrap;
        background: var(--good-soft); color: var(--good-text); }
.edge.neutral { background: #f0efec; color: var(--text-2); }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
.stat .k { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.stat .v { font-size: 15px; font-weight: 600; color: var(--text); font-variant-numeric: tabular-nums; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.tag { font-size: 12px; padding: 2px 8px; border-radius: 6px; background: #f0efec; color: var(--text-2); }
.tag.warn { background: var(--warn-soft); color: var(--warn-text); }

/* game cards */
.game-h { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.game-h .teams { font-size: 17px; font-weight: 700; }
.game-h .time { font-size: 13px; color: var(--text-2); }
.proj { font-size: 13px; color: var(--text-2); margin-bottom: 10px; }
table.mk { width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: tabular-nums;
           border: 0 !important; margin: 0; display: table; }
table.mk th, table.mk td { border-left: 0 !important; border-right: 0 !important; border-top: 0 !important;
                           background: transparent !important; }
table.mk th:not(:first-child), table.mk td:not(:first-child) { text-align: right; }
table.mk td:first-child { font-weight: 600; }
table.mk th { text-align: left; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em;
              color: var(--muted); padding: 4px 6px; border-bottom: 1px solid var(--border); }
table.mk td { padding: 7px 6px; border-bottom: 1px solid #f0efec; color: var(--text); }
table.mk tr:last-child td { border-bottom: 0; }
table.mk td.pos { color: var(--good-text); font-weight: 650; }
table.mk td.dim { color: var(--muted); }

/* KPI tiles */
.tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
.tile { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 12px 14px; }
.tile .k { font-size: 12px; color: var(--text-2); }
.tile .v { font-size: 26px; font-weight: 700; color: var(--text); margin-top: 2px; }
.tile .d { font-size: 12px; color: var(--muted); }

/* status rows */
.srow { display: flex; justify-content: space-between; align-items: center; padding: 10px 0;
        border-bottom: 1px solid #f0efec; gap: 10px; }
.srow:last-child { border-bottom: 0; }
.srow .name { font-weight: 650; }
.srow .detail { font-size: 13px; color: var(--text-2); }
.badge { font-size: 12px; font-weight: 650; padding: 3px 9px; border-radius: 999px; white-space: nowrap; }
.badge.ok { background: var(--good-soft); color: var(--good-text); }
.badge.warn { background: var(--warn-soft); color: var(--warn-text); }
.badge.bad { background: var(--bad-soft); color: #a32424; }

.empty { text-align: center; padding: 28px 16px; color: var(--text-2); }
.empty .big { font-size: 18px; font-weight: 650; color: var(--text); margin-bottom: 6px; }
.section { font-size: 13px; font-weight: 650; color: var(--text-2); text-transform: uppercase; letter-spacing: .05em;
           margin: 18px 2px 8px; }
.steps { margin: 14px auto 0; padding: 0; list-style: none; color: var(--text-2); font-size: 14px;
         display: inline-block; text-align: left; }
.steps li { margin: 6px 0; padding-left: 24px; position: relative; }
.steps li::before { content: "○"; position: absolute; left: 0; color: var(--muted); }
.steps li.done { color: var(--good-text); }
.steps li.done::before { content: "✓"; color: var(--good-text); font-weight: 700; }

@media (max-width: 640px) {
  .block-container { padding: .75rem .75rem 3rem; }
  .hdr .brand { font-size: 22px; }
  .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tile .v { font-size: 22px; }
  [data-testid="stTab"] { padding: 0 8px; }
  [data-testid="stTab"] p { font-size: 13px; }
  table.mk { font-size: 13px; }
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------------------------
def setting(name, default=None):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


REPO = setting("NHLMODEL_REPO", "Mbennett00/NHLModel")
TOKEN = setting("GITHUB_TOKEN")
LOCAL = setting("NHLMODEL_SITE_DIR")


@st.cache_data(ttl=300, show_spinner=False)
def release_assets() -> dict:
    if LOCAL:
        return {}
    h = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    try:
        r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}", headers=h, timeout=20)
    except requests.RequestException:
        return {}
    if r.status_code != 200:
        return {}
    return {a["name"]: a["url"] for a in r.json().get("assets", [])}


@st.cache_data(ttl=300, show_spinner=False)
def fetch(name: str) -> bytes | None:
    if LOCAL:
        p = os.path.join(LOCAL, name)
        return open(p, "rb").read() if os.path.exists(p) else None
    url = release_assets().get(name)
    if not url:
        return None
    h = {"Accept": "application/octet-stream"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    r = requests.get(url, headers=h, timeout=60)
    return r.content if r.status_code == 200 else None


def csv(name, **kw):
    b = fetch(name)
    return pd.read_csv(io.BytesIO(b), **kw) if b else pd.DataFrame()


def js(name):
    b = fetch(name)
    return json.loads(b) if b else {}


# ---------------------------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------------------------
E = html.escape
MARKET_NAME = {"goals": "Anytime goal", "sog": "Shots on goal", "assists": "Assists", "points": "Points",
               "moneyline": "Moneyline", "puckline": "Puck line", "total": "Total", "team_total": "Team total",
               "p1_total": "1st period total", "p1_3way": "1st period 3-way"}
SHORT = {"sog": "SOG", "assists": "AST", "points": "PTS", "goals": "G"}


def teams_of(matchup: str):
    away, home = str(matchup).split(" @ ")
    return home, away


def describe(r) -> str:
    home, away = teams_of(r.matchup)
    m, s, ln = r.market, str(r.selection), r.line
    team = lambda x: home if x.startswith("home") else (away if x.startswith("away") else "Draw")
    if m in SHORT:
        if m == "goals" and ln == 0.5 and s == "over":
            return f"{r.player} · anytime goal"
        return f"{r.player} · {'Over' if s == 'over' else 'Under'} {ln:g} {SHORT[m]}"
    if m == "moneyline":
        return f"{team(s)} moneyline"
    if m == "puckline":
        return f"{team(s)} {ln:+g}"
    if m == "total":
        return f"{'Over' if s == 'over' else 'Under'} {ln:g} goals"
    if m == "team_total":
        return f"{team(s)} {'over' if s.endswith('over') else 'under'} {ln:g}"
    if m == "p1_total":
        return f"1st period {'over' if s == 'over' else 'under'} {ln:g}"
    if m == "p1_3way":
        return f"1st period: {team(s)}"
    return f"{m} {s} {ln}"


def fmt_time(x):
    t = pd.to_datetime(x, utc=True, errors="coerce")
    return "" if pd.isna(t) else t.tz_convert(ET).strftime("%-I:%M %p")


def pct(p, d=1):
    return "–" if p is None or pd.isna(p) else f"{100 * p:.{d}f}%"


def am(x):
    return "–" if x is None or pd.isna(x) else format_american(x)


def prep(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    d = df.copy()
    d["play"] = [describe(r) for r in d.itertuples()]
    d["time"] = [fmt_time(x) for x in d.get("start_utc", pd.Series([None] * len(d)))]
    d["notes"] = d["flags"].fillna("") if "flags" in d else ""
    d["confirmed"] = d.confirmed.astype(bool)
    return d


def play_card(r, muted=False) -> str:
    edge = r.edge
    edge_html = (f'<div class="edge">+{100 * edge:.1f}%</div>' if pd.notna(edge) and edge > 0
                 else f'<div class="edge neutral">{pct(edge) if pd.notna(edge) else "no line"}</div>')
    tags = []
    if not r.confirmed:
        tags.append('<span class="tag warn">⚠ Lineup/goalie unconfirmed</span>')
    if r.confidence == "low":
        tags.append('<span class="tag">Low confidence · thin or single-book market</span>')
    for n in [x.strip() for x in str(r.notes).split(";") if x.strip()][:2]:
        tags.append(f'<span class="tag">{E(n)}</span>')
    proj_label = "Projection" if r.market in SHORT else "Proj. goals"
    return f"""
<div class="card{' muted' if muted else ''}">
  <div class="play">
    <div><div class="title">{E(r.play)}</div>
         <div class="meta">{E(r.matchup)}{' · ' + E(r.time) if r.time else ''} · {MARKET_NAME.get(r.market, r.market)}</div></div>
    {edge_html}
  </div>
  <div class="stats">
    <div class="stat"><div class="k">Best price</div><div class="v">{am(r.best_price)}</div></div>
    <div class="stat"><div class="k">Model</div><div class="v">{pct(r.p_model)}</div></div>
    <div class="stat"><div class="k">Fair odds</div><div class="v">{am(r.fair_odds)}</div></div>
    <div class="stat"><div class="k">Book no-vig</div><div class="v">{pct(r.p_novig)}</div></div>
  </div>
  {'<div class="tags">' + ''.join(tags) + '</div>' if tags else ''}
</div>"""


def empty(title, body=""):
    st.markdown(f'<div class="card empty"><div class="big">{E(title)}</div>{body}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------------------------
meta, status = js("meta.json"), js("status.json")
plays_raw = csv("plays.csv")
if "plays" not in st.session_state or st.session_state.get("plays_src") != meta.get("generated_at"):
    st.session_state.plays = plays_raw
    st.session_state.plays_src = meta.get("generated_at")
    st.session_state.repriced = False
plays = prep(st.session_state.plays)

# ---------------------------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------------------------
if meta.get("date"):
    d = pd.Timestamp(meta["date"])
    when = ("Next slate · " if meta.get("upcoming") else "") + d.strftime("%A, %B %-d")
    sub = f"{when} · {meta.get('games', 0)} games"
else:
    sub = "Setting up"
chips = []
if meta.get("generated_at"):
    chips.append(f'<span class="chip">Updated {pd.Timestamp(meta["generated_at"]).strftime("%-I:%M %p")} ET</span>')
if meta:
    chips.append('<span class="chip ok">Odds live</span>' if meta.get("odds_rows") else
                 '<span class="chip warn">No odds yet</span>')
    if meta.get("teams"):
        c, n = meta.get("teams_confirmed", 0), meta["teams"]
        chips.append(f'<span class="chip {"ok" if c == n else "warn"}">Lineups {c}/{n} confirmed</span>')
if st.session_state.repriced:
    chips.append('<span class="chip info">Re-priced with your lineups</span>')
st.markdown(f"""
<div class="hdr">
  <div><div class="brand">NHL <span>Model</span></div><div class="sub">{E(sub)}</div></div>
  <div class="chips">{''.join(chips)}</div>
</div>""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------------------------
# Setup state: nothing published yet
# ---------------------------------------------------------------------------------------------
if plays.empty:
    games = status.get("games_stored", 0)
    steps = [
        ("Data pipeline connected", True),
        (f"Historical games loaded ({games:,} so far)" if games else "Loading two seasons of NHL games (first run takes about an hour)",
         games > 1500),
        ("Model backtested and first slate priced", bool(meta.get("generated_at"))),
    ]
    items = "".join(f'<li class="{"done" if ok else ""}">{E(t)}</li>' for t, ok in steps)
    msg = ("No regular-season games scheduled soon." if meta.get("generated_at") else
           "The daily job is building the data. This page fills in automatically once it finishes.")
    empty("Getting ready", f'<div>{E(msg)}</div><ul class="steps">{items}</ul>')
    st.stop()

# ---------------------------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------------------------
t_best, t_games, t_props, t_lineups, t_results, t_model = st.tabs(
    ["Bets", "Games", "Props", "Lineups", "Results", "Model"])

flagged = plays[plays.flag.astype(bool)].sort_values("edge", ascending=False)
pending = plays[(~plays.confirmed) & (plays.edge >= plays.threshold)].sort_values("edge", ascending=False)

with t_best:
    if len(flagged):
        st.markdown('<div class="grid">' + "".join(play_card(r) for r in flagged.itertuples()) + "</div>",
                    unsafe_allow_html=True)
    else:
        why = []
        if not meta.get("odds_rows"):
            why.append("No sportsbook odds yet, so there is nothing to compare against. Add the "
                       "<b>ODDS_API_KEY</b> secret in GitHub, or wait for lines to post.")
        if len(pending):
            why.append(f"{len(pending)} edges are waiting on confirmed lineups and goalies (see below or the Lineups tab).")
        if not why:
            why.append("No play clears the edge threshold right now.")
        empty("No bets flagged yet", "<br>".join(why))
    if len(pending):
        st.markdown(f'<div class="section">Waiting on confirmation · {len(pending)}</div>', unsafe_allow_html=True)
        st.markdown('<div class="grid">' + "".join(play_card(r, muted=True) for r in pending.head(15).itertuples())
                    + "</div>", unsafe_allow_html=True)

with t_games:
    games = plays[plays.player.fillna("") == ""]
    for gid, g in games.groupby("game_id", sort=False):
        r0 = g.iloc[0]
        home, away = teams_of(r0.matchup)
        proj = g[g.market == "moneyline"].projection.iloc[0] if (g.market == "moneyline").any() else ""
        tot = g[(g.market == "total")].projection
        proj_txt = E(str(proj).replace(" (regulation goal λ)", ""))
        rows = []

        def row(label, sel_rows):
            out = []
            for r in sel_rows.itertuples():
                edge_cls = ("pos" if pd.notna(r.edge) and r.edge >= r.threshold else
                            "dim" if pd.isna(r.edge) or r.edge < 0 else "")
                out.append(f"<tr><td>{E(label(r))}</td><td>{pct(r.p_model)}</td><td>{am(r.fair_odds)}</td>"
                           f"<td>{am(r.best_price)}</td><td class='{edge_cls}'>{f'{100 * r.edge:+.1f}%' if pd.notna(r.edge) else '–'}</td></tr>")
            return out

        ml = g[g.market == "moneyline"]
        rows += row(lambda r: f"{home if r.selection == 'home' else away} ML", ml.sort_values("selection", ascending=False))
        pl = g[(g.market == "puckline") & (g.line.abs() == 1.5)]
        pl = pl[((pl.selection == "home") & (pl.line == -1.5)) | ((pl.selection == "away") & (pl.line == 1.5))
                if (ml.p_model.iloc[0] if len(ml) else .5) >= .5 else
                ((pl.selection == "away") & (pl.line == -1.5)) | ((pl.selection == "home") & (pl.line == 1.5))]
        rows += row(lambda r: f"{home if r.selection == 'home' else away} {r.line:+g}", pl)
        tl = g[g.market == "total"]
        if len(tl):
            main = tl[tl.best_price.notna()].line.mode()
            ln = main.iloc[0] if len(main) else 6.5
            rows += row(lambda r: f"{'Over' if r.selection == 'over' else 'Under'} {r.line:g}",
                        tl[tl.line == ln].sort_values("selection"))
        st.markdown(f"""
<div class="card">
  <div class="game-h"><div class="teams">{E(away)} @ {E(home)}</div><div class="time">{E(r0.time)}</div></div>
  <div class="proj">Projected regulation goals: {proj_txt}{' · total ' + E(str(tot.iloc[0])) if len(tot) else ''}</div>
  <table class="mk"><tr><th>Market</th><th>Model</th><th>Fair</th><th>Best</th><th>Edge</th></tr>{''.join(rows)}</table>
</div>""", unsafe_allow_html=True)

with t_props:
    props = plays[plays.player.fillna("") != ""]
    if props.empty:
        empty("No props priced")
    else:
        c1, c2, c3 = st.columns([2, 2, 1.4])
        q = c1.text_input("Player", placeholder="Search a player", label_visibility="collapsed")
        mk = c2.segmented_control("Market", ["Shots", "Goals", "Assists", "Points"], default="Shots",
                                  label_visibility="collapsed") or "Shots"
        only_lines = c3.toggle("Has book line", value=bool(props.best_price.notna().any()))
        key = {"Shots": "sog", "Goals": "goals", "Assists": "assists", "Points": "points"}[mk]
        d = props[props.market == key]
        if q:
            d = d[d.player.str.contains(q, case=False, na=False)]
        if only_lines:
            d = d[d.best_price.notna()]
        else:
            d = d[d.selection == "over"]
        d = d.sort_values(["edge", "p_model"], ascending=False)
        view = pd.DataFrame({
            "Player": d.player,
            "Bet": [("Over " if s == "over" else "Under ") + f"{l:g}" for s, l in zip(d.selection, d.line)],
            "Edge": d.edge * 100, "Best": d.best_price.map(am), "Model": d.p_model * 100,
            "Fair": d.fair_odds.map(am), "Proj": pd.to_numeric(d.projection, errors="coerce"),
            "Game": d.matchup, "Lineup": np.where(d.confirmed, "confirmed", "unconfirmed")})
        st.dataframe(view, hide_index=True, use_container_width=True, height=min(600, 38 + 35 * len(view)),
                     column_config={
                         "Proj": st.column_config.NumberColumn(format="%.2f"),
                         "Model": st.column_config.NumberColumn(format="%.1f%%"),
                         "Edge": st.column_config.NumberColumn(format="%+.1f%%"),
                     })

with t_lineups:
    blob = fetch("slate_state.pkl")
    if not blob:
        empty("Lineups not available yet")
    else:
        saved = pickle.loads(blob)
        state, roster = saved["state"], saved["roster"]
        lu = state.lineups.copy()
        st.caption("Projected lineups come from each team's last game; starters from recent starts. Confirm what "
                   "you know, then re-price. Only confirmed teams can have best bets.")
        choices = []
        for gm in state.schedule.itertuples():
            with st.expander(f"{gm.away} @ {gm.home}", expanded=False):
                cols = st.columns(2)
                for col, team in zip(cols, (gm.away, gm.home)):
                    goalies = roster[(roster.team == team) & (roster.pos == "G")]
                    cur = lu[(lu.team == team) & (lu.pos == "G")]
                    names = list(dict.fromkeys(goalies.name))
                    idx = names.index(cur.name.iloc[0]) if len(cur) and cur.name.iloc[0] in names else 0
                    col.markdown(f"**{team}**")
                    gname = col.selectbox("Starting goalie", names, index=idx, key=f"g_{gm.game_id}_{team}") if names else None
                    gconf = col.toggle("Goalie confirmed", key=f"gc_{gm.game_id}_{team}",
                                       value=bool(cur.confirmed.iloc[0]) if len(cur) else False)
                    lconf = col.toggle("Lineup confirmed", key=f"lc_{gm.game_id}_{team}",
                                       value=bool(lu[(lu.team == team) & (lu.pos != "G")].confirmed.all()))
                    choices.append(dict(team=team, goalie=gname, goalie_confirmed=gconf, lineup_confirmed=lconf))
        b1, b2 = st.columns(2)
        if b1.button("Re-price", type="primary", use_container_width=True):
            from nhlmodel.slate import price_state
            new = lu.copy()
            for c in choices:
                gi = new.index[(new.team == c["team"]) & (new.pos == "G")]
                if c["goalie"] is not None and len(gi):
                    hit = roster[(roster.team == c["team"]) & (roster.name == c["goalie"])]
                    new.loc[gi, ["player_id", "name"]] = [hit.player_id.iloc[0], c["goalie"]]
                    new.loc[gi, "confirmed"] = c["goalie_confirmed"]
                new.loc[(new.team == c["team"]) & (new.pos != "G"), "confirmed"] = c["lineup_confirmed"]
            with st.spinner("Pricing…"):
                p, _, _ = price_state(state, lineups=new)
            st.session_state.plays = p
            st.session_state.repriced = True
            st.rerun()
        ov = pd.DataFrame([dict(team=c["team"], goalie=c["goalie"] if c["goalie_confirmed"] else "",
                                lineup_confirmed=c["lineup_confirmed"]) for c in choices])
        b2.download_button("Save as override file", ov.to_csv(index=False), file_name=f"{state.date.date()}.csv",
                           mime="text/csv", use_container_width=True,
                           help="Commit this file to overrides/ in the repo so the daily job logs these bets.")

with t_results:
    log = csv("bets_log.csv")
    g = log[log.result.notna()].copy() if "result" in log else pd.DataFrame()
    if g.empty:
        empty("No results yet", "Best bets are logged at the price when first flagged and graded the next morning.")
    else:
        g["date"] = pd.to_datetime(g.date)
        roi = g.profit.mean()
        clv = g.clv_ev.mean() if g.clv_ev.notna().any() else np.nan
        beat = (g.clv_prob > 0).mean() if g.clv_prob.notna().any() else np.nan
        st.markdown(f"""
<div class="tiles">
  <div class="tile"><div class="k">Graded bets</div><div class="v">{len(g):,}</div><div class="d">1 unit each</div></div>
  <div class="tile"><div class="k">Profit</div><div class="v">{g.profit.sum():+.1f}u</div><div class="d">ROI {roi:+.1%}</div></div>
  <div class="tile"><div class="k">CLV</div><div class="v">{'–' if pd.isna(clv) else f'{clv:+.1%}'}</div><div class="d">EV at closing no-vig</div></div>
  <div class="tile"><div class="k">Beat the close</div><div class="v">{'–' if pd.isna(beat) else f'{beat:.0%}'}</div><div class="d">of graded bets</div></div>
</div>""", unsafe_allow_html=True)
        daily = g.groupby("date").profit.sum().cumsum().reset_index(name="units")
        chart = alt.Chart(daily).mark_line(color=ACCENT, strokeWidth=2).encode(
            x=alt.X("date:T", title=None, axis=alt.Axis(grid=False, labelColor="#52514e", domainColor="#d6d5d0")),
            y=alt.Y("units:Q", title="Units", axis=alt.Axis(gridColor="#ecebe7", labelColor="#52514e", domain=False)),
            tooltip=[alt.Tooltip("date:T", title="Date"), alt.Tooltip("units:Q", format="+.2f", title="Units")],
        ).properties(height=240, title=alt.Title("Cumulative profit", anchor="start", color="#0b0b0b", fontSize=14))
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#b9b8b3", strokeDash=[3, 3]).encode(y="y:Q")
        st.altair_chart((zero + chart).configure_view(strokeWidth=0), use_container_width=True)
        by = g.groupby("market").agg(Bets=("profit", "size"), Profit=("profit", "sum"), ROI=("profit", "mean"),
                                     CLV=("clv_ev", "mean")).reset_index()
        by["market"] = by.market.map(MARKET_NAME).fillna(by.market)
        by["ROI"] *= 100; by["CLV"] *= 100
        st.dataframe(by.rename(columns={"market": "Market"}), hide_index=True, use_container_width=True,
                     column_config={"Profit": st.column_config.NumberColumn(format="%+.1f u"),
                                    "ROI": st.column_config.NumberColumn(format="%+.1f%%"),
                                    "CLV": st.column_config.NumberColumn(format="%+.1f%%")})

with t_model:
    ms = csv("market_summary.csv")
    if ms.empty:
        empty("Backtest not run yet", "The morning job runs a walk-forward backtest once data is loaded.")
    else:
        rows = []
        for r in ms[ms.line.astype(str) == "all"].itertuples():
            s = str(r.status)
            cls, icon, lab = (("ok", "✓", "Bet") if s == "OK" else ("warn", "▼", "Downweight")
                              if s.startswith("DOWN") else ("bad", "✕", "Don't bet"))
            better = (1 - r.logloss_model_on_base_rows / r.logloss_base) if r.logloss_base == r.logloss_base else np.nan
            detail = (f"{r.n:,} predictions · {'beats' if better > 0 else 'trails'} {E(str(r.baseline))} by "
                      f"{abs(better):.1%} log loss · calibration error {r.ece:.1%}")
            rows.append(f'<div class="srow"><div><div class="name">{MARKET_NAME.get(r.market, r.market)}</div>'
                        f'<div class="detail">{detail}</div></div><span class="badge {cls}">{icon} {lab}</span></div>')
        st.markdown(f'<div class="card">{"".join(rows)}</div>', unsafe_allow_html=True)
        st.caption("Walk-forward, out-of-sample. Each market is compared with a naive baseline: the closing line "
                   "when odds are available, otherwise the player's season rate or historical frequency.")
        v = fetch("validation.md")
        if v:
            with st.expander("Full validation report"):
                st.markdown(v.decode())
    if meta.get("warnings"):
        with st.expander(f"Assumptions and data notes ({len(meta['warnings'])})"):
            for w in meta["warnings"]:
                st.markdown(f"- {w}")
