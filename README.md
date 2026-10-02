# NHL betting model

Prices anytime goal scorer, player shots on goal, assists, points, moneyline, puck line, totals,
team totals and first-period markets. For every play it outputs the **model projection, model
probability, fair American odds, the book's no-vig price and the edge**.

```
pip install -r requirements-dev.txt
python -m pytest -q                       # 37 tests, ~60 s
```

## Website (phone + desktop) and daily automation

```
GitHub Actions (.github/workflows/daily.yml)              GitHub Pages: https://mbennett00.github.io/NHLModel/
  ~6am ET   fetch last night's games from the NHL API,       plain HTML page (nhlmodel/web_template.html) +
            grade logged plays, walk-forward backtest         data.json written by nhlmodel/web.py on every
  11am, 1pm, 3:30pm, 5:30pm, 6:40pm ET                        slate run: Tonight, Players, Check, Lineups,
            re-price with Daily Faceoff lines, goalies        Model. No server, so nothing to crash or wake up.
            and injuries                                      The Check tab prices any line in the browser.
  push to overrides/**  re-price with your confirmations
        │ state (history, bets_log.csv, validation, ...) ──► GitHub release `data-latest`
```

One-time setup: repo **Settings → Pages → Build and deployment → Source: GitHub Actions**, then
**Actions → daily model run → Run workflow** (task `slate`). On a phone, open the page and use
*Add to Home Screen*. The older Streamlit dashboard (`app/streamlit_app.py`) still works from the
same release files but is no longer needed.

**Market consensus game lines (lean mode, default).** `ODDS_ENABLED: "lean"` pulls moneyline, puck line
and totals for every US book in one Odds API call (`regions=us`, 3 credits), once after 10:30am and once
between 5:45 and 8pm ET (by the clock, since scheduled GitHub runs can start late; one attempt per
window), about 180 credits a month. Edges are the model's chance minus the market consensus (median
no-vig chance across books). Tiles show Caesars' price when Caesars is in the feed (matched by name; as
of Oct 2026 the feed carries BetMGM, BetOnline, BetRivers, BetUS, Bovada, DraftKings, FanDuel, LowVig and
MyBookie for NHL, not Caesars), otherwise the market's fair price ("Mkt"). The evening pull also records
the close for games starting within 2.5 hours. Needs the repo secret `ODDS_API_KEY`.

