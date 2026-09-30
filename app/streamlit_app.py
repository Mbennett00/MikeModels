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

APP_VERSION = "v4 · rink"
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
[data-testid="stButtonGroup"] button[kind="segmented_controlActive"] { background: var(--navy) !important; }
[data-testid="stButtonGroup"] button[kind="segmented_controlActive"] p { color: var(--cream) !important; }

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


def strength(r):
    """Plain-English label instead of an edge number."""
    if not r.confirmed:
        return "wait", "⏳ Waiting on lineup"
    if pd.notna(r.edge) and r.edge >= 2 * r.threshold:
        return "hot", "🚨 Goal-light pick"
    return "solid", "✅ Solid value"


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


def pick_card(r) -> str:
    cls, label = strength(r)
    home, away = teams_of(r.matchup)
    who = r.player if r.market in UNIT and r.player else f"{nickname(away)} @ {nickname(home)}"
    when = f"{away} @ {home}" + (f" · {r.time}" if r.time else "")
    book = r.p_novig
    why = (f"Our model gives this a <b>{pct(r.p_model)}</b> chance. The sportsbook's price implies "
           f"<b>{pct(book)}</b> (with its cut removed). That gap is the edge: <b>+{100 * r.edge:.1f} points</b>."
           if pd.notna(book) else f"Our model gives this a <b>{pct(r.p_model)}</b> chance. No book price yet.")
    extra = f" Fair price would be <b>{am(r.fair_odds)}</b>."
    if r.market in UNIT:
        try:
            extra += f" Projection: <b>{float(r.projection):.2f} {UNIT[r.market]}</b>."
        except (TypeError, ValueError):
            pass
    bars = ""
    if pd.notna(book):
        bars = (f'<div class="vs"><div class="row"><span class="lab">Model</span><div class="bar"><div style="width:{100 * r.p_model:.0f}%;background:var(--green)"></div></div><span class="num">{pct(r.p_model)}</span></div>'
                f'<div class="row"><span class="lab">Book</span><div class="bar"><div style="width:{100 * book:.0f}%;background:var(--muted)"></div></div><span class="num">{pct(book)}</span></div></div>')
    notes = [x.strip() for x in str(r.flags).split(";") if x.strip() and "UNCONFIRMED" not in x]
    if r.confidence == "low":
        notes.append("thin market or only one sportsbook: size down")
    note_html = "".join(f"<div>• {E(n)}</div>" for n in notes[:3])
    return f"""
<div class="card{' dim' if cls == 'wait' else ''}">
  <div class="pick">{avatar(r)}
    <div class="body"><div class="who">{E(who)}</div><div class="bet">{E(r.bet)}</div></div>
    <div class="odds">{am(r.best_price)}</div>
  </div>
  <div class="tagrow"><span class="strength {cls}">{label}</span><span class="meta">{E(when)}</span></div>
  <details><summary>Why this pick?</summary><div class="why">{why}{extra}{bars}{note_html}</div></details>
</div>"""


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
IMAGES = js("images.json")
if len(plays):
    with st.spinner("Loading logos and headshots…"):
        _teams = sorted({t for m in plays.matchup.unique() for t in teams_of(m)})
        load_images(_teams, plays.headshot.unique())
if len(plays):
    over = plays[plays.edge >= plays.threshold].sort_values("edge", ascending=False)
    ready = over[over.confirmed]
    waiting = over[~over.confirmed]
else:
    ready = waiting = plays

# ---------------------------------------------------------------------------------------------
# Header card
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
    pills.append(f'<span class="pill gold">🎯 {len(ready)} pick{"s" if len(ready) != 1 else ""}</span>')
    if len(waiting):
        pills.append(f'<span class="pill">⏳ {len(waiting)} on deck</span>')
if meta.get("date") and not meta.get("odds_rows"):
    pills.append('<span class="pill red">No sportsbook odds yet</span>')
if st.session_state.repriced:
    pills.append('<span class="pill green">Re-priced with your lineups</span>')
