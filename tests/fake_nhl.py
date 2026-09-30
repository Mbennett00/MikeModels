"""Fabricated NHL API payloads (play-by-play + shift charts) with the real field names."""
import numpy as np

TEAMS = {1: "BOS", 2: "TOR", 3: "MTL", 4: "OTT"}


def _mmss(s):
    return f"{s // 60:02d}:{s % 60:02d}"


def roster(team_id):
    base = team_id * 100
    out = []
    for i in range(12):
        out.append(dict(teamId=team_id, playerId=base + i, positionCode="C", firstName={"default": "F"},
                        lastName={"default": f"{TEAMS[team_id]}{i}"}))
    for i in range(12, 18):
        out.append(dict(teamId=team_id, playerId=base + i, positionCode="D", firstName={"default": "D"},
                        lastName={"default": f"{TEAMS[team_id]}{i}"}))
    for i in (18, 19):
        out.append(dict(teamId=team_id, playerId=base + i, positionCode="G", firstName={"default": "G"},
                        lastName={"default": f"{TEAMS[team_id]}{i}"}))
    return out


def game(gid, date, home, away, rng):
    plays, shifts = [], []
    # penalty on away in P2 at 600-720s: away plays 4 skaters
    pen_lo, pen_hi = 1200 + 600, 1200 + 720
    for team_id in (home, away):
        base = team_id * 100
        starter = base + 18 if rng.random() < 0.7 else base + 19
        for per in (1, 2, 3):
            shifts.append(dict(typeCode=517, playerId=starter, teamAbbrev=TEAMS[team_id], period=per,
                               startTime="00:00", endTime="20:00"))
            for k, t0 in enumerate(range(0, 1200, 45)):
                t1 = min(t0 + 45, 1200)
                fl = k % 4; dp = k % 3
                skaters = [base + fl * 3 + j for j in range(3)] + [base + 12 + dp * 2 + j for j in range(2)]
                g0 = (per - 1) * 1200 + t0
                if team_id == away and pen_lo <= g0 < pen_hi:
                    skaters = skaters[:4]
                for pid in skaters:
                    shifts.append(dict(typeCode=517, playerId=pid, teamAbbrev=TEAMS[team_id], period=per,
                                       startTime=_mmss(t0), endTime=_mmss(t1)))
        # the starter id is carried in shots below
        if team_id == home:
            hg = starter
        else:
            ag = starter
    score = {home: 0, away: 0}
    for t in sorted(rng.choice(3600, 60, replace=False)):
        per, tin = t // 1200 + 1, t % 1200
        team = home if rng.random() < 0.5 else away
        base = team * 100
        sc = "1551"
        if pen_lo <= t < pen_hi:
            sc = "1451"
        k = (tin // 45) % 4
        shooter = base + k * 3 + int(rng.integers(3))
        r = rng.random()
        typ = "goal" if r < 0.07 else ("shot-on-goal" if r < 0.6 else ("missed-shot" if r < 0.8 else "blocked-shot"))
        det = dict(eventOwnerTeamId=team, xCoord=float(rng.integers(30, 89)), yCoord=float(rng.integers(-30, 30)),
                   shotType="wrist", goalieInNetId=ag if team == home else hg)
        if typ == "goal":
            det.update(scoringPlayerId=shooter, assist1PlayerId=base + ((k * 3 + 1) % 12), assist2PlayerId=base + 12)
            score[team] += 1
        else:
            det["shootingPlayerId"] = shooter
        plays.append(dict(typeDescKey=typ, periodDescriptor=dict(number=int(per), periodType="REG"),
                          timeInPeriod=_mmss(int(tin)), situationCode=sc, details=det))
    plays.append(dict(typeDescKey="penalty", periodDescriptor=dict(number=2, periodType="REG"), timeInPeriod="10:00",
                      situationCode="1551", details=dict(typeCode="MIN", committedByPlayerId=away * 100 + 1,
                                                         eventOwnerTeamId=away, duration=2)))
    decision = "REG"
    if score[home] == score[away]:
        decision = "SO"; score[home] += 1
    pbp = dict(id=gid, gameDate=str(date.date()), season=20242025, gameType=2,
               homeTeam=dict(id=home, abbrev=TEAMS[home], score=score[home]),
               awayTeam=dict(id=away, abbrev=TEAMS[away], score=score[away]),
               gameOutcome=dict(lastPeriodType=decision), plays=plays, rosterSpots=roster(home) + roster(away))
    return pbp, shifts
