# NHL betting model

Prices anytime goal scorer, player shots on goal, assists, points, moneyline, puck line, totals,
team totals and first-period markets. For every play it outputs the **model projection, model
probability, fair American odds, the book's no-vig price and the edge**.

```
pip install -r requirements.txt
python -m pytest -q                       # 30 tests, ~45 s
```

## Website (phone + desktop) and daily automation

```
GitHub Actions (.github/workflows/daily.yml)            Streamlit Community Cloud (app/streamlit_app.py)
  ~6am ET   fetch last night's games from the NHL API,     reads the files below from the `data-latest`
            grade logged plays, walk-forward backtest       release: Flagged plays, All plays, Lineups
  ~11am ET  price today's slate (+ odds if key set)         (pick goalies, confirm, re-price), Track record,
  ~5:30pm   re-price with later lines                       Model health
  hourly    closing odds for games about to start
  push to overrides/**  re-price with your confirmations
        │ writes plays.csv, slate.md, meta.json, bets_log.csv, odds_history, validation.md ... │
        └────────────────────────────► GitHub release `data-latest` ───────────────────────────┘
```

Setup (one time):
1. **Odds (optional but needed for edges):** get a key from the-odds-api.com, then add it in GitHub
   → repo **Settings → Secrets and variables → Actions → New repository secret**, name `ODDS_API_KEY`.
   Player props cost one request per game per market group, so the free tier (500/month) is not
   enough for props every day. Add `--no-props` to the workflow to save credits.
2. **First data load:** GitHub → **Actions → daily model run → Run workflow → task `update`**.
   The first run downloads two seasons of games (roughly 1–2 hours; it resumes if cut off).
3. **Dashboard:** sign in at share.streamlit.io with GitHub → **Create app** → repo
   `Mbennett00/NHLModel`, branch `claude/betting-model-calibration-66x246` (or `main` once merged),
   main file `app/streamlit_app.py`. On a phone, open the app URL and use *Add to Home Screen*.
   To restrict who can see it, use the app's **Share** settings (viewer emails).
4. **Confirming lineups:** nothing is flagged until a team's goalie and lineup are confirmed. Either
   use the dashboard's Lineups tab (re-prices instantly, not saved), or commit
   `overrides/YYYY-MM-DD.csv` (format in `overrides/README.md`), which re-runs the slate and logs
   flagged plays for the track record.

Notes: the repository is public, so the release files (your plays) are public too. To keep them
private, make the repo private and add a read-only GitHub token as the Streamlit secret
`GITHUB_TOKEN`. GitHub pauses scheduled workflows in a repo with no activity for 60 days.

## Layout (one module per section of the spec)

| Spec section | Module |
|---|---|
| Data: NHL API play-by-play + shift charts (automated), MoneyPuck (manual), lineups, odds | `nhlmodel/data/` (`nhl_pipeline.py`, `xg.py`, `odds_api.py`, `moneypuck.py`, `schema.py`) |
| No leakage, 2 seasons, decay half-life | `nhlmodel/ratings.py` (every rate is built from rows dated before the game) |
| 1. Team model, bivariate Poisson, ML / PL / totals / P1 / team totals | `nhlmodel/team_model.py`, `nhlmodel/distributions.py` |
| 2–6. Player shrinkage, TOI, goals, SOG (NB), assists, points | `nhlmodel/player_model.py` |
| 7. Consistency check (player λ vs team λ) | `project_team_players` in `player_model.py` |
| 8. Fair odds, no-vig, edge, flags, low confidence | `nhlmodel/pricing.py`, `nhlmodel/book.py`, `nhlmodel/slate.py` |
| 9. Walk-forward, calibration, log loss / Brier vs baseline, CLV, grading | `nhlmodel/backtest.py`, `nhlmodel/validation.py`, `nhlmodel/report.py` |
| Fitted from history (λ3, OT slope, EN bumps, rest, NB r) | `nhlmodel/fitting.py` |
| Grid search of k, m, half-life, edge thresholds | `nhlmodel/tuning.py` |
| Every tunable constant | `nhlmodel/config.py` |

## Workflow

```
# 1. Build canonical tables (needs network access to api-web.nhle.com; MoneyPuck files downloaded by hand)
python -m nhlmodel build --raw data/raw --start 2024-10-04 --end 2026-04-17 --out data/processed

# 2. Tune on an early window and report on a later, untouched holdout
python -m nhlmodel tune --data data/processed \
    --tune-start 2025-10-20 --tune-end 2026-01-15 --holdout-start 2026-01-16 --holdout-end 2026-04-17 \
    --out out/tune

# 3. Price a slate with the tuned constants and dispersion fitted on the backtest's predictions
python -m nhlmodel slate --data data/processed --config out/tune/tuned_config.json --history out/tune \
    --schedule today_schedule.csv --lineups today_lineups.csv --odds today_odds.csv --out out/slate
```

`out/slate/slate.md` lists flagged plays and the consistency check. `out/slate/plays.csv` has the full
board (every market, both sides). `out/tune/validation.md` is the per-market validation report.

To try the whole pipeline without real data: `python -m nhlmodel synth --out data/synthetic`, then run
`tune` or `backtest` against `data/synthetic`. **Synthetic results say nothing about real edges.**

## Input files

* `data/raw/teams/*.csv`, `data/raw/skaters/*.csv`, `data/raw/goalies/*.csv`: MoneyPuck game-by-game
  files. Column names are mapped at the top of `nhlmodel/data/moneypuck.py`. If a load fails, the
  error lists the missing columns.
