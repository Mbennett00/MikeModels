"""Print the distinct identifiers used on Daily Faceoff pages (for building the parser)."""
import collections
import sys

sys.path.insert(0, ".")
import pandas as pd  # noqa: E402

from nhlmodel.data import dailyfaceoff as dfo  # noqa: E402

date = sys.argv[1] if len(sys.argv) > 1 else str(pd.Timestamp.now(tz="America/New_York").date())
js = dfo.next_data(dfo.goalies_url(date))
for g in js["props"]["pageProps"]["data"]:
    print("GOALIES", g.get("awayTeamSlug"), g.get("awayGoalieName"), g.get("awayNewsStrengthName"), "|",
          g.get("homeTeamSlug"), g.get("homeGoalieName"), g.get("homeNewsStrengthName"), "|", g.get("dateGmt"))
for team in ("TOR", "COL", "PIT", "UTA", "NYI"):
    try:
        js = dfo.next_data(dfo.lines_url(team))
    except Exception as e:
        print(team, "FAILED", e)
        if team in dfo.ALT_SLUG:
            for s in dfo.ALT_SLUG[team]:
                try:
                    js = dfo.next_data(dfo.lines_url(team, s)); print(team, "alt slug ok:", s)
                except Exception as e2:
                    print(team, "alt", s, "FAILED", e2); continue
        else:
            continue
    pl = js["props"]["pageProps"]["combinations"]["players"]
    combos = collections.Counter((p.get("categoryIdentifier"), p.get("groupIdentifier"), p.get("positionIdentifier"))
                                 for p in pl)
    print(team, "combos:", sorted(combos.items(), key=str))
    for p in pl:
        if p.get("injuryStatus") or p.get("gameTimeDecision") or p.get("categoryIdentifier") not in ("ev", "pp", "pk"):
            print(team, "  ", p.get("name"), p.get("categoryIdentifier"), p.get("groupIdentifier"),
                  p.get("positionIdentifier"), "inj=", p.get("injuryStatus"), "gtd=", p.get("gameTimeDecision"))
