"""NHL Model dashboard (Streamlit). Designed phone-first, works on desktop.

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

import numpy as np
import pandas as pd
import requests
import streamlit as st

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from nhlmodel.pricing import format_american  # noqa: E402
from teams import color, nickname  # noqa: E402

APP_VERSION = "v6 · price sheet"


def _build() -> str:
    """Short git commit of the running code, so it's obvious which version is deployed."""
    import subprocess
    try:
        return subprocess.run(["git", "-C", HERE, "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, timeout=5).stdout.strip() or "?"
    except Exception:
        return "?"


BUILD = _build()
TAG = "data-latest"
ET = "America/New_York"

st.set_page_config(page_title="NHL Model", page_icon="🏒", layout="centered", initial_sidebar_state="collapsed")

# ---------------------------------------------------------------------------------------------
# Style: icy rink background, cream cards, thick navy outlines, offset "sticker" shadows
# ---------------------------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600;700&family=Nunito:wght@500;600;700;800&display=swap');
:root {
  --ice: #bfe0f2; --ice-2: #d7ecf8; --cream: #fffaf0; --navy: #1f3448; --ink: #1f3448; --ink-2: #4d5d6c;
  --muted: #7a8894; --red: #d9443a; --red-soft: #fbe3df; --gold: #e2ae45; --gold-soft: #fbefd2;
  --green: #2e8b57; --green-soft: #def2e5; --line: #e7dfcf;
}
html, body, .stApp, [data-testid="stAppViewContainer"] {
  background:
    linear-gradient(90deg, transparent calc(50% - 2px), rgba(217,68,58,.10) calc(50% - 2px), rgba(217,68,58,.10) calc(50% + 2px), transparent calc(50% + 2px)),
    radial-gradient(120% 80% at 50% 0%, #d9eefa 0%, var(--ice) 60%, #a9d4ec 100%) fixed;
}
.stApp { font-family: 'Nunito', system-ui, sans-serif; color: var(--ink); }
.stMarkdown, .stMarkdown p, .stMarkdown div, .stMarkdown span:not([data-testid="stIconMaterial"]), .stApp label p,
.stApp input, .stApp button p, [data-testid="stExpander"] summary p {
  font-family: 'Nunito', system-ui, sans-serif;
}
[data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer, [data-testid="stDecoration"],
[data-testid="stStatusWidget"] { display: none !important; }
.block-container { max-width: 760px; padding: 1.1rem 1rem 4rem; }
h1, h2, h3, .display { font-family: 'Fredoka', 'Nunito', sans-serif !important; letter-spacing: -.01em; }

/* sticker card */
.card { background: var(--cream); border: 3px solid var(--navy); border-radius: 26px; padding: 18px 20px;
        box-shadow: 6px 7px 0 var(--navy); margin: 0 6px 20px 0; }
.card.soft { box-shadow: 4px 5px 0 var(--navy); }
.card.dim { opacity: .82; }

/* header */
.top { display: flex; align-items: center; gap: 16px; }
.puck { font-size: 46px; line-height: 1; filter: drop-shadow(3px 4px 0 rgba(31,52,72,.25)); }
.top h1 { font-size: 28px; margin: 0; padding: 0; line-height: 1.1; color: var(--navy); }
.top .sub { color: var(--ink-2); font-size: 15px; margin-top: 2px; font-weight: 700; }
.pills { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
.pill { display: inline-flex; align-items: center; gap: 6px; font-weight: 800; font-size: 14px; padding: 5px 12px;
        border-radius: 999px; border: 2.5px solid var(--navy); background: var(--cream); color: var(--navy); white-space: nowrap; }
.pill.gold { background: var(--gold); }
.pill.green { background: var(--green-soft); }
.pill.red { background: var(--red-soft); }

/* tabs = pill row */
[data-testid="stTabs"] [role="tablist"] { gap: 8px; background: transparent; border: 0; padding: 2px 6px 10px 0;
    overflow-x: auto; scrollbar-width: none; }
[data-testid="stTabs"] [role="tablist"]::-webkit-scrollbar { display: none; }
[data-testid="stTab"] { height: 42px; padding: 0 18px; border-radius: 999px; border: 2.5px solid var(--navy);
    background: var(--cream); flex: 0 0 auto; display: flex; align-items: center; box-shadow: 3px 3px 0 var(--navy); }
[data-testid="stTab"] p { font-family: 'Fredoka', sans-serif !important; font-weight: 600; font-size: 16px; color: var(--navy); }
[data-testid="stTab"][aria-selected="true"] { background: var(--navy); }
[data-testid="stTab"][aria-selected="true"] p { color: var(--cream) !important; }
[data-testid="stTabs"] .react-aria-SelectionIndicator { display: none !important; }
[data-testid="stTabs"] [role="tablist"]::after { display: none; }

.h2 { font-family: 'Fredoka', sans-serif; font-weight: 600; font-size: 24px; color: var(--navy);
      display: flex; align-items: center; gap: 10px; margin: 8px 0 12px; }
.count { font-family: 'Nunito', sans-serif; font-size: 14px; font-weight: 800; background: var(--gold);
         border-radius: 999px; padding: 3px 12px; color: #6b3d0c; }
.note { color: var(--ink-2); font-size: 15px; margin: -4px 0 14px; }

/* avatars */
.av { position: relative; flex: 0 0 auto; width: 58px; height: 58px; border-radius: 50%; background: var(--ice-2);
      border: 3px solid var(--navy); display: flex; align-items: center; justify-content: center;
      font-family: 'Fredoka', sans-serif; font-weight: 600; color: var(--navy); overflow: visible; }
.av > img.face { position: absolute; inset: 0; width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
.av > img.logo { position: absolute; width: 74%; height: 74%; object-fit: contain; }
.av .mini { position: absolute; right: -8px; bottom: -6px; width: 28px; height: 28px; border-radius: 50%;
            background: var(--cream); border: 2.5px solid var(--navy); display: flex; align-items: center; justify-content: center; overflow: hidden; }
.av .mini img { width: 22px; height: 22px; object-fit: contain; }

/* pick card */
.pick { display: flex; gap: 14px; align-items: center; }
.pick .body { flex: 1; min-width: 0; }
.pick .who { font-family: 'Fredoka', sans-serif; font-weight: 600; font-size: 20px; line-height: 1.15; color: var(--navy); }
.pick .bet { font-size: 16px; font-weight: 700; color: var(--ink-2); margin-top: 2px; }
.pick .odds { font-family: 'Fredoka', sans-serif; font-weight: 700; font-size: 22px; padding: 6px 12px; border-radius: 16px;
              border: 2.5px solid var(--navy); background: var(--gold); color: var(--navy); white-space: nowrap; box-shadow: 3px 3px 0 var(--navy); }
.tagrow { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 12px; }
.strength { font-weight: 800; font-size: 14px; padding: 5px 12px; border-radius: 999px; border: 2px solid var(--navy); }
.strength.hot { background: var(--red); color: #fff; }
.strength.solid { background: var(--green-soft); color: #1d5a37; }
.strength.wait { background: var(--gold-soft); color: #6b3d0c; }
.meta { font-size: 14px; color: var(--muted); font-weight: 700; }
.card details { margin-top: 10px; }
.card details summary { cursor: pointer; font-weight: 800; color: var(--navy); font-size: 14px; list-style: none; }
.card details summary::-webkit-details-marker { display: none; }
.card details summary::before { content: "▸ "; }
.card details[open] summary::before { content: "▾ "; }
.why { margin-top: 8px; font-size: 15px; color: var(--ink-2); line-height: 1.5; }
.why b { color: var(--navy); }
.vs { margin-top: 8px; }
.vs .row { display: flex; align-items: center; gap: 10px; font-size: 14px; font-weight: 700; margin: 5px 0; }
.vs .lab { width: 64px; color: var(--ink-2); }
.vs .bar { flex: 1; height: 12px; border-radius: 99px; background: #efe7d6; border: 2px solid var(--navy); overflow: hidden; }
.vs .bar div { height: 100%; }
.vs .num { width: 44px; text-align: right; }

/* game tile */
.game .teams { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 6px; }
.game .t { display: flex; flex-direction: column; align-items: center; gap: 4px; text-align: center; }
.game .t img { width: 64px; height: 64px; object-fit: contain; }
.game .t .code { width: 64px; height: 64px; border-radius: 18px; border: 2.5px solid var(--navy); background: var(--ice-2);
                 display: flex; align-items: center; justify-content: center; font-family: 'Fredoka', sans-serif; font-weight: 600; }
.game .t .nm { font-family: 'Fredoka', sans-serif; font-weight: 600; font-size: 18px; color: var(--navy); }
.game .t .g { font-size: 13px; color: var(--muted); font-weight: 700; }
.game .mid { text-align: center; }
.game .mid .at { font-family: 'Fredoka', sans-serif; font-size: 15px; color: var(--muted); }
.game .mid .time { font-weight: 800; font-size: 15px; color: var(--navy); }
.wp { margin-top: 14px; }
.wp .bar { display: flex; height: 16px; border-radius: 99px; overflow: hidden; border: 2.5px solid var(--navy); gap: 2px; background: var(--navy); }
.wp .lab { display: flex; justify-content: space-between; margin-top: 6px; font-weight: 800; font-size: 15px; }
.proj { text-align: center; color: var(--ink-2); font-size: 15px; margin-top: 10px; }
.proj b { font-family: 'Fredoka', sans-serif; color: var(--navy); font-size: 18px; }
table.mk { width: 100%; border-collapse: collapse; font-size: 15px; margin-top: 8px; border: 0 !important; display: table; }
table.mk th, table.mk td { border: 0 !important; border-bottom: 2px solid var(--line) !important; background: transparent !important;
                           padding: 8px 4px; }
table.mk th { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); text-align: left; }
table.mk tr:last-child td { border-bottom: 0 !important; }
table.mk th:not(:first-child), table.mk td:not(:first-child) { text-align: right; }
table.mk td:first-child { font-weight: 800; color: var(--navy); }
table.mk td.good { color: var(--green); font-weight: 800; }

/* prop rows */
.prow { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 2px dashed var(--line); }
.prow:last-child { border-bottom: 0; }
.prow .av { width: 46px; height: 46px; border-width: 2.5px; }
.prow .body { flex: 1; min-width: 0; }
.prow .nm { font-weight: 800; font-size: 16px; color: var(--navy); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.prow .bt { font-size: 14px; color: var(--ink-2); font-weight: 700; }
.prow .right { text-align: right; }
.prow .price { font-family: 'Fredoka', sans-serif; font-weight: 700; font-size: 18px; }
.prow .edge { font-size: 13px; font-weight: 800; color: var(--green); }
.prow .edge.neg { color: var(--muted); }

/* record */
.big { font-family: 'Fredoka', sans-serif; font-weight: 700; font-size: 46px; line-height: 1.05; color: var(--green); }
.big.neg { color: var(--red); }
.bigsub { color: var(--ink-2); font-size: 16px; font-weight: 700; margin-bottom: 18px; }
.status { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 2px dashed var(--line); gap: 10px; }
.status:last-child { border-bottom: 0; }
.status .nm { font-weight: 800; font-size: 16px; }
.status .d { font-size: 13px; color: var(--muted); font-weight: 700; }

.empty { text-align: center; }
.empty .e { font-size: 44px; }
.empty .t { font-family: 'Fredoka', sans-serif; font-weight: 600; font-size: 22px; margin: 6px 0; color: var(--navy); }
.empty .s { color: var(--ink-2); font-size: 16px; }
.steps { list-style: none; padding: 0; margin: 14px auto 0; display: inline-block; text-align: left; }
.steps li { margin: 8px 0; font-weight: 700; color: var(--ink-2); }
.foot { text-align: center; color: #56708a; font-size: 13px; font-weight: 700; margin-top: 26px; }

/* Streamlit widgets in the same style */
[data-testid="stTextInput"] input { background: var(--cream) !important; border-radius: 999px !important; }
[data-testid="stTextInput"] > div > div, [data-baseweb="select"] > div {
  border: 2.5px solid var(--navy) !important; border-radius: 999px !important; background: var(--cream) !important; }
[data-testid="stExpander"] details { background: var(--cream); border: 3px solid var(--navy) !important; border-radius: 22px;
  box-shadow: 4px 5px 0 var(--navy); margin-right: 6px; }
.stButton button, .stDownloadButton button { border: 2.5px solid var(--navy) !important; border-radius: 999px !important;
  box-shadow: 3px 3px 0 var(--navy); font-weight: 800 !important; }
.stButton button[kind="primary"] { background: var(--gold) !important; color: var(--navy) !important; }
.stButton button[kind="secondary"], .stDownloadButton button { background: var(--cream) !important; color: var(--navy) !important; }
[data-testid="stButtonGroup"] button { border: 2.5px solid var(--navy) !important; border-radius: 999px !important;
  background: var(--cream) !important; font-weight: 800; margin-right: 4px; }
[data-testid="stButtonGroup"] button[aria-checked="true"] { background: var(--navy) !important; }
[data-testid="stButtonGroup"] button[aria-checked="true"] p { color: var(--cream) !important; }

@media (max-width: 640px) {
  .block-container { padding: .8rem .7rem 3rem; }
  .card { padding: 16px 16px; border-radius: 22px; box-shadow: 5px 6px 0 var(--navy); }
  .top h1 { font-size: 22px; }
  .puck { font-size: 36px; }
  .pill { font-size: 13px; padding: 4px 10px; }
  .pick .who { font-size: 18px; }
  .pick .odds { font-size: 19px; padding: 5px 10px; }
  .av { width: 52px; height: 52px; }
  .game .t img { width: 54px; height: 54px; }
  .big { font-size: 40px; }
  [data-testid="stTab"] { height: 36px; padding: 0 9px; }
  [data-testid="stTab"] p { font-size: 13.5px; }
  [data-testid="stTabs"] [role="tablist"] { gap: 6px; }
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
    return {a["name"]: a["url"] for a in r.json().get("assets", [])} if r.status_code == 200 else {}


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
# Images: downloaded by this server, shrunk and embedded, so the phone never hotlinks NHL/ESPN
# ---------------------------------------------------------------------------------------------
UA = {"User-Agent": "Mozilla/5.0 (nhlmodel dashboard)"}
ESPN_ABBR = {"LAK": "la", "NJD": "nj", "SJS": "sj", "TBL": "tb", "UTA": "utah"}


def _embed_one(url: str, size: int) -> str:
    import base64
    if not url:
        return ""
    try:
        r = requests.get(url, headers=UA, timeout=8)
    except requests.RequestException:
        return ""
    if r.status_code != 200 or not r.content:
        return ""
    ctype = r.headers.get("content-type", "")
    if "svg" in ctype or url.endswith(".svg"):
        return "data:image/svg+xml;base64," + base64.b64encode(r.content).decode()
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(r.content)).convert("RGBA")
        im.thumbnail((size, size))
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
    except Exception:
        data = r.content
    return "data:image/png;base64," + base64.b64encode(data).decode()


@st.cache_data(ttl=86400, show_spinner=False, max_entries=5000)
def embed_many(urls: tuple, size: int) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=12) as ex:
        return dict(zip(urls, ex.map(lambda u: _embed_one(u, size), urls)))


IMAGES = {}


def team_logo_url(team: str) -> str:
    return IMAGES.get("logos", {}).get(team) or \
        f"https://a.espncdn.com/i/teamlogos/nhl/500/{ESPN_ABBR.get(team, team.lower())}.png"


LOGO: dict = {}
FACE: dict = {}


def load_images(teams, faces):
    """Fetch every logo and headshot the page needs in one parallel, cached call."""
    LOGO.update({t: v for t, v in zip(teams, (embed_many(tuple(team_logo_url(t) for t in teams), 160).get(team_logo_url(t), "")
                                               for t in teams))})
    urls = tuple(sorted({u for u in faces if isinstance(u, str) and u.startswith("http")}))
    FACE.update(embed_many(urls, 132) if urls else {})


def logo_img(team: str, cls: str = "", style: str = "") -> str:
    src = LOGO.get(team, "")
    if src:
        return f'<img class="{cls}" src="{src}" style="{style}" alt="{E(team)}">'
    return f'<div class="code" style="{style}">{E(team)}</div>'


# ---------------------------------------------------------------------------------------------
# Words, not numbers
# ---------------------------------------------------------------------------------------------
E = html.escape
MARKET = {"goals": "Anytime goal", "sog": "Shots on goal", "assists": "Assists", "points": "Points",
          "moneyline": "Moneyline", "puckline": "Puck line", "total": "Total goals", "team_total": "Team total",
          "p1_total": "1st period total", "p1_3way": "1st period winner"}
UNIT = {"sog": "shots", "assists": "assists", "points": "points", "goals": "goals"}


def teams_of(matchup: str):
    away, home = str(matchup).split(" @ ")
    return home, away


def bet_text(r) -> str:
    home, away = teams_of(r.matchup)
    m, s, ln = r.market, str(r.selection), r.line
    team = lambda x: home if x.startswith("home") else (away if x.startswith("away") else "Tie")
    if m in UNIT:
        if m == "goals" and ln == 0.5:
            return "Scores a goal" if s == "over" else "Doesn't score"
        return f"{'Over' if s == 'over' else 'Under'} {ln:g} {UNIT[m]}"
    if m == "moneyline":
        return f"{nickname(team(s))} win"
    if m == "puckline":
        return f"{nickname(team(s))} {ln:+g}"
    if m == "total":
        return f"{'Over' if s == 'over' else 'Under'} {ln:g} total goals"
    if m == "team_total":
        return f"{nickname(team(s))} {'over' if s.endswith('over') else 'under'} {ln:g} goals"
    if m == "p1_total":
        return f"1st period {'over' if s == 'over' else 'under'} {ln:g}"
    if m == "p1_3way":
        return f"1st period: {nickname(team(s)) if s != 'draw' else 'tied'}"
    return f"{m} {s} {ln}"


def bet_team(r):
    home, away = teams_of(r.matchup)
    if isinstance(getattr(r, "team", None), str) and r.team:
        return r.team
    s = str(r.selection)
    return away if s.startswith("away") else home


def fmt_time(x):
    t = pd.to_datetime(x, utc=True, errors="coerce")
    return "" if pd.isna(t) else t.tz_convert(ET).strftime("%-I:%M %p")


def pct(p):
    return "–" if p is None or pd.isna(p) else f"{100 * p:.0f}%"


def am(x):
    return "–" if x is None or pd.isna(x) else format_american(x)


def initials(name: str) -> str:
    parts = [p for p in str(name).split() if p]
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) > 1 else str(name)[:3].upper()


def avatar(r, small=False) -> str:
    team = bet_team(r)
    if r.market in UNIT and r.player:
        face = FACE.get(r.headshot, "") if isinstance(r.headshot, str) else ""
        img = f'<img class="face" src="{face}" alt="">' if face else ""
        mini = "" if small or not LOGO.get(team) else f'<div class="mini"><img src="{LOGO[team]}" alt=""></div>'
        return f'<div class="av"><span>{"" if face else E(initials(r.player))}</span>{img}{mini}</div>'
    lg = LOGO.get(team, "")
    return (f'<div class="av"><span>{"" if lg else E(team)}</span>'
            + (f'<img class="logo" src="{lg}" alt="">' if lg else "") + "</div>")


def empty(emoji, title, sub="", extra=""):
    st.markdown(f'<div class="card empty"><div class="e">{emoji}</div><div class="t">{E(title)}</div>'
                f'<div class="s">{sub}</div>{extra}</div>', unsafe_allow_html=True)


def prep(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    d = df.copy()
    for c in ("player", "team", "headshot", "flags"):
        d[c] = d[c].fillna("") if c in d else ""
    d["bet"] = [bet_text(r) for r in d.itertuples()]
    d["time"] = [fmt_time(x) for x in d.get("start_utc", pd.Series([None] * len(d)))]
    d["confirmed"] = d.confirmed.astype(bool)
    return d



st.markdown("""
<style>
.howto { background: var(--gold-soft); border: 2.5px dashed var(--navy); border-radius: 18px; padding: 10px 14px;
         font-size: 14px; font-weight: 700; color: var(--ink); margin: 0 6px 16px 0; }
table.px { width: 100%; border-collapse: collapse; font-size: 15px; margin-top: 10px; border: 0 !important; display: table; }
table.px th, table.px td { border: 0 !important; border-bottom: 2px solid var(--line) !important; background: transparent !important;
                           padding: 9px 4px; }
table.px th { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); text-align: left; }
table.px tr:last-child td { border-bottom: 0 !important; }
table.px th:not(:first-child), table.px td:not(:first-child) { text-align: right; white-space: nowrap; }
table.px td:first-child { font-weight: 800; color: var(--navy); }
table.px td.tgt { font-family: 'Fredoka', sans-serif; font-weight: 700; color: var(--green); }
.chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.lc { border: 2px solid var(--navy); border-radius: 12px; padding: 4px 9px; background: #fff; font-size: 13px; font-weight: 700; }
.lc b { font-family: 'Fredoka', sans-serif; }
.lc .t { color: var(--green); font-weight: 800; }
.verdict { font-family: 'Fredoka', sans-serif; font-weight: 700; font-size: 30px; margin-bottom: 6px; }
.verdict.good { color: var(--green); } .verdict.meh { color: #9a6a12; } .verdict.bad { color: var(--red); }
.vline { font-size: 16px; font-weight: 700; color: var(--ink-2); margin: 4px 0; }
.vline b { color: var(--navy); }
.gl { display: flex; justify-content: space-between; gap: 8px; margin-top: 10px; font-size: 14px; font-weight: 700; }
.gl .g { flex: 1; }
.gl .g.r { text-align: right; }
.gl .st { display: inline-block; font-size: 12px; font-weight: 800; padding: 1px 8px; border-radius: 999px;
          border: 2px solid var(--navy); margin-top: 3px; }
.gl .st.ok { background: var(--green-soft); } .gl .st.lk { background: var(--gold-soft); } .gl .st.un { background: #eee; }
.inj { margin-top: 10px; font-size: 13px; color: var(--ink-2); font-weight: 700; line-height: 1.5; }
.inj b { color: var(--red); }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------------------------
from nhlmodel.pricing import american_to_decimal, american_to_prob, fair_american  # noqa: E402

meta, status = js("meta.json"), js("status.json")
plays_raw = csv("plays.csv")
if "plays" not in st.session_state or st.session_state.get("plays_src") != meta.get("generated_at"):
    st.session_state.plays = plays_raw
    st.session_state.plays_src = meta.get("generated_at")
    st.session_state.repriced = False
    st.session_state.lineups = None
    st.session_state.games = {}
plays = prep(st.session_state.plays)
if len(plays) and "target_odds" not in plays:
    thr = plays.threshold if "threshold" in plays else 0.03
    plays["target_odds"] = [fair_american(p) if p >= 0.02 else np.nan for p in plays.p_model - thr]
IMAGES.update(js("images.json"))
if len(plays):
    with st.spinner("Loading logos and headshots…"):
        load_images(sorted({t for m in plays.matchup.unique() for t in teams_of(m)}), plays.headshot.unique())
blob = fetch("slate_state.pkl")
SAVED = pickle.loads(blob) if blob else None
NEWS = js("news.json")


def goalie_line(team):
    """(name, status) for the starter: user choice > Daily Faceoff > projection."""
    lu = st.session_state.get("lineups")
    lu = lu if lu is not None else (SAVED["state"].lineups if SAVED else None)
    name, status = "", ""
    if lu is not None:
        g = lu[(lu.team == team) & (lu.pos == "G")]
        if len(g):
            name = str(g["name"].iloc[0])
            status = (g.status.iloc[0] if "status" in g and isinstance(g.status.iloc[0], str) and g.status.iloc[0]
                      else ("Confirmed" if bool(g.confirmed.iloc[0]) else "Projected"))
            if st.session_state.get("repriced") and bool(g.confirmed.iloc[0]):
                status = "Confirmed"
    if not name and team in NEWS.get("goalies", {}):
        name, status = NEWS["goalies"][team]["goalie"], NEWS["goalies"][team]["status"]
    return name, status


def goalie_html(team, right=False):
    name, status = goalie_line(team)
    if not name:
        return f'<div class="g{" r" if right else ""}">🥅 TBD</div>'
    cls, icon = {"Confirmed": ("ok", "✅"), "Likely": ("lk", "🟡")}.get(status, ("un", "❔"))
    return (f'<div class="g{" r" if right else ""}">🥅 {E(name)}<br>'
            f'<span class="st {cls}">{icon} {E(status or "Projected")}</span></div>')


def injuries_html(teams):
    items = [i for i in NEWS.get("injuries", []) if i["team"] in teams]
    if not items:
        return ""
    parts = []
    for t in teams:
        mine = [i for i in items if i["team"] == t]
        if mine:
            parts.append(f"{E(t)}: " + ", ".join(f'{E(i["name"])} <b>{E(i["status"])}</b>' for i in mine))
    return f'<div class="inj">🚑 {" · ".join(parts)}</div>'



def bet_at(x):
    return "–" if pd.isna(x) or x < -1500 else format_american(x)


# ---------------------------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------------------------
if meta.get("date"):
    d = pd.Timestamp(meta["date"])
    title = "Next up" if meta.get("upcoming") else "Tonight"
    sub = f"{d.strftime('%a, %b %-d')} · {meta.get('games', 0)} games"
    if meta.get("generated_at"):
        sub += f" · updated {pd.Timestamp(meta['generated_at']).strftime('%-I:%M %p')}"
else:
    title, sub = "Getting set up", "Warming up the Zamboni"
pills = []
if len(plays):
    pills.append('<span class="pill gold">💲 Fair prices ready</span>')
    if meta.get("teams"):
        c, n = meta.get("teams_confirmed", 0), meta["teams"]
        pills.append(f'<span class="pill{" green" if c == n else ""}">🥅 Goalies {c}/{n} confirmed</span>')
if st.session_state.get("repriced"):
    pills.append('<span class="pill green">Updated with your lineups</span>')
st.markdown(f"""<div class="card"><div class="top"><div class="puck">🏒</div>
<div><h1>{E(title)}</h1><div class="sub">{E(sub)}</div></div></div>
<div class="pills">{''.join(pills)}</div></div>""", unsafe_allow_html=True)

if plays.empty:
    games = int(status.get("games_stored", 0) or 0)
    steps = [("✅", "Connected to the NHL"),
             ("✅" if games > 1500 else "⏳", f"Loaded {games:,} past games" if games else "Loading past games (about an hour)"),
             ("✅" if meta.get("generated_at") else "⏳", "Tonight's prices calculated")]
    items = "".join(f"<li>{i} {E(t)}</li>" for i, t in steps)
    empty("🧊", "Almost game time", "This page fills itself in once the first run finishes.",
          f'<ul class="steps">{items}</ul>')
    st.stop()

HOWTO = ('💡 Bet it if DraftKings pays the <span style="color:var(--green)">green “bet at”</span> price or better. '
         'Not sure? Use <b>Check</b>.')

t_games, t_players, t_check, t_lineups, t_model = st.tabs(["Tonight", "Players", "Check", "Lineups", "Model"])

# ---------------------------------------------------------------------------------------------
# Tonight: game price sheet
# ---------------------------------------------------------------------------------------------
with t_games:
    st.markdown(f'<div class="howto">{HOWTO}</div>', unsafe_allow_html=True)
    games = plays[plays.player == ""]
    cards = []
    for gid, g in games.groupby("game_id", sort=False):
        r0 = g.iloc[0]
        home, away = teams_of(r0.matchup)
        ml = g[g.market == "moneyline"]
        mlh = ml[ml.selection == "home"]
        ph = float(mlh.p_model.iloc[0]) if len(mlh) else np.nan
        try:
            parts = str(ml.projection.iloc[0]).split(" (")[0].split(" - ")
            s_home, s_away = float(parts[0].split()[-1]), float(parts[1].split()[0])
            proj_html = (f'<div class="proj">Projected score · <b>{E(away)} {s_away:.1f}</b> – '
                         f'<b>{s_home:.1f} {E(home)}</b></div>')
        except (IndexError, ValueError):
            proj_html = ""

        def rows(sel):
            return "".join(f"<tr><td>{E(r.bet)}</td><td>{pct(r.p_model)}</td><td>{am(r.fair_odds)}</td>"
                           f"<td class='tgt'>{bet_at(r.target_odds)}</td></tr>" for r in sel.itertuples())

        pl = g[(g.market == "puckline")]
        main = pd.concat([ml.sort_values("selection"),
                          pl[((pl.selection == "away") & (pl.line == 1.5)) | ((pl.selection == "home") & (pl.line == -1.5))],
                          pl[((pl.selection == "away") & (pl.line == -1.5)) | ((pl.selection == "home") & (pl.line == 1.5))],
                          g[(g.market == "total") & (g.line == 6.5)].sort_values("selection")])
        more = pd.concat([g[(g.market == "total") & (g.line.isin([5.5, 6.0]))].sort_values(["line", "selection"]),
                          g[g.market == "team_total"].sort_values(["selection", "line"]),
                          g[g.market == "p1_total"].sort_values("selection"),
                          g[g.market == "p1_3way"]])
        head = "<tr><th>Bet</th><th>Chance</th><th>Fair</th><th>Bet at</th></tr>"
        wp = ""
        if ph == ph:
            wp = (f'<div class="wp"><div class="bar"><div style="width:{100 * (1 - ph):.1f}%;background:{color(away)}"></div>'
                  f'<div style="width:{100 * ph:.1f}%;background:{color(home)}"></div></div>'
                  f'<div class="lab"><span>{pct(1 - ph)}</span><span style="color:var(--muted)">chance to win</span>'
                  f'<span>{pct(ph)}</span></div></div>')
        cards.append(f"""
<div class="card game">
  <div class="teams">
    <div class="t">{logo_img(away)}<div class="nm">{E(nickname(away))}</div><div class="g">{E(away)}</div></div>
    <div class="mid"><div class="at">at</div><div class="time">{E(r0.time) or ''}</div></div>
    <div class="t">{logo_img(home)}<div class="nm">{E(nickname(home))}</div><div class="g">{E(home)}</div></div>
  </div>
  <div class="gl">{goalie_html(away)}{goalie_html(home, right=True)}</div>
  {wp}{proj_html}{injuries_html([away, home])}
  <table class="px">{head}{rows(main)}</table>
  <details><summary>More bets (other totals, team totals, 1st period)</summary>
  <table class="px">{head}{rows(more)}</table></details>
</div>""")
    st.markdown("".join(cards), unsafe_allow_html=True)

# ---------------------------------------------------------------------------------------------
# Players: projections and prices to beat
# ---------------------------------------------------------------------------------------------
PLAYER_LINES = {"sog": [1.5, 2.5, 3.5, 4.5], "goals": [0.5], "points": [0.5, 1.5], "assists": [0.5]}
with t_players:
    props = plays[(plays.player != "") & (plays.selection == "over")]
    if props.empty:
        empty("👤", "No player projections yet")
    else:
        c1, c2 = st.columns([1, 1])
        q = c1.text_input("Find a player", placeholder="🔍  Find a player", label_visibility="collapsed")
        gsel = c2.selectbox("Game", ["All games"] + list(props.matchup.unique()), label_visibility="collapsed")
        mk = st.segmented_control("Market", ["Shots", "Goals", "Points", "Assists"], default="Shots",
                                  label_visibility="collapsed") or "Shots"
        key = {"Shots": "sog", "Goals": "goals", "Assists": "assists", "Points": "points"}[mk]
        d = props[props.market == key]
        if q:
            d = d[d.player.str.contains(q, case=False, na=False)]
        if gsel != "All games":
            d = d[d.matchup == gsel]
        d = d.assign(lam=pd.to_numeric(d.projection, errors="coerce"))
        order = d.groupby("player_id").lam.first().sort_values(ascending=False).index[:40]
        rows = []
        for pid in order:
            dp = d[d.player_id == pid].sort_values("line")
            r = dp.iloc[0]
            chips = "".join(
                f'<span class="lc"><b>{"Scores" if key == "goals" else "O " + f"{x.line:g}"}</b> · {pct(x.p_model)} · '
                f'<span class="t">bet at {bet_at(x.target_odds)}</span></span>'
                for x in dp.itertuples() if x.line in PLAYER_LINES[key])
            proj = f"{r.lam:.2f} {UNIT[key]}" if key != "goals" else f"{r.lam:.2f} expected goals"
            rows.append(f'<div class="prow" style="align-items:flex-start">{avatar(r, small=True)}<div class="body">'
                        f'<div class="nm">{E(r.player)}</div><div class="bt">{E(r.team)} · projects {E(proj)}'
                        f'{"" if r.confirmed else " · lineup projected"}</div><div class="chips">{chips}</div></div></div>')
        st.markdown(f'<div class="howto">{HOWTO}</div><div class="card soft">{"".join(rows) or "No matches"}</div>',
                    unsafe_allow_html=True)

# ---------------------------------------------------------------------------------------------
# Check a bet against a DraftKings price
# ---------------------------------------------------------------------------------------------
MKTS_GAME = {"Moneyline": "moneyline", "Puck line": "puckline", "Total goals": "total", "Team total": "team_total",
             "1st period total": "p1_total", "1st period winner": "p1_3way"}


def game_projection(home, away):
    """Recompute the game model for any line, with the current (possibly user-confirmed) goalies."""
    from nhlmodel.team_model import TeamModel
    key = (home, away)
    cache = st.session_state.setdefault("games", {})
    if key not in cache and SAVED:
        state = SAVED["state"]
        lu = st.session_state.get("lineups")
        lu = state.lineups if lu is None else lu

        def goalie(team):
            g = lu[(lu.team == team) & (lu.pos == "G")]
            return (g.player_id.iloc[0], bool(g.confirmed.iloc[0])) if len(g) else (None, False)
        (hg, hc), (ag, ac) = goalie(home), goalie(away)
        cache[key] = TeamModel(state.cfg, state.snap, state.params).project(home, away, hg, ag, state.date, (hc, ac))
    return cache.get(key)


def parse_odds(s: str):
    s = str(s).strip().replace(" ", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if abs(v) >= 100 else None


with t_check:
    st.markdown('<div class="note">Pick a bet, type the DraftKings odds, and we\'ll tell you if it\'s worth it.</div>',
                unsafe_allow_html=True)
    matchups = list(dict.fromkeys(plays.matchup))
    gm = st.selectbox("Game", matchups, format_func=lambda m: f"{nickname(teams_of(m)[1])} @ {nickname(teams_of(m)[0])}")
    home, away = teams_of(gm)
    kind = st.segmented_control("Type", ["Game bet", "Player prop"], default="Game bet",
                                label_visibility="collapsed") or "Game bet"
    p_model, label, market = None, "", None
    if kind == "Game bet":
        mname = st.selectbox("Bet type", list(MKTS_GAME))
        market = MKTS_GAME[mname]
        c1, c2 = st.columns(2)
        if market in ("moneyline", "p1_3way"):
            opts = [away, home] + (["Tie"] if market == "p1_3way" else [])
            side = c1.selectbox("Pick", opts, format_func=lambda t: nickname(t) if t != "Tie" else "Tied after 1st")
            sel = "draw" if side == "Tie" else ("home" if side == home else "away")
            line = np.nan
            label = f"{nickname(side) if side != 'Tie' else 'Tie'} {'to win' if market == 'moneyline' else 'after 1st period'}"
        elif market == "puckline":
            side = c1.selectbox("Team", [away, home], format_func=nickname)
            line = c2.selectbox("Spread", [-1.5, 1.5, -2.5, 2.5], format_func=lambda x: f"{x:+g}")
            sel = "home" if side == home else "away"
            label = f"{nickname(side)} {line:+g}"
        elif market == "team_total":
            side = c1.selectbox("Team", [away, home], format_func=nickname)
            ou = c2.selectbox("Over/Under", ["Over", "Under"])
            line = st.number_input("Line", value=3.5 if side == home else 2.5, step=0.5, format="%.1f")
            sel = f"{'home' if side == home else 'away'}_{ou.lower()}"
            label = f"{nickname(side)} {ou.lower()} {line:g}"
        else:
            ou = c1.selectbox("Over/Under", ["Over", "Under"])
            line = c2.number_input("Line", value=6.5 if market == "total" else 1.5, step=0.5, format="%.1f")
            sel = ou.lower()
            label = f"{'1st period ' if market == 'p1_total' else ''}{ou} {line:g} goals"
        gp = game_projection(home, away)
        if gp is not None:
            from nhlmodel.slate import _game_prob
            try:
                p_model = float(_game_prob(gp, market, sel, float(line) if line == line else np.nan))
            except (ValueError, KeyError):
                p_model = None
    else:
        pp = plays[(plays.matchup == gm) & (plays.player != "")]
        sog = pp[pp.market == "sog"].assign(lam=lambda x: pd.to_numeric(x.projection, errors="coerce"))
        names = list(sog.groupby("player").lam.first().sort_values(ascending=False).index)
        names += [n for n in pp.player.unique() if n not in names]
        who = st.selectbox("Player", names, format_func=lambda n: f"{n} ({pp[pp.player == n].team.iloc[0]})")
        c1, c2, c3 = st.columns(3)
        mname = c1.selectbox("Prop", ["Shots", "Goals", "Points", "Assists"])
        market = {"Shots": "sog", "Goals": "goals", "Assists": "assists", "Points": "points"}[mname]
        ou = c2.selectbox("Over/Under", ["Over", "Under"])
        line = c3.number_input("Line", value={"sog": 2.5}.get(market, 0.5), step=1.0, format="%.1f")
        row = pp[(pp.player == who) & (pp.market == market)]
        if len(row) and SAVED:
            from nhlmodel.player_model import player_market_prob
            lam = float(pd.to_numeric(row.projection, errors="coerce").iloc[0])
            col = {"goals": "lam_goals", "sog": "lam_sog", "assists": "lam_ast", "points": "lam_pts"}[market]
            p_over = player_market_prob({col: lam, "pos": row.pos.iloc[0] if "pos" in row else "F"},
                                        market, float(line), SAVED["state"].params)
            p_model = p_over if ou == "Over" else 1 - p_over
        label = f"{who}: {ou.lower()} {line:g} {UNIT[market]}"
    dk = st.text_input("DraftKings odds", placeholder="e.g. +140 or -115")
    odds = parse_odds(dk)
    if p_model is None:
        empty("🤔", "Can't price that one", "This game or player isn't in tonight's model.")
    elif odds is None:
        st.markdown(f'<div class="card"><div class="vline">{E(label)}</div>'
                    f'<div class="vline">Our chance: <b>{pct(p_model)}</b> · fair price <b>{am(fair_american(p_model))}</b></div>'
                    f'<div class="vline">Type DraftKings\' odds above to check it.</div></div>', unsafe_allow_html=True)
    else:
        from nhlmodel.config import DEFAULT
        thr = DEFAULT.edge_threshold.get(market, 0.03)
        implied = american_to_prob(odds)
        cut = 0.08 if market in UNIT else 0.045   # DK's usual two-way cut: ~8% on props, ~4.5% on game lines
        book = implied / (1 + cut / 2)
        edge = p_model - book
        ev = p_model * (american_to_decimal(odds) - 1) * 100 - (1 - p_model) * 100
        if edge >= thr:
            cls, verdict = "good", "✅ Bet it"
        elif edge > 0:
            cls, verdict = "meh", "🤏 Small edge. Pass or bet small"
        else:
            cls, verdict = "bad", "❌ Pass"
        st.markdown(f"""<div class="card"><div class="verdict {cls}">{verdict}</div>
<div class="vline">{E(label)} at <b>{format_american(odds)}</b></div>
<div class="vs"><div class="row"><span class="lab">Model</span><div class="bar"><div style="width:{100 * p_model:.0f}%;background:var(--green)"></div></div><span class="num">{pct(p_model)}</span></div>
<div class="row"><span class="lab">DK</span><div class="bar"><div style="width:{100 * book:.0f}%;background:var(--muted)"></div></div><span class="num">{pct(book)}</span></div></div>
<div class="vline">Edge <b>{100 * edge:+.1f} pts</b> · expected profit <b>{'+' if ev >= 0 else '−'}${abs(ev):.2f}</b> per $100</div>
<div class="vline">Fair price <b>{am(fair_american(p_model))}</b> · bet at <b>{bet_at(fair_american(p_model - thr)) if p_model - thr > .02 else '–'}</b> or better</div>
</div>""", unsafe_allow_html=True)
        st.caption("DK's chance removes its usual cut (about 4.5% on game lines, 8% on props). Lineups and goalies "
                   "are projected unless confirmed in the Lineups tab.")

# ---------------------------------------------------------------------------------------------
# Lineups
# ---------------------------------------------------------------------------------------------
with t_lineups:
    if not SAVED:
        empty("📋", "Lineups aren't ready yet")
    else:
        state, roster = SAVED["state"], SAVED["roster"]
        lu = (state.lineups if st.session_state.get("lineups") is None else st.session_state.lineups).copy()
        st.markdown('<div class="note">Heard who\'s starting? Set the goalie, flip the switches, then tap '
                    '<b>Update prices</b>.</div>', unsafe_allow_html=True)
        choices = []
        for gm_ in state.schedule.itertuples():
            with st.expander(f"{nickname(gm_.away)}  @  {nickname(gm_.home)}", expanded=False):
                for team in (gm_.away, gm_.home):
                    goalies = roster[(roster.team == team) & (roster.pos == "G")]
                    cur = lu[(lu.team == team) & (lu.pos == "G")]
                    names = list(dict.fromkeys(goalies.name))
                    idx = names.index(cur.name.iloc[0]) if len(cur) and cur.name.iloc[0] in names else 0
                    st.markdown('<div style="display:flex;align-items:center;gap:10px;margin:6px 0">'
                                + logo_img(team, style="width:36px;height:36px;font-size:12px;border-radius:10px")
                                + f'<span style="font-family:Fredoka,sans-serif;font-weight:600;font-size:18px">'
                                  f'{E(nickname(team))}</span></div>', unsafe_allow_html=True)
                    gname = st.selectbox("Starting goalie", names, index=idx, key=f"g_{gm_.game_id}_{team}") if names else None
                    c1, c2 = st.columns(2)
                    gconf = c1.toggle("Goalie confirmed", key=f"gc_{gm_.game_id}_{team}",
                                      value=bool(cur.confirmed.iloc[0]) if len(cur) else False)
                    lconf = c2.toggle("Lineup confirmed", key=f"lc_{gm_.game_id}_{team}",
                                      value=bool(lu[(lu.team == team) & (lu.pos != "G")].confirmed.all()))
                    choices.append(dict(team=team, goalie=gname, goalie_confirmed=gconf, lineup_confirmed=lconf))
        if st.button("🔄  Update prices", type="primary", use_container_width=True):
            from nhlmodel.slate import price_state
            new = lu.copy()
            for c in choices:
                gi = new.index[(new.team == c["team"]) & (new.pos == "G")]
                if c["goalie"] is not None and len(gi):
                    hit = roster[(roster.team == c["team"]) & (roster.name == c["goalie"])]
                    new.loc[gi, ["player_id", "name"]] = [hit.player_id.iloc[0], c["goalie"]]
                    new.loc[gi, "confirmed"] = c["goalie_confirmed"]
                new.loc[(new.team == c["team"]) & (new.pos != "G"), "confirmed"] = c["lineup_confirmed"]
            with st.spinner("Crunching…"):
                p, _, _ = price_state(state, lineups=new)
            if "headshot" in st.session_state.plays and "headshot" in p:
                hs = dict(zip(st.session_state.plays.player_id, st.session_state.plays.headshot))
                p["headshot"] = [hs.get(x, h) for x, h in zip(p.player_id, p.headshot)]
            st.session_state.plays = p
            st.session_state.lineups = new
            st.session_state.games = {}
            st.session_state.repriced = True
            st.rerun()
        ov = pd.DataFrame([dict(team=c["team"], goalie=c["goalie"] if c["goalie_confirmed"] else "",
                                lineup_confirmed=c["lineup_confirmed"]) for c in choices])
        st.download_button("💾  Save confirmations for everyone", ov.to_csv(index=False),
                           file_name=f"{state.date.date()}.csv", mime="text/csv", use_container_width=True,
                           help="Commit this file to overrides/ in the repo; the next run uses it for everyone.")

# ---------------------------------------------------------------------------------------------
# Model: how much to trust each market
# ---------------------------------------------------------------------------------------------
with t_model:
    ms = csv("market_summary.csv")
    if len(ms):
        rows = []
        for r in ms[ms.line.astype(str) == "all"].itertuples():
            s = str(r.status)
            icon, lab = (("✅", "Trust it") if s == "OK" else ("⚠️", "Bet smaller") if s.startswith("DOWN")
                         else ("⛔", "Skip it"))
            rows.append(f'<div class="status"><div><div class="nm">{MARKET.get(r.market, r.market)}</div>'
                        f'<div class="d">tested on {r.n:,} past predictions</div></div>'
                        f'<span class="pill">{icon} {lab}</span></div>')
        st.markdown(f'<div class="card"><div class="h2" style="margin-top:0">How much to trust each market</div>'
                    f'<div class="note">Based on how the model did on past games it never saw.</div>'
                    f'{"".join(rows)}</div>', unsafe_allow_html=True)
        v = fetch("validation.md")
        if v:
            with st.expander("🤓 The nerdy details"):
                st.markdown(v.decode())
    else:
        empty("📈", "Backtest not run yet")
    if meta.get("warnings"):
        with st.expander("ℹ️ Data notes"):
            for w in meta["warnings"]:
                st.markdown(f"- {w}")

st.markdown(f'<div class="foot">🏒 NHL Model {APP_VERSION} · build {BUILD} · data from the NHL · bet responsibly</div>',
            unsafe_allow_html=True)