**Previously: no odds feed.** The site is a price sheet: for every bet it shows the model's chance, the
fair price and a "bet at or better than" price (fair chance minus the market's edge threshold, with
the book's cut left in as a cushion). You compare with your sportsbook yourself, or type its odds into
the **Check** tab. The Odds API code is still in `nhlmodel/data/odds_api.py`: set `ODDS_ENABLED: "1"`
and pass `secrets.ODDS_API_KEY` in `daily.yml` to switch it back on.

Setup (one time):
1. **Odds (optional, off by default):** get a key from the-odds-api.com, then add it in GitHub
   → repo **Settings → Secrets and variables → Actions → New repository secret**, name `ODDS_API_KEY`.
   Player props cost one request per game per market group, so the free tier (500/month) is not
   enough for props every day. Add `--no-props` to the workflow to save credits.
2. **First data load:** GitHub → **Actions → daily model run → Run workflow → task `update`**.
   The first run downloads two seasons of games (roughly 1–2 hours; it resumes if cut off).
3. **Website:** enable GitHub Pages as above. The page is public (as is the repo).
4. **Confirming lineups:** nothing is flagged until a team's goalie and lineup are confirmed. Either
   use the dashboard's Lineups tab (re-prices instantly, not saved), or commit
   `overrides/YYYY-MM-DD.csv` (format in `overrides/README.md`), which re-runs the slate and logs
   flagged plays for the track record.

Notes: the repository is public, so the release files (your plays) are public too. To keep them
private, make the repo private and add a read-only GitHub token as the Streamlit secret
`GITHUB_TOKEN`. GitHub pauses scheduled workflows in a repo with no activity for 60 days.

## NFL (🏈 tab: `nfl.html`, package `nflmodel/`)

Same idea as the hockey side, rebuilt for football. The 🏒 / 🏈 switch at the top of the page flips between them;
the NFL page has a turf background, team-colour game cards, a Teams power ranking and a Check calculator.

- **Data**: nflverse play-by-play (2018 onward) and schedule (results, lines, projected starting QBs). Every run
  re-downloads the schedule and the current season, so the page is as fresh as nflverse (they refresh overnight
  after each game day). Finished seasons are kept as small per-game tables in `state/intermediate/nfl/`.
- **Ratings**: for EPA per play, EPA per dropback and points, a weighted ridge regression
  `y = mu + home + offense[team] + defense[opponent]` over past games (half-life 140 days, garbage time removed).
- **Starting QB**: each QB's EPA per dropback (shrunk toward replacement); when the listed starter differs from the
  team's usual QB play, the passing numbers move by the difference.
- **Injuries**: ESPN's live NFL injury list (official report from nflverse as a fallback). A starter is a player with
  40%+ of offensive or defensive snaps over the team's last 6 games; each injured starter counts his snap share,
  scaled by status (Out/IR 1.0, Doubtful 0.85, Questionable 0.25). A ruled-out starting QB is replaced by his backup
  in the QB adjustment. Backtest (official pre-game reports, 2021-2026): one "missing starters" number moves the margin
  about 0.84 points per full-time starter; margin error 10.22 → 10.20, moneyline Brier 0.2243 → 0.2234, ATS when the
  model is off the close by 3+ 48.8% → 50.9%. Splitting by position group (6 numbers) overfit (10.26), and injuries did
  not improve totals, so totals ignore them.
- **Game expectation**: margin and total are linear in the two sides' ratings (plus dome / wind / cold for totals),
  fitted on past seasons. The margin distribution is a discretised normal reweighted by key-number factors measured
  on past finals (3, 7, 10, 6, 14 ...), re-centred to keep its mean. Moneyline, spread, total and alt lines come from it.
- **Market**: one Odds API call a day (`americanfootball_nfl`, h2h + spreads + totals, all US books, 3 credits),
  the first run after 10:30am ET. Consensus = the line most books hang and the median no-vig chance at that line;
  Caesars' price is shown when it is in the feed. Until a pull exists, the nflverse posted lines are used.
  Manual pull: run the workflow with task `nfl-odds`.
- **Backtest** (walk-forward, 2021-2026 regular + post season, 1,473 games, vs **closing** lines):

  | | model | closing line |
  |---|---|---|
  | Margin mean abs. error | 10.20 | 9.78 |
  | Total mean abs. error | 10.54 | 10.34 |
  | Against the spread (all games / model off by 3+) | ~48% / 50.9% | – |
  | Over/under (all games / off by 3+) | 51.2% / 48.5% | – |
  | Moneyline Brier score | 0.2234 | 0.2123 |

  Closing lines are sharper than a public-data team model, as expected. The page says so, the 💰 flag needs a 6-point
  edge, and the model is best used to find numbers worth a look early in the week and to price alt lines.
  Starting-QB adjustment: margin error 10.28 → 10.22. Half-life 90-300 days and ridge 3-12 all landed within 0.08.
- **Player props** (`nflmodel/props.py`, 👤 Props tab and each game's Players panel): anytime TD, receptions,
  receiving / rushing / passing yards, passing TDs.
  - Volume: team targets and carries per game (half-life 5 games), moved by game script (leading teams run more).
  - Share: recency-weighted share of team targets / carries; players ruled out (ESPN injuries, roster status)
    are dropped and their share goes to available teammates. The projected starting QB gets the dropbacks.
  - Efficiency: catch rate, yards per target / carry / attempt shrunk toward the role average, adjusted for the
    opponent's pass / run defence. TDs: team TDs from the game model's projected points, split pass / rush, with
    each player's slice from his red-zone share blended with his overall share.
  - Fitted on 2022-23 walk-forward projections, tested on 2024-26 (players who played):

    | | model MAE | last-5-games average MAE |
    |---|---|---|
    | Receptions | 1.65 | 1.70 |
    | Receiving yards | 22.5 | 23.5 |
    | Rushing yards | 22.9 | 24.2 |
    | Passing yards (starters) | 59.6 | 65.5 |

    Anytime TD Brier 0.163 vs 0.176 for the base rate; calibrated by bucket (e.g. 30-40% predicted → 35% scored).
    Yardage uses a shifted gamma (less skewed than a plain gamma, which put the median too low); the model's
    chance of going over its own even-money line runs within about 1 point of actual for receiving and rushing.
  - No prop odds are pulled (the per-game prop endpoint would cost ~75 credits a week); type the book's line and
    price into the player sheet for a verdict. The green price leaves a 4-point cushion for prop hold.
- **Next**: a field formation view.

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
9b. **League scale**: a walk-forward factor, actual ÷ predicted regulation goals over prior
    predictions (recency weighted, clipped 0.9–1.1), multiplies every team λ. It removes the small
    upward bias from multiplying shrunk factors, which had overpriced overs. It is refit with the
    other parameters and shown in the fit log.
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

17b. **Missing regulars** (`nhlmodel/lineup.py`): this season's top-6 F / top-4 D (by ice time over the
    last 10 games) who are not dressing are replaced at replacement level for their usual minutes, and
    the team's expected goals can drop by `lineup_beta` x that share (capped at -10%). Walk-forward
    Dec 2025-Apr 2026 (449 games, tuned config): teams missing regulars did score ~4-5% below
    expectation, but also allowed ~6-9% fewer, so with beta 0.5 moneyline log loss went 0.6784 -> 0.6789,
    totals 0.6930 -> 0.6925, puck line and props unchanged within noise. No gain, so `lineup_beta = 0`
    (off) and it stays in the tuning grid; the page still lists missing regulars and their usual share
    of team scoring on each game's Matchup tab.

17c. **xG v2** (`nhlmodel/data/xg.py`, `XG_VERSION = 2`): adds shot-sequence context from the stored
    shots (rebound angle change per second, rush proxy = attempt within 10 s of one by the other team,
    sustained pressure, time since the last attempt), a finer distance/angle shape, tip/deflection x
    distance, score state, and a per-rink recorded-distance correction. Out of sample (fit 2024-25,
    scored 2025-26): shot log loss 0.2261 -> 0.2251, AUC 0.740 -> 0.743. Walk-forward Dec 2025-Apr
    2026: moneyline 0.6784 -> 0.6780, totals 0.6930 -> 0.6913, team totals 0.6622 -> 0.6616, goals
    0.23427 -> 0.23424; puck line and other props unchanged. No passes/carries in the stored data, so
    true pre-shot movement and shooter handedness are not modelled.

17d. **Ice-time projection v2** (`toi_method = 2`): recent games weighted by 0.5^(games ago / 5); games
    the player spent in tonight's line / PP unit carry 80% of the estimate when he has at least two;
    shrunk toward the role average with 5 pseudo-games. On 8,063 player-games: 5v5 TOI error 1.59 ->
    1.47 min, PP 0.68 -> 0.62 min. Walk-forward: shots on goal 0.36981 -> 0.36900, goals 0.23424 ->
    0.23416, assists / points unchanged within noise.

17e. **MoneyPuck xG (optional source)**: `nhlmodel/data/moneypuck_shots.py` downloads MoneyPuck's
    shot files each morning (`intermediate/mp_shots.csv.gz`) and `build_tables(..., xg_source=
    "moneypuck")` uses their xG for every shot that matches ours (game, shooter, game second), with our
    model for the rest. Off by default (`NHL_XG_SOURCE=model`); `python -m nhlmodel.daily xg-compare`
    (workflow task `xg-compare`) runs the walk-forward with each source and writes
    `site/xg_compare.json`. Data courtesy of MoneyPuck.com; check their terms before commercial use.
    Result (walk-forward 2025-12-27 to 2026-04-16): MoneyPuck's xG is clearly better shot by shot
    (log loss 0.2181 vs our 0.2254 on 110,719 shots, flattered because their model trained on that
    season), but priced through this model it was worse on every market: moneyline 0.6842 vs 0.6836,
    totals 0.6832 vs 0.6743, team totals 0.6666 vs 0.6632, puck line and props slightly worse. The
    goalie, finishing and tuned constants are fitted around our xG, so the source stays "model".
    **xG v3** (`XG_VERSION = 3`): v2 plus MoneyPuck's event-feed context as model inputs (rush, speed /
    time / distance from the last event, rebound angle speed, off-wing, last event type, shooter and
    defender time on ice), still fit on the previous season. Shot level it beats v2 out of sample
    (0.2246 vs 0.2254), but in the walk-forward it is mixed and within noise: moneyline 0.6843 vs
    0.6836, totals 0.6739 vs 0.6743, puck line 0.5928 vs 0.5925, team totals and props even. Team and
    goalie ratings average thousands of shots, so better per-shot grading mostly washes out. v2 stays
    the default; `xg-compare` re-runs the test as more MoneyPuck data accumulates.

## Known gaps / data not available here

* Natural Stat Trick is not scraped. The same situation splits (5v5, 5on4, 4on5) come from
  MoneyPuck. NST exports could replace them, but no adapter is written.
* Daily Faceoff has no public API. Lineups are read from a CSV in the template format.
* No odds feed is wired in. Odds are read from a CSV, and without odds there is no closing-line
  baseline, CLV or edge-threshold tuning.
* Travel uses approximate arena coordinates (`nhlmodel/arenas.py`). Time zones are not modelled.
