# Lineup / goalie overrides

To confirm a slate, add a file named `YYYY-MM-DD.csv` here (you can do it from the GitHub mobile
app or website). Committing it re-runs the slate automatically.

```
team,goalie,lineup_confirmed
BOS,Jeremy Swayman,True
TOR,Joseph Woll,True
```

* `goalie` is the confirmed starter (matched by name to that team's recent goalies).
* `lineup_confirmed=True` means the projected skater lineup (the team's last game) is confirmed.

Only teams whose goalie and lineup are both confirmed can have flagged plays.