* Schedule, lineups and odds for a slate: see `templates/`. Lineups follow Daily Faceoff: `line` is
  F1–F4, D1–D3 or G1 (the starting goalie), `pp_unit` is 0/1/2, and `confirmed` is True/False.
  Odds need one row per book price. `snapshot` is `bet` (or `open`) for the price you would take,
  and `close` for CLV.

## How the method is implemented, and where it departs from the spec

These are the assumptions made instead of guesses. Each one is also printed in the reports.

1. **PP_PK_factor** is defined so that the 5v5 factors do not also scale power-play goals:
   `PP_PK = [(1−s)·off·def + s·pp_off·pk_def_opp·pp_time] / (off·def)`, where `s` is the league PP
   share of xG. Multiplied out, this is the spec's product form. Expected PP time is
   `(team penalties drawn/60 ÷ league) × (opponent penalties taken/60 ÷ league)`.
2. **Totals and team totals are graded on the official final score.** A regulation tie adds one
   goal (the OT or shootout winner), so P(over) comes from the final-score distribution rather than
   raw `h + a`. Whole-number lines remove the push and renormalise.
3. **Empty-net adjustment** has one mechanism for the puck line, totals and team totals. From
   history, fit P(the leader scores 0, 1 or 2 EN goals | regulation lead of 1, 2 or 3), then move
   mass in the score matrix. The fit is smoothed toward priors with 50 pseudo-games.
4. **OT/SO**: `P(home) = 0.5 + slope × (λ_h/(λ_h+λ_a) − 0.5)`, clipped to 0.3–0.7. The slope is
   fitted by maximum likelihood once there are at least 150 OT/SO games.
5. **Rest/travel**: back-to-back offence, back-to-back defence (the opponent's goals) and travel
   over 1,500 km on a back-to-back are estimated as residual ratios. Each is kept only if |z| ≥ 2,
   otherwise set to 1.0. The report lists what was kept or dropped.
6. **Pace** enters as `pace_factor^pace_exponent`. xG rates already include volume, so the exponent
   is tuned and may be 0.
7. **Finishing**: `finish = clip((G + m·r)/(xG + m), 0.85, 1.15)`, where r is league goals per xG.
   This is m goals-equivalent of league-average finishing.
8. **Assists**: A1 + A2 shrunk with one k equals A1 and A2 shrunk separately with that k, then
   summed. The linemate factor applies to 5v5 only and is damped (exponent 0.5, clipped 0.8–1.25).
9. **Empty-net goals** are excluded from the training rates, but books settle on all goals. After
   the consistency check, player goal and assist λ get a fitted uplift of 1/(1 − league EN share).
   This uplift is the same for every player, so it does not model top-line forwards scoring more EN
   goals.
10. **Consistency target**: team regulation non-EN λ × the share of goals credited to skaters, plus
    expected OT goals. Assists use the fitted assists-per-goal ratio.
11. **Points**: `P(1+) = 1 − exp(−λ_pts)`. For higher lines, and for all lines once the backtest
    shows overdispersion, an NB dispersion fitted on the backtest's own out-of-sample predictions is
    used. Assists use the same rule: Poisson unless NB improves log-likelihood by more than
    2 per 1,000 observations.
12. **Lines in history**: MoneyPuck has no line data, so historical lines and PP units are inferred
    from TOI rank. Real Daily Faceoff lines are only used for live slates. The walk-forward treats
    the lineup that actually dressed, and the actual starting goalie, as the confirmed pre-game lineup.
13. **xG and score/venue adjustment.** The automated pipeline uses its own xG model (logistic
    regression on distance, angle, shot type, rebound and strength), with each season scored by the
    previous season's fit. The earliest loaded season is scored in-sample and flagged. Score/venue
    coefficients (0.5 / xG share by lead state and venue, clipped 0.8–1.25) are computed league-wide
    across all loaded data. That is a small leak into the backtest, but not into live pricing. The
    MoneyPuck path uses MoneyPuck's `scoreVenueAdjustedxGoals*` columns instead.
13b. **TOI by strength** comes from NHL shift charts: 5v5 means five skaters and a goalie on both
    sides, and PP means more skaters with both goalies in. Event strength comes from each event's
    `situationCode`.
14. **One-sided markets**: a small assumed hold is removed (2.5% for game markets, 5% for player
    props). Keeping the hold small keeps the book's probability high, so edge is understated rather
    than overstated.
15. **Several books**: the no-vig price is the median of each book's own no-vig probability, and the
    bet price is the best available price. A play is `low` confidence if it is single-book,
    one-sided, in a thin market (assists, team totals, P1) or has an unconfirmed lineup.
    Unconfirmed plays are priced but never flagged.
16. **Grid search** is coordinate descent (one parameter at a time over its grid), not a full
    Cartesian product. Every grid point is a full walk-forward, so a full product is too expensive.
    Edge thresholds are chosen per market to maximise mean CLV (EV at the closing no-vig price) with
    at least 50 bets, using the tuning window only.
17. **Market grading**: `DROP` if the model's log loss is no better than the baseline on the same
    rows. `DOWNWEIGHT` if the ECE is above 3%, or a bucket with 200+ samples misses by more than 2
    points with |z| > 3. For game markets the baseline is the closing no-vig line whenever odds are
    supplied, which is a hard bar to clear.

## Known gaps / data not available here

* Natural Stat Trick is not scraped. The same situation splits (5v5, 5on4, 4on5) come from
  MoneyPuck. NST exports could replace them, but no adapter is written.
* Daily Faceoff has no public API. Lineups are read from a CSV in the template format.
* No odds feed is wired in. Odds are read from a CSV, and without odds there is no closing-line
  baseline, CLV or edge-threshold tuning.
* Travel uses approximate arena coordinates (`nhlmodel/arenas.py`). Time zones are not modelled.
