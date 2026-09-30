"""NHL model dashboard (Streamlit). Works in desktop and phone browsers.

Data comes from the `data-latest` GitHub release written by the daily workflow.
Settings (Streamlit secrets or environment variables):
  NHLMODEL_REPO       owner/repo (default Mbennett00/NHLModel)
  GITHUB_TOKEN        only needed if the repository is private
  NHLMODEL_SITE_DIR   read files from a local folder instead (development)
"""
from __future__ import annotations

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

st.set_page_config(page_title="NHL Model", page_icon="🏒", layout="wide")

TAG = "data-latest"
SERIES = "#2a78d6"


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


@st.cache_data(ttl=600, show_spinner=False)
def fetch(name: str) -> bytes | None:
    if LOCAL:
        p = os.path.join(LOCAL, name)
        return open(p, "rb").read() if os.path.exists(p) else None
    h = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}", headers=h, timeout=20)
    if r.status_code != 200:
        return None
    asset = next((a for a in r.json().get("assets", []) if a["name"] == name), None)
    if asset is None:
        return None
    r = requests.get(asset["url"], headers={**h, "Accept": "application/octet-stream"}, timeout=60)
    return r.content if r.status_code == 200 else None


def csv(name, **kw):
    b = fetch(name)
    return pd.read_csv(io.BytesIO(b), **kw) if b else pd.DataFrame()


MARKET_LABEL = {"sog": "SOG", "assists": "Ast", "points": "Pts", "goals": "Goals"}


def describe(r) -> str:
    home, away = str(r.matchup).split(" @ ")[1], str(r.matchup).split(" @ ")[0]
    m, s, ln = r.market, str(r.selection), r.line
    team = lambda x: home if x.startswith("home") else (away if x.startswith("away") else "Draw")
    if m in ("goals", "sog", "assists", "points"):
        if m == "goals" and ln == 0.5 and s == "over":
            return f"{r.player} anytime goal"
        return f"{r.player} {'o' if s == 'over' else 'u'}{ln:g} {MARKET_LABEL[m]}"
    if m == "moneyline":
        return f"{team(s)} ML"
    if m == "puckline":
        return f"{team(s)} {ln:+g}"
    if m == "total":
        return f"{'Over' if s == 'over' else 'Under'} {ln:g}"
    if m == "team_total":
        return f"{team(s)} {'o' if s.endswith('over') else 'u'}{ln:g}"
    if m == "p1_total":
        return f"1P {'o' if s == 'over' else 'u'}{ln:g}"
    if m == "p1_3way":
        return f"1P {team(s)}"
    return f"{m} {s} {ln}"