st.markdown(f"""<div class="card"><div class="top"><div class="puck">🏒</div>
<div><h1>{E(title)}</h1><div class="sub">{E(sub)}</div></div></div>
<div class="pills">{''.join(pills)}</div></div>""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------------------------
# Setup state
# ---------------------------------------------------------------------------------------------
if plays.empty:
    games = int(status.get("games_stored", 0) or 0)
    steps = [("✅", "Connected to the NHL"),
             ("✅" if games > 1500 else "⏳", f"Loaded {games:,} past games" if games else "Loading past games (about an hour)"),
             ("✅" if meta.get("generated_at") else "⏳", "Tonight's picks priced")]
    items = "".join(f"<li>{i} {E(t)}</li>" for i, t in steps)
    empty("🧊", "Almost game time", "This page fills itself in once the first run finishes.",
          f'<ul class="steps">{items}</ul>')
    st.stop()

# ---------------------------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------------------------
t_picks, t_games, t_props, t_lineups, t_record = st.tabs(["Picks", "Games", "Props", "Lineups", "Record"])

with t_picks:
    if len(ready):
        st.markdown(f'<div class="h2">Tonight\'s picks <span class="count">{len(ready)}</span></div>'
                    '<div class="note">Bets where our price beats the sportsbook by enough to matter.</div>',
                    unsafe_allow_html=True)
        st.markdown("".join(pick_card(r) for r in ready.itertuples()), unsafe_allow_html=True)
    else:
        why = ("Lines aren't posted yet." if not meta.get("odds_rows") else
               "We only make picks once starting goalies and lineups are confirmed. "
               "Confirm them in the 📋 Lineups tab, or check back closer to puck drop."
               if len(waiting) else "Nothing beats the sportsbook by enough tonight. No bet is a good bet.")
        empty("🥅", "No picks yet", E(why))
    if len(waiting):
        st.markdown(f'<div class="h2">On deck <span class="count">{len(waiting)}</span></div>'
                    '<div class="note">Look good on paper, but lineups or goalies aren\'t confirmed yet.</div>',
                    unsafe_allow_html=True)
        st.markdown("".join(pick_card(r) for r in waiting.head(12).itertuples()), unsafe_allow_html=True)

with t_games:
    games = plays[plays.player == ""]
    out = []
    for gid, g in games.groupby("game_id", sort=False):
        r0 = g.iloc[0]
        home, away = teams_of(r0.matchup)
        ml = g[g.market == "moneyline"]
        mlh = ml[ml.selection == "home"]
        ph = float(mlh.p_model.iloc[0]) if len(mlh) else np.nan
        proj = str(ml.projection.iloc[0]) if len(ml) else ""
        try:
            parts = proj.split(" (")[0].split(" - ")
            s_home, s_away = float(parts[0].split()[-1]), float(parts[1].split()[0])
            proj_html = f'<div class="proj">Projected score · <b>{E(away)} {s_away:.1f}</b> – <b>{s_home:.1f} {E(home)}</b></div>'
        except (IndexError, ValueError):
            proj_html = ""
        fav_home = (ph if ph == ph else .5) >= .5
        pl = g[g.market == "puckline"]
        pl = pl[((pl.selection == ("home" if fav_home else "away")) & (pl.line == -1.5)) |
                ((pl.selection == ("away" if fav_home else "home")) & (pl.line == 1.5))]
        tl = g[g.market == "total"]
        ln = (tl[tl.best_price.notna()].line.mode().iloc[0] if tl.best_price.notna().any() else 6.5) if len(tl) else None
        sel = pd.concat([ml.sort_values("selection", ascending=False), pl,
                         tl[tl.line == ln].sort_values("selection") if ln is not None else tl.iloc[:0]])
        rows = "".join(
            f"<tr><td>{E(r.bet)}</td><td>{pct(r.p_model)}</td><td>{am(r.best_price)}</td>"
            f"<td class='{'good' if pd.notna(r.edge) and r.edge >= r.threshold else ''}'>"
            f"{('✅ ' if pd.notna(r.edge) and r.edge >= r.threshold else '') + (f'{100 * r.edge:+.0f}' if pd.notna(r.edge) else '–')}</td></tr>"
            for r in sel.itertuples())
        n_picks = int(((g.edge >= g.threshold) & g.confirmed).sum())
        wp = ""
        if ph == ph:
            wp = (f'<div class="wp"><div class="bar"><div style="width:{100 * (1 - ph):.1f}%;background:{color(away)}"></div>'
                  f'<div style="width:{100 * ph:.1f}%;background:{color(home)}"></div></div>'
                  f'<div class="lab"><span>{pct(1 - ph)}</span><span style="color:var(--muted)">chance to win</span><span>{pct(ph)}</span></div></div>')
        out.append(f"""
<div class="card game">
  <div class="teams">
    <div class="t">{logo_img(away)}<div class="nm">{E(nickname(away))}</div><div class="g">{E(away)}</div></div>
    <div class="mid"><div class="at">at</div><div class="time">{E(r0.time) or ''}</div></div>
    <div class="t">{logo_img(home)}<div class="nm">{E(nickname(home))}</div><div class="g">{E(home)}</div></div>
  </div>
  {wp}{proj_html}
  <details><summary>Full breakdown{f' · {n_picks} pick' + ('s' if n_picks != 1 else '') if n_picks else ''}</summary>
  <table class="mk"><tr><th>Bet</th><th>Model</th><th>Price</th><th>Edge</th></tr>{rows}</table></details>
</div>""")
    st.markdown("".join(out), unsafe_allow_html=True)

with t_props:
    props = plays[plays.player != ""]
    if props.empty:
        empty("👤", "No player props yet")
    else:
        q = st.text_input("Find a player", placeholder="🔍  Find a player", label_visibility="collapsed")
        mk = st.segmented_control("Market", ["Shots", "Goals", "Points", "Assists"], default="Shots",
                                  label_visibility="collapsed") or "Shots"
        key = {"Shots": "sog", "Goals": "goals", "Assists": "assists", "Points": "points"}[mk]
        d = props[props.market == key]
        if q:
            d = d[d.player.str.contains(q, case=False, na=False)]
        with_line = d[d.best_price.notna()]
        d = with_line if len(with_line) else d[d.selection == "over"]
        d = d.sort_values(["edge", "p_model"], ascending=False).head(40)
        rows = []
        for r in d.itertuples():
            e = r.edge
            etxt = ("✅ " if r.confirmed and pd.notna(e) and e >= r.threshold else "") + (
                f"{100 * e:+.0f} pts" if pd.notna(e) else f"{pct(r.p_model)} model")
            rows.append(f'<div class="prow">{avatar(r, small=True)}<div class="body"><div class="nm">{E(r.player)}</div>'
                        f'<div class="bt">{E(r.bet)} · {E(r.team)}</div></div>'
                        f'<div class="right"><div class="price">{am(r.best_price) if pd.notna(r.best_price) else pct(r.p_model)}</div>'
                        f'<div class="edge{" neg" if pd.isna(e) or e < 0 else ""}">{etxt}</div></div></div>')
        st.markdown(f'<div class="note">Sorted by best value. "pts" = how many percentage points our odds beat the book\'s.</div>'
                    f'<div class="card soft">{"".join(rows) or "No matches"}</div>', unsafe_allow_html=True)

with t_lineups:
    blob = fetch("slate_state.pkl")
    if not blob:
        empty("📋", "Lineups aren't ready yet")
    else:
        saved = pickle.loads(blob)
        state, roster = saved["state"], saved["roster"]
        lu = state.lineups.copy()
        st.markdown('<div class="note">Heard who\'s starting? Set the goalie, flip the switches, then tap '
                    '<b>Update picks</b>. Picks only go live once both are confirmed.</div>', unsafe_allow_html=True)
        choices = []
        for gm in state.schedule.itertuples():
            with st.expander(f"{nickname(gm.away)}  @  {nickname(gm.home)}", expanded=False):
                for team in (gm.away, gm.home):
                    goalies = roster[(roster.team == team) & (roster.pos == "G")]
                    cur = lu[(lu.team == team) & (lu.pos == "G")]
                    names = list(dict.fromkeys(goalies.name))
                    idx = names.index(cur.name.iloc[0]) if len(cur) and cur.name.iloc[0] in names else 0
                    st.markdown(f'<div style="display:flex;align-items:center;gap:10px;margin:6px 0">'
                                + logo_img(team, style="width:36px;height:36px;font-size:12px;border-radius:10px") +
                                f'<span style="font-family:Fredoka,sans-serif;font-weight:600;font-size:18px">{E(nickname(team))}</span></div>',
                                unsafe_allow_html=True)
                    gname = st.selectbox("Starting goalie", names, index=idx, key=f"g_{gm.game_id}_{team}") if names else None
                    c1, c2 = st.columns(2)
                    gconf = c1.toggle("Goalie confirmed", key=f"gc_{gm.game_id}_{team}",
                                      value=bool(cur.confirmed.iloc[0]) if len(cur) else False)
                    lconf = c2.toggle("Lineup confirmed", key=f"lc_{gm.game_id}_{team}",
                                      value=bool(lu[(lu.team == team) & (lu.pos != "G")].confirmed.all()))
                    choices.append(dict(team=team, goalie=gname, goalie_confirmed=gconf, lineup_confirmed=lconf))
        if st.button("🔄  Update picks", type="primary", use_container_width=True):
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
            st.session_state.plays = p
            st.session_state.repriced = True
            st.rerun()
        ov = pd.DataFrame([dict(team=c["team"], goalie=c["goalie"] if c["goalie_confirmed"] else "",
                                lineup_confirmed=c["lineup_confirmed"]) for c in choices])
        st.download_button("💾  Save for the track record", ov.to_csv(index=False), file_name=f"{state.date.date()}.csv",
                           mime="text/csv", use_container_width=True,
                           help="Commit this file to overrides/ in the repo so tonight's picks get logged and graded.")

with t_record:
    log = csv("bets_log.csv")
    g = log[log.result.notna()].copy() if "result" in log else pd.DataFrame()
    if g.empty:
        empty("📈", "The scoreboard starts tonight",
              "Every pick is logged at the price we flagged it and graded the next morning.")
    else:
        x = g[g.result.isin([0, 1])]
        units, roi = x.profit.sum(), x.profit.mean()
        w, l = int(x.result.sum()), int((1 - x.result).sum())
        blocks = [f'<div class="big{" neg" if units < 0 else ""}">{units:+.1f} units</div>'
                  f'<div class="bigsub">{w}-{l} · {roi:+.1%} return per bet (1 unit each)</div>']
        clv = g.clv_prob.dropna()
        if len(clv):
            beat = (clv > 0).mean()
            blocks.append(f'<div class="big{" neg" if beat < .5 else ""}">{beat:.0%}</div>'
                          f'<div class="bigsub">beat the closing line. Over the long run this matters more than '
                          f'wins and losses.</div>')
        groups = {"Player props": ["goals", "sog", "assists", "points"],
                  "Sides": ["moneyline", "puckline", "p1_3way"], "Totals": ["total", "team_total", "p1_total"]}
        rows = []
        for name, mk in groups.items():
            y = x[x.market.isin(mk)]
            if len(y):
                rows.append(f'<div class="status"><div><div class="nm">{name}</div><div class="d">'
                            f'{int(y.result.sum())}-{int((1 - y.result).sum())}</div></div>'
                            f'<span class="pill {"green" if y.profit.sum() >= 0 else "red"}">{y.profit.sum():+.1f}u</span></div>')
        blocks.append("".join(rows))
        st.markdown(f'<div class="card"><div class="h2" style="margin-top:0">Track record</div>{"".join(blocks)}</div>',
                    unsafe_allow_html=True)
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
                    f'<div class="note">Based on how the model did on last season\'s games it never saw.</div>'
                    f'{"".join(rows)}</div>', unsafe_allow_html=True)
        v = fetch("validation.md")
        if v:
            with st.expander("🤓 The nerdy details"):
                st.markdown(v.decode())
    if meta.get("warnings"):
        with st.expander("ℹ️ Data notes"):
            for w in meta["warnings"]:
                st.markdown(f"- {w}")

st.markdown(f'<div class="foot">🏒 NHL Model {APP_VERSION} · data from the NHL · bet responsibly</div>',
            unsafe_allow_html=True)
