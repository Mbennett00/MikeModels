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

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from nhlmodel.pricing import format_american  # noqa: E402
from teams import color, logo_url, nickname  # noqa: E402

APP_VERSION = "v3 · dark"
TAG = "data-latest"
ET = "America/New_York"
SERIES = "#3987e5"

st.set_page_config(page_title="NHL Model", page_icon="🏒", layout="wide", initial_sidebar_state="collapsed")

# ---------------------------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {
  --bg: #0f1116; --surface: #171a21; --surface-2: #1e222b; --border: #272c36; --border-2: #323845;
  --text: #f3f4f6; --text-2: #b4b9c3; --muted: #7d838f; --accent: #3987e5; --accent-soft: rgba(57,135,229,.16);
  --good: #22c55e; --good-text: #4ade80; --good-soft: rgba(34,197,94,.14);
  --warn: #fab219; --warn-soft: rgba(250,178,25,.14); --bad: #f06363; --bad-soft: rgba(240,99,99,.14);
}
html, body, [data-testid="stAppViewContainer"], .stApp { background: var(--bg); }
.stApp, .stApp p, .stApp div, .stApp span, .stApp button, .stApp input { font-family: 'Inter', system-ui, sans-serif; }
[data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer,
[data-testid="stDecoration"], [data-testid="stStatusWidget"] { display: none !important; }
.block-container { max-width: 1120px; padding: 1rem 1rem 4rem; }

/* hero */
.hero { position: relative; overflow: hidden; border-radius: 20px; padding: 22px 22px 18px; margin-bottom: 14px;
        background: radial-gradient(120% 140% at 0% 0%, #1d3b66 0%, #14233b 45%, #121822 100%);
        border: 1px solid #22324a; }
.hero::after { content: ""; position: absolute; right: -60px; top: -60px; width: 240px; height: 240px; border-radius: 50%;
               background: radial-gradient(circle, rgba(57,135,229,.35), transparent 70%); }
.hero .eyebrow { font-size: 12px; font-weight: 700; letter-spacing: .14em; color: #8fb8ee; text-transform: uppercase; }
.hero .title { font-size: 30px; font-weight: 800; color: #fff; margin-top: 4px; letter-spacing: -.02em; }
.hero .kpis { display: flex; gap: 22px; margin-top: 14px; flex-wrap: wrap; position: relative; z-index: 1; }
.hero .kpi .v { font-size: 24px; font-weight: 800; color: #fff; }
.hero .kpi .k { font-size: 12px; color: #a9bddb; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 14px; position: relative; z-index: 1; }
.chip { font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 999px; background: rgba(255,255,255,.08);
        color: #dfe6f0; white-space: nowrap; }
.chip.ok { background: var(--good-soft); color: var(--good-text); }
.chip.warn { background: var(--warn-soft); color: #ffd36b; }
.chip.info { background: var(--accent-soft); color: #9cc5f5; }

/* tabs as a segmented control */
[data-testid="stTabs"] [role="tablist"] { gap: 2px; background: var(--surface); padding: 4px; border-radius: 14px;
    overflow-x: auto; scrollbar-width: none; border: 1px solid var(--border); }
[data-testid="stTabs"] [role="tablist"]::-webkit-scrollbar { display: none; }
[data-testid="stTab"] { height: 36px; padding: 0 16px; border-radius: 10px; background: transparent; flex: 0 0 auto;
    display: flex; align-items: center; cursor: pointer; }
[data-testid="stTab"] p { font-weight: 600; color: var(--muted); font-size: 14px; white-space: nowrap; }
[data-testid="stTab"][aria-selected="true"] { background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--border-2); }
[data-testid="stTab"][aria-selected="true"] p { color: var(--text); }
[data-testid="stTabs"] .react-aria-SelectionIndicator { display: none !important; }

/* generic card */
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr)); gap: 12px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 16px; }
.card.muted { opacity: .72; }
.section { font-size: 12px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .1em;
           margin: 22px 2px 10px; }

/* avatars */
.av { position: relative; flex: 0 0 auto; width: 56px; height: 56px; border-radius: 50%; background: var(--surface-2);
      display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 16px; color: var(--muted);
      box-shadow: inset 0 0 0 2px var(--ring, var(--border-2)); }
.av > img.face { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; border-radius: 50%; }
.av > img.logo { width: 70%; height: 70%; object-fit: contain; position: absolute; }
.av > img.logo.fb::after { border-radius: 50%; }
.av .badge-logo { position: absolute; right: -4px; bottom: -4px; width: 24px; height: 24px; border-radius: 50%;
                  background: var(--surface); box-shadow: 0 0 0 2px var(--surface); display: flex; align-items: center;
                  justify-content: center; overflow: hidden; }
.av .badge-logo img { width: 20px; height: 20px; object-fit: contain; }
/* if an image fails to load, draw its fallback text over the browser's broken-image icon */
img.fb { position: relative; }
img.fb::after { content: attr(data-fb); position: absolute; inset: -3px; display: flex; align-items: center;
                justify-content: center; background: var(--surface-2); color: var(--text-2); font-weight: 700;
                font-size: 13px; border-radius: 50%; }
.game .team img.fb::after { border-radius: 12px; font-size: 14px; }

/* bet card */
.bet { display: flex; gap: 14px; align-items: flex-start; }
.bet .body { flex: 1; min-width: 0; }
.bet .top { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; }
.bet .name { font-size: 17px; font-weight: 700; color: var(--text); line-height: 1.25; }
.bet .what { font-size: 14px; color: var(--text-2); margin-top: 2px; }
.bet .what b { color: var(--text); font-weight: 600; }
.edge { font-size: 16px; font-weight: 800; padding: 6px 10px; border-radius: 10px; white-space: nowrap;
        background: var(--good-soft); color: var(--good-text); }
.edge.neutral { background: var(--surface-2); color: var(--muted); }
.edge small { display: block; font-size: 10px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; opacity: .8; text-align: center; }
.meter { margin-top: 12px; }
.meter .track { position: relative; height: 8px; border-radius: 99px; background: var(--surface-2); }
.meter .fill { position: absolute; top: 0; bottom: 0; border-radius: 99px; background: linear-gradient(90deg, rgba(34,197,94,.35), var(--good)); }
.meter .mark { position: absolute; top: -4px; width: 3px; height: 16px; border-radius: 2px; background: var(--text-2); }
.meter .dot { position: absolute; top: -4px; width: 16px; height: 16px; margin-left: -8px; border-radius: 50%;
              background: var(--good); box-shadow: 0 0 0 3px var(--surface); }
.meter .legend { display: flex; justify-content: space-between; font-size: 12px; color: var(--muted); margin-top: 6px; }
.meter .legend b { color: var(--text); font-weight: 600; }
.stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 12px;
         padding-top: 12px; border-top: 1px solid var(--border); }
.stat .k { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.stat .v { font-size: 16px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.tag { font-size: 12px; padding: 3px 8px; border-radius: 6px; background: var(--surface-2); color: var(--text-2); }
.tag.warn { background: var(--warn-soft); color: #ffd36b; }

/* game card */
.game .head { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 8px; }
.game .team { display: flex; align-items: center; gap: 10px; min-width: 0; }
.game .team.home { justify-content: flex-end; text-align: right; }
.game .team img { width: 46px; height: 46px; object-fit: contain; flex: 0 0 auto; }
.game .abbr { font-size: 12px; color: var(--muted); font-weight: 600; letter-spacing: .06em; }
.game .nick { font-size: 16px; font-weight: 700; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.game .mid { text-align: center; }
.game .score { font-size: 24px; font-weight: 800; color: var(--text); font-variant-numeric: tabular-nums; }
.game .time { font-size: 12px; color: var(--muted); }
.wp { margin: 14px 0 6px; }
.wp .bar { display: flex; height: 10px; border-radius: 99px; overflow: hidden; background: var(--surface-2); gap: 2px; }
.wp .bar div { height: 100%; }
.wp .lab { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-2); margin-top: 6px; }
.wp .lab b { color: var(--text); }
table.mk { width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: tabular-nums; margin-top: 10px;
           border: 0 !important; display: table; }
table.mk th, table.mk td { border-left: 0 !important; border-right: 0 !important; border-top: 0 !important;
                           background: transparent !important; }
table.mk th { text-align: left; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em;
              color: var(--muted); padding: 6px 6px; border-bottom: 1px solid var(--border) !important; }
table.mk td { padding: 8px 6px; border-bottom: 1px solid var(--border) !important; color: var(--text); }
table.mk tr:last-child td { border-bottom: 0 !important; }
table.mk th:not(:first-child), table.mk td:not(:first-child) { text-align: right; }
table.mk td:first-child { font-weight: 600; }
table.mk td.pos { color: var(--good-text); font-weight: 700; }
table.mk td.dim { color: var(--muted); }

/* tiles */
.tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.tile { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 14px 16px; }
.tile .k { font-size: 12px; color: var(--text-2); }
.tile .v { font-size: 28px; font-weight: 800; color: var(--text); margin-top: 2px; }
.tile .d { font-size: 12px; color: var(--muted); }

/* status rows */
.srow { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--border); gap: 10px; }
.srow:last-child { border-bottom: 0; }
.srow .name { font-weight: 700; color: var(--text); }
.srow .detail { font-size: 13px; color: var(--text-2); }
.badge { font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 999px; white-space: nowrap; }
.badge.ok { background: var(--good-soft); color: var(--good-text); }
.badge.warn { background: var(--warn-soft); color: #ffd36b; }
.badge.bad { background: var(--bad-soft); color: #ff8f8f; }

.empty { text-align: center; padding: 30px 18px; color: var(--text-2); }
.empty .big { font-size: 19px; font-weight: 700; color: var(--text); margin-bottom: 6px; }
.steps { margin: 16px auto 0; padding: 0; list-style: none; font-size: 14px; display: inline-block; text-align: left; }
.steps li { margin: 8px 0; padding-left: 26px; position: relative; color: var(--text-2); }
.steps li::before { content: ""; position: absolute; left: 2px; top: 4px; width: 12px; height: 12px; border-radius: 50%;
                    border: 2px solid var(--border-2); }
.steps li.done { color: var(--good-text); }
.steps li.done::before { background: var(--good); border-color: var(--good); }
.steps li.now::before { border-color: var(--accent); box-shadow: 0 0 0 4px var(--accent-soft); }
.foot { text-align: center; color: var(--muted); font-size: 12px; margin-top: 30px; }

@media (max-width: 640px) {
  .block-container { padding: .6rem .6rem 3rem; }
  .grid { grid-template-columns: 1fr; }
  .hero { padding: 18px 16px 14px; border-radius: 16px; }
  .hero .title { font-size: 24px; }
  .hero .kpis { gap: 16px; }
  .hero .kpi .v { font-size: 20px; }
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tile .v { font-size: 22px; }
  .av { width: 48px; height: 48px; }
  .bet .name { font-size: 16px; }
  .game .team img { width: 38px; height: 38px; }
  .game .nick { font-size: 14px; }
  .game .score { font-size: 20px; }
  [data-testid="stTab"] { padding: 0 2px; flex: 1 1 0; justify-content: center; min-width: 0; }
  [data-testid="stTab"] p { font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; }
  [data-testid="stTabs"] [role="tablist"] { overflow-x: hidden; }
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
               "moneyline": "Moneyline", "puckline": "Puck line", "total": "Total goals", "team_total": "Team total",
               "p1_total": "1st period total", "p1_3way": "1st period 3-way"}
UNIT = {"sog": "shots", "assists": "assists", "points": "points", "goals": "goals"}


def teams_of(matchup: str):
    away, home = str(matchup).split(" @ ")
    return home, away


def bet_text(r) -> str:
    """What the bet is, e.g. 'Over 2.5 shots' or 'Bruins -1.5'."""
    home, away = teams_of(r.matchup)
    m, s, ln = r.market, str(r.selection), r.line
    team = lambda x: home if x.startswith("home") else (away if x.startswith("away") else "Draw")
    if m in UNIT:
        if m == "goals" and ln == 0.5:
            return "Anytime goal scorer" if s == "over" else "No goal"
        return f"{'Over' if s == 'over' else 'Under'} {ln:g} {UNIT[m]}"
    if m == "moneyline":
        return f"{nickname(team(s))} to win"
    if m == "puckline":
        return f"{nickname(team(s))} {ln:+g}"
    if m == "total":
        return f"{'Over' if s == 'over' else 'Under'} {ln:g} goals"
    if m == "team_total":
        return f"{nickname(team(s))} {'over' if s.endswith('over') else 'under'} {ln:g}"
    if m == "p1_total":
        return f"1st period {'over' if s == 'over' else 'under'} {ln:g}"
    if m == "p1_3way":
        return f"1st period: {nickname(team(s)) if s != 'draw' else 'tie'}"
    return f"{m} {s} {ln}"


def bet_team(r):
    home, away = teams_of(r.matchup)
    s = str(r.selection)
    if isinstance(getattr(r, "team", None), str) and r.team:
        return r.team
    if s.startswith("home"):
        return home
    if s.startswith("away"):
        return away
    return home


def fmt_time(x):
    t = pd.to_datetime(x, utc=True, errors="coerce")
    return "" if pd.isna(t) else t.tz_convert(ET).strftime("%-I:%M %p")


def pct(p, d=0):
    return "–" if p is None or pd.isna(p) else f"{100 * p:.{d}f}%"


def am(x):
    return "–" if x is None or pd.isna(x) else format_american(x)


def initials(name: str) -> str:
    parts = [p for p in str(name).split() if p]
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) > 1 else str(name)[:3].upper()


def avatar(r) -> str:
    team = bet_team(r)
    ring = color(team)
    if r.market in UNIT and str(getattr(r, "player", "")):
        face = getattr(r, "headshot", "")
        face = face if isinstance(face, str) and face.startswith("http") else ""
        return (f'<div class="av" style="--ring:{ring}"><span>{E(initials(r.player))}</span>'
                + (f'<img class="face fb" data-fb="{E(initials(r.player))}" src="{E(face)}" alt="" loading="lazy">'
                   if face else "")
                + f'<div class="badge-logo"><img class="fb" data-fb="" src="{logo_url(team)}" alt=""></div></div>')
    return (f'<div class="av" style="--ring:{ring}"><span>{E(team)}</span>'
            f'<img class="logo fb" data-fb="{E(team)}" src="{logo_url(team)}" alt="" loading="lazy"></div>')


def prep(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    d = df.copy()
    for c in ("player", "team", "headshot", "flags"):
        if c not in d:
            d[c] = ""
        d[c] = d[c].fillna("")
    d["bet"] = [bet_text(r) for r in d.itertuples()]
    d["time"] = [fmt_time(x) for x in d.get("start_utc", pd.Series([None] * len(d)))]
    d["confirmed"] = d.confirmed.astype(bool)
    return d


def meter(p_model, p_book) -> str:
    if pd.isna(p_book):
        return (f'<div class="meter"><div class="track"><div class="dot" style="left:{100 * p_model:.1f}%"></div></div>'
                f'<div class="legend"><span>Model <b>{pct(p_model, 1)}</b></span><span>no book line</span></div></div>')
    lo, hi = sorted((p_model, p_book))
    return (f'<div class="meter"><div class="track">'
            f'<div class="fill" style="left:{100 * lo:.1f}%;width:{100 * (hi - lo):.1f}%"></div>'
            f'<div class="mark" style="left:{100 * p_book:.1f}%"></div>'
            f'<div class="dot" style="left:{100 * p_model:.1f}%"></div></div>'
            f'<div class="legend"><span>Model <b>{pct(p_model, 1)}</b></span><span>Book (no-vig) <b>{pct(p_book, 1)}</b></span></div></div>')


def bet_card(r, muted=False) -> str:
    edge = r.edge
    edge_html = (f'<div class="edge"><small>edge</small>+{100 * edge:.1f}%</div>' if pd.notna(edge) and edge > 0
                 else f'<div class="edge neutral"><small>edge</small>{pct(edge, 1) if pd.notna(edge) else "–"}</div>')
    home, away = teams_of(r.matchup)
    who = r.player if r.market in UNIT and r.player else f"{away} @ {home}"
    tags = []
    if not r.confirmed:
        tags.append('<span class="tag warn">⚠ Lineup or goalie not confirmed</span>')
    if r.confidence == "low":
        tags.append('<span class="tag">Low confidence · thin or single-book market</span>')
    for n in [x.strip() for x in str(r.flags).split(";") if x.strip()][:2]:
        tags.append(f'<span class="tag">{E(n)}</span>')
    try:
        proj_v = f"{float(r.projection):.2f}"
    except (TypeError, ValueError):
        proj_v = "–"
    third_k = "Projection" if r.market in UNIT else "Market"
    third_v = proj_v if r.market in UNIT else E(MARKET_NAME.get(r.market, r.market))
    return f"""
<div class="card{' muted' if muted else ''}"><div class="bet">
  {avatar(r)}
  <div class="body">
    <div class="top"><div><div class="name">{E(who)}</div>
      <div class="what"><b>{E(r.bet)}</b> · {E(r.matchup)}{' · ' + E(r.time) if r.time else ''}</div></div>{edge_html}</div>
    {meter(r.p_model, r.p_novig)}
    <div class="stats">
      <div class="stat"><div class="k">Best price</div><div class="v">{am(r.best_price)}</div></div>
      <div class="stat"><div class="k">Fair odds</div><div class="v">{am(r.fair_odds)}</div></div>
      <div class="stat"><div class="k">{third_k}</div><div class="v">{third_v}</div></div>
    </div>
    {'<div class="tags">' + ''.join(tags) + '</div>' if tags else ''}
  </div></div></div>"""


def empty(title, body=""):
    st.markdown(f'<div class="card empty"><div class="big">{E(title)}</div>{body}</div>', unsafe_allow_html=True)


def footer():
    st.markdown(f'<div class="foot">NHL Model {APP_VERSION} · data from the NHL API · logos and headshots © NHL</div>',
                unsafe_allow_html=True)


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
flagged = plays[plays.flag.astype(bool)].sort_values("edge", ascending=False) if len(plays) else plays
pending = (plays[(~plays.confirmed) & (plays.edge >= plays.threshold)].sort_values("edge", ascending=False)
           if len(plays) else plays)

# ---------------------------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------------------------
if meta.get("date"):
    d = pd.Timestamp(meta["date"])
    eyebrow = "Next slate" if meta.get("upcoming") else "Tonight"
    title = d.strftime("%A, %B %-d")
else:
    eyebrow, title = "NHL Model", "Getting ready"
chips = []
if meta.get("generated_at"):
    chips.append(f'<span class="chip">Updated {pd.Timestamp(meta["generated_at"]).strftime("%-I:%M %p")} ET</span>')
if meta.get("date"):
    chips.append('<span class="chip ok">● Odds live</span>' if meta.get("odds_rows") else
                 '<span class="chip warn">No odds yet</span>')
    if meta.get("teams"):
        c, n = meta.get("teams_confirmed", 0), meta["teams"]
        chips.append(f'<span class="chip {"ok" if c == n else "warn"}">Lineups {c}/{n} confirmed</span>')
if st.session_state.repriced:
    chips.append('<span class="chip info">Re-priced with your lineups</span>')
kpis = ""
if len(plays):
    top = flagged.edge.max() if len(flagged) else np.nan
    kpis = f"""<div class="kpis">
      <div class="kpi"><div class="v">{meta.get('games', plays.game_id.nunique())}</div><div class="k">games</div></div>
      <div class="kpi"><div class="v">{len(flagged)}</div><div class="k">best bets</div></div>
      <div class="kpi"><div class="v">{'–' if pd.isna(top) else f'+{100 * top:.1f}%'}</div><div class="k">top edge</div></div>
      <div class="kpi"><div class="v">{len(pending)}</div><div class="k">awaiting lineups</div></div></div>"""
st.markdown(f"""<div class="hero"><div class="eyebrow">{E(eyebrow)}</div><div class="title">{E(title)}</div>
{kpis}<div class="chips">{''.join(chips)}</div></div>""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------------------------
# Setup state
# ---------------------------------------------------------------------------------------------
if plays.empty:
    games = int(status.get("games_stored", 0) or 0)
    loaded = games > 1500
    steps = [("Data pipeline connected", "done"),
             (f"Historical games loaded ({games:,})" if games else "Loading two seasons of NHL games (about an hour on the first run)",
              "done" if loaded else "now"),
             ("Model backtested and first slate priced", "done" if meta.get("generated_at") else ("now" if loaded else ""))]
    items = "".join(f'<li class="{c}">{E(t)}</li>' for t, c in steps)
    msg = ("No regular-season games scheduled in the next few weeks." if meta.get("generated_at") else
           "The daily job is building the data. This page fills in by itself when it's done.")
    empty("Almost there", f'<div>{E(msg)}</div><ul class="steps">{items}</ul>')
    footer()
    st.stop()

# ---------------------------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------------------------
t_best, t_games, t_props, t_lineups, t_results, t_model = st.tabs(
    ["Bets", "Games", "Props", "Lineups", "Results", "Model"])

with t_best:
    if len(flagged):
        st.markdown('<div class="grid">' + "".join(bet_card(r) for r in flagged.itertuples()) + "</div>",
                    unsafe_allow_html=True)
    else:
        why = []
        if not meta.get("odds_rows"):
            why.append("No sportsbook odds yet, so there's nothing to compare against. Add the <b>ODDS_API_KEY</b> "
                       "secret in GitHub, or wait for lines to post.")
        if len(pending):
            why.append(f"{len(pending)} edges are waiting on confirmed lineups and goalies (below, or the Lineups tab).")
        if not why:
            why.append("Nothing clears the edge threshold right now.")
        empty("No best bets yet", "<br>".join(why))
    if len(pending):
        st.markdown(f'<div class="section">Waiting on confirmation · {len(pending)}</div>', unsafe_allow_html=True)
        st.markdown('<div class="grid">' + "".join(bet_card(r, muted=True) for r in pending.head(16).itertuples())
                    + "</div>", unsafe_allow_html=True)

with t_games:
    games = plays[plays.player == ""]
    cards = []
    for gid, g in games.groupby("game_id", sort=False):
        r0 = g.iloc[0]
        home, away = teams_of(r0.matchup)
        ml = g[g.market == "moneyline"]
        mlh = ml[ml.selection == "home"]
        ph = float(mlh.p_model.iloc[0]) if len(mlh) else np.nan
        proj = str(ml.projection.iloc[0]) if len(ml) else ""
        try:   # "HOME 2.83 - 2.33 AWAY (...)"
            parts = proj.split(" (")[0].split(" - ")
            s_home, s_away = parts[0].split()[-1], parts[1].split()[0]
        except (IndexError, ValueError):
            s_home = s_away = "–"

        def rows(sel):
            out = []
            for r in sel.itertuples():
                cls = ("pos" if pd.notna(r.edge) and r.edge >= r.threshold else
                       "dim" if pd.isna(r.edge) or r.edge < 0 else "")
                out.append(f"<tr><td>{E(r.bet)}</td><td>{pct(r.p_model, 1)}</td><td>{am(r.fair_odds)}</td>"
                           f"<td>{am(r.best_price)}</td><td class='{cls}'>"
                           f"{f'{100 * r.edge:+.1f}%' if pd.notna(r.edge) else '–'}</td></tr>")
            return "".join(out)

        fav_home = (ph if ph == ph else .5) >= .5
        pl = g[g.market == "puckline"]
        pl = pl[((pl.selection == ("home" if fav_home else "away")) & (pl.line == -1.5)) |
                ((pl.selection == ("away" if fav_home else "home")) & (pl.line == 1.5))]
        tl = g[g.market == "total"]
        ln = (tl[tl.best_price.notna()].line.mode().iloc[0] if tl.best_price.notna().any() else 6.5) if len(tl) else None
        body = rows(pd.concat([ml.sort_values("selection", ascending=False), pl,
                               tl[tl.line == ln].sort_values("selection") if ln is not None else tl.iloc[:0]]))
        wp = ""
        if ph == ph:
            wp = (f'<div class="wp"><div class="bar"><div style="width:{100 * (1 - ph):.1f}%;background:{color(away)}"></div>'
                  f'<div style="width:{100 * ph:.1f}%;background:{color(home)}"></div></div>'
                  f'<div class="lab"><span><b>{pct(1 - ph)}</b> {E(away)}</span><span>win probability</span>'
                  f'<span>{E(home)} <b>{pct(ph)}</b></span></div></div>')
        cards.append(f"""
<div class="card game">
  <div class="head">
    <div class="team"><img class="fb" data-fb="{E(away)}" src="{logo_url(away)}" alt=""><div><div class="abbr">{E(away)}</div><div class="nick">{E(nickname(away))}</div></div></div>
    <div class="mid"><div class="score">{E(s_away)} – {E(s_home)}</div><div class="time">{E(r0.time) or 'projected'}</div></div>
    <div class="team home"><div><div class="abbr">{E(home)}</div><div class="nick">{E(nickname(home))}</div></div><img class="fb" data-fb="{E(home)}" src="{logo_url(home)}" alt=""></div>
  </div>
  {wp}
  <table class="mk"><tr><th>Bet</th><th>Model</th><th>Fair</th><th>Best</th><th>Edge</th></tr>{body}</table>
</div>""")
    st.markdown('<div class="grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)
    st.caption("Projected score is expected regulation goals (empty-net and OT goals come on top).")

with t_props:
    props = plays[plays.player != ""]
    if props.empty:
        empty("No props priced")
    else:
        c1, c2, c3 = st.columns([2, 2, 1.3])
        q = c1.text_input("Player", placeholder="Search a player", label_visibility="collapsed")
        mk = c2.segmented_control("Market", ["Shots", "Goals", "Assists", "Points"], default="Shots",
                                  label_visibility="collapsed") or "Shots"
        only_lines = c3.toggle("Has book line", value=bool(props.best_price.notna().any()))
        key = {"Shots": "sog", "Goals": "goals", "Assists": "assists", "Points": "points"}[mk]
        d = props[props.market == key]
        if q:
            d = d[d.player.str.contains(q, case=False, na=False)]
        d = d[d.best_price.notna()] if only_lines else d[d.selection == "over"]
        d = d.sort_values(["edge", "p_model"], ascending=False)
        view = pd.DataFrame({
            "": d.headshot.where(d.headshot.str.startswith("http"), None),
            "Player": d.player, "Team": d.team,
            "Bet": [("Over " if s == "over" else "Under ") + f"{l:g}" for s, l in zip(d.selection, d.line)],
            "Edge": d.edge * 100, "Best": d.best_price.map(am), "Model": d.p_model * 100,
            "Fair": d.fair_odds.map(am), "Proj": pd.to_numeric(d.projection, errors="coerce"),
            "Game": d.matchup, "Lineup": np.where(d.confirmed, "✓", "–")})
        st.dataframe(view, hide_index=True, use_container_width=True, height=min(640, 40 + 44 * len(view)),
                     row_height=44, column_config={
                         "": st.column_config.ImageColumn(width="small"),
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
        st.caption("Projected lineups come from each team's last game and starters from recent starts. Confirm what "
                   "you know, then re-price. Only confirmed teams can produce best bets.")
        choices = []
        for gm in state.schedule.itertuples():
            with st.expander(f"{gm.away}  @  {gm.home}", expanded=False):
                cols = st.columns(2)
                for col, team in zip(cols, (gm.away, gm.home)):
                    goalies = roster[(roster.team == team) & (roster.pos == "G")]
                    cur = lu[(lu.team == team) & (lu.pos == "G")]
                    names = list(dict.fromkeys(goalies.name))
                    idx = names.index(cur.name.iloc[0]) if len(cur) and cur.name.iloc[0] in names else 0
                    col.markdown(f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
                                 f'<img class="fb" data-fb="{E(team)}" src="{logo_url(team)}" style="width:32px;height:32px" alt="">'
                                 f'<b>{E(nickname(team))}</b></div>', unsafe_allow_html=True)
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
  <div class="tile"><div class="k">Closing line value</div><div class="v">{'–' if pd.isna(clv) else f'{clv:+.1%}'}</div><div class="d">EV at the closing price</div></div>
  <div class="tile"><div class="k">Beat the close</div><div class="v">{'–' if pd.isna(beat) else f'{beat:.0%}'}</div><div class="d">of graded bets</div></div>
</div>""", unsafe_allow_html=True)
        daily = g.groupby("date").profit.sum().cumsum().reset_index(name="units")
        base = alt.Chart(daily).encode(x=alt.X("date:T", title=None,
                                               axis=alt.Axis(grid=False, labelColor="#b4b9c3", domainColor="#323845",
                                                             tickColor="#323845")))
        area = base.mark_area(color=SERIES, opacity=.15).encode(y="units:Q")
        line = base.mark_line(color=SERIES, strokeWidth=2).encode(
            y=alt.Y("units:Q", title="Units", axis=alt.Axis(gridColor="#232833", labelColor="#b4b9c3", domain=False,
                                                          titleColor="#7d838f")),
            tooltip=[alt.Tooltip("date:T", title="Date"), alt.Tooltip("units:Q", format="+.2f", title="Units")])
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#4a5160", strokeDash=[3, 3]).encode(y="y:Q")
        st.altair_chart((area + zero + line).properties(height=250, background="#171a21", padding=12,
                                                        title=alt.Title("Cumulative profit", anchor="start",
                                                                        color="#f3f4f6", fontSize=14))
                        .configure_view(strokeWidth=0), use_container_width=True)
        by = g.groupby("market").agg(Bets=("profit", "size"), Profit=("profit", "sum"), ROI=("profit", "mean"),
                                     CLV=("clv_ev", "mean")).reset_index()
        by["market"] = by.market.map(MARKET_NAME).fillna(by.market)
        by["ROI"] *= 100
        by["CLV"] *= 100
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

footer()