def board(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    d = df.copy()
    d["play"] = [describe(r) for r in d.itertuples()]
    d["start"] = pd.to_datetime(d.get("start_utc"), utc=True, errors="coerce").dt.tz_convert(
        "America/New_York").dt.strftime("%-I:%M %p")
    d["model"] = d.p_model
    d["fair"] = d.fair_odds.map(format_american)
    d["book no-vig"] = d.book_novig_odds.map(format_american)
    d["best price"] = d.best_price.map(lambda x: format_american(x) if pd.notna(x) else "")
    d["status"] = np.where(d.confirmed.astype(bool), "confirmed", "unconfirmed")
    d["flags"] = d["flags"].fillna("")
    return d


# most important columns first so they are visible without scrolling on a phone
COLS = ["play", "edge", "best price", "model", "fair", "book no-vig", "projection", "start", "matchup",
        "confidence", "status", "flags"]
CFG = {"model": st.column_config.NumberColumn("model", format="%.1f%%", help="Model probability"),
       "edge": st.column_config.NumberColumn("edge", format="%.1f pts", help="Model minus book no-vig, in points"),
       "flags": st.column_config.TextColumn("notes", width="medium")}


def pct_cols(d):
    d = d.copy()
    for c in ("model", "edge"):
        if c in d:
            d[c] = d[c] * 100
    return d


# ---------------------------------------------------------------------------------------------
meta = json.loads(fetch("meta.json") or b"{}")
plays_raw = csv("plays.csv")
if "plays" not in st.session_state:
    st.session_state.plays = plays_raw
    st.session_state.repriced = False

st.title("NHL Model")
if meta:
    st.caption(f"Slate {meta.get('date', '?')} · updated {str(meta.get('generated_at', ''))[:16].replace('T', ' ')} ET · "
               f"data through {meta.get('data_through', '?')} · constants: {meta.get('constants', '?')}")
else:
    st.warning("No data published yet. The daily GitHub workflow has not run, or the release is missing.")
if meta.get("warnings"):
    with st.expander(f"Warnings and assumptions ({len(meta['warnings'])})"):
        for w in meta["warnings"]:
            st.write("• " + w)

tab_flag, tab_all, tab_lineups, tab_record, tab_health = st.tabs(
    ["Flagged", "All plays", "Lineups", "Track record", "Model health"])

plays = board(st.session_state.plays)
markets = sorted(plays.market.unique()) if len(plays) else []

with tab_flag:
    if st.session_state.repriced:
        st.info("Showing plays re-priced with your lineup choices (not saved; see Lineups).")
    if plays.empty:
        st.write("No plays today.")
    else:
        f = plays[plays.flag.astype(bool)].sort_values("edge", ascending=False)
        pending = plays[(~plays.confirmed.astype(bool)) & (plays.edge >= plays.threshold)]
        st.markdown(f"**{len(f)}** flagged plays · **{plays.game_id.nunique()}** games · "
                    f"**{len(pending)}** edges awaiting lineup/goalie confirmation")
        st.dataframe(pct_cols(f[COLS]), hide_index=True, use_container_width=True, column_config=CFG)
        if len(pending):
            with st.expander(f"Edges over threshold but lineup/goalie unconfirmed ({len(pending)}): not bets yet"):
                st.dataframe(pct_cols(pending.sort_values("edge", ascending=False)[COLS]), hide_index=True,
                             use_container_width=True, column_config=CFG)

with tab_all:
    if len(plays):
        c1, c2, c3 = st.columns([2, 1, 1])
        pick = c1.multiselect("Markets", markets, default=markets)
        min_edge = c2.slider("Min edge (pts)", -10.0, 15.0, 0.0, 0.5)
        games = ["All"] + sorted(plays.matchup.unique())
        g = c3.selectbox("Game", games)
        d = plays[plays.market.isin(pick)]
        d = d[(d.edge.fillna(-1) * 100 >= min_edge) | (d.edge.isna() & (min_edge <= -10))]
        if g != "All":
            d = d[d.matchup == g]
        st.caption(f"{len(d)} plays")
        st.dataframe(pct_cols(d.sort_values("edge", ascending=False)[COLS]), hide_index=True,
                     use_container_width=True, column_config=CFG)

with tab_lineups:
    blob = fetch("slate_state.pkl")
    if not blob:
        st.write("No slate state published yet.")
    else:
        saved = pickle.loads(blob)
        state, roster = saved["state"], saved["roster"]
        lu = state.lineups.copy()
        st.write("Pick the confirmed starting goalies, tick the lineups you have confirmed, then re-price. "
                 "To save the choices (so the daily job logs the bets), download the overrides file and "
                 "commit it to `overrides/` in the repo.")
        choices = []
        for gm in state.schedule.itertuples():
            st.subheader(f"{gm.away} @ {gm.home}")
            cols = st.columns(2)
            for col, team in zip(cols, (gm.away, gm.home)):
                goalies = roster[(roster.team == team) & (roster.pos == "G")]
                cur = lu[(lu.team == team) & (lu.pos == "G")]
                names = list(goalies.name)
                idx = names.index(cur.name.iloc[0]) if len(cur) and cur.name.iloc[0] in names else 0
                gname = col.selectbox(f"{team} starter", names, index=idx, key=f"g_{gm.game_id}_{team}") if names else None
                gconf = col.checkbox(f"{team} goalie confirmed", key=f"gc_{gm.game_id}_{team}")
                lconf = col.checkbox(f"{team} lineup confirmed", key=f"lc_{gm.game_id}_{team}")
                choices.append(dict(game_id=gm.game_id, team=team, goalie=gname, goalie_confirmed=gconf,
                                    lineup_confirmed=lconf))
        if st.button("Re-price with these lineups", type="primary"):
            from nhlmodel.slate import price_state
            new = lu.copy()
            for c in choices:
                gi = new.index[(new.team == c["team"]) & (new.pos == "G")]
                if c["goalie"] is not None and len(gi):
                    hit = roster[(roster.team == c["team"]) & (roster.name == c["goalie"])]
                    new.loc[gi, ["player_id", "name"]] = [hit.player_id.iloc[0], c["goalie"]]
                    new.loc[gi, "confirmed"] = c["goalie_confirmed"]
                new.loc[(new.team == c["team"]) & (new.pos != "G"), "confirmed"] = c["lineup_confirmed"]
            with st.spinner("Pricing..."):
                p, _, _ = price_state(state, lineups=new)
            st.session_state.plays = p
            st.session_state.repriced = True
            st.success(f"Re-priced: {int(p.flag.sum())} flagged plays. See the Flagged tab.")
        ov = pd.DataFrame([dict(team=c["team"], goalie=c["goalie"] if c["goalie_confirmed"] else "",
                                lineup_confirmed=c["lineup_confirmed"]) for c in choices])
        st.download_button("Download overrides file", ov.to_csv(index=False), file_name=f"{state.date.date()}.csv",
                           mime="text/csv")

with tab_record:
    log = csv("bets_log.csv")
    if log.empty or "result" not in log:
        st.write("No graded plays yet. Flagged plays are logged at the price when first flagged and graded the next morning.")
    else:
        g = log[log.result.notna()].copy()
        g["date"] = pd.to_datetime(g.date)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Graded plays", len(g))
        c2.metric("ROI (1u flat)", f"{g.profit.mean():+.1%}" if len(g) else "n/a")
        c3.metric("Avg CLV (EV at close)", f"{g.clv_ev.mean():+.1%}" if g.clv_ev.notna().any() else "n/a")
        c4.metric("Beat closing line", f"{(g.clv_prob > 0).mean():.0%}" if g.clv_prob.notna().any() else "n/a")
        if len(g):
            daily = g.groupby("date").profit.sum().cumsum().reset_index(name="units")
            ch = alt.Chart(daily).mark_line(color=SERIES, strokeWidth=2).encode(
                x=alt.X("date:T", title=None, axis=alt.Axis(grid=False)),
                y=alt.Y("units:Q", title="Cumulative units (1u flat)", axis=alt.Axis(gridOpacity=0.3)),
                tooltip=[alt.Tooltip("date:T"), alt.Tooltip("units:Q", format="+.2f")],
            ).properties(height=260, title="Cumulative result, flagged plays")
            st.altair_chart(ch, use_container_width=True)
            by = g.groupby("market").agg(plays=("profit", "size"), roi=("profit", "mean"), clv_ev=("clv_ev", "mean"),
                                         beat_close=("clv_prob", lambda s: (s > 0).mean())).reset_index()
            for c in ("roi", "clv_ev", "beat_close"):
                by[c] = by[c] * 100
            st.dataframe(by, hide_index=True, use_container_width=True, column_config={
                "roi": st.column_config.NumberColumn("ROI", format="%+.1f%%"),
                "clv_ev": st.column_config.NumberColumn("CLV (EV at close)", format="%+.1f%%"),
                "beat_close": st.column_config.NumberColumn("beat close", format="%.0f%%")})
        with st.expander("All logged plays"):
            st.dataframe(log.sort_values("date", ascending=False), hide_index=True, use_container_width=True)

with tab_health:
    ms = csv("market_summary.csv")
    if ms.empty:
        st.write("No backtest published yet.")
    else:
        st.write("Walk-forward, out-of-sample results per market. Markets marked DROP or DOWNWEIGHT should not be bet "
                 "(or bet smaller).")
        show = ms[ms.line.astype(str) == "all"][["market", "n", "logloss", "logloss_base", "baseline", "ece", "status"]]
        st.dataframe(show, hide_index=True, use_container_width=True)
        v = fetch("validation.md")
        if v:
            with st.expander("Full validation report (calibration tables, warnings, CLV)"):
                st.markdown(v.decode())
