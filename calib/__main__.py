"""python -m calib {status, recalibrate, health} [--sport nhl|all] [--state state]"""
from __future__ import annotations

import argparse
import json
import os

from . import db, engine, health


def main(argv=None):
    p = argparse.ArgumentParser(prog="calib")
    p.add_argument("cmd", choices=["status", "recalibrate", "health"])
    p.add_argument("--sport", default="all", choices=["nhl", "all"])
    p.add_argument("--state", default="state")
    a = p.parse_args(argv)
    site = os.path.join(a.state, "site")
    sports = ["nhl"] if a.sport == "all" else [a.sport]
    for s in sports:
        engine.ensure_baseline(site, s)
        if a.cmd == "status":
            print(s, db.counts(site).get(s), "active", db.active(site, s).get("version"))
        elif a.cmd == "recalibrate":
            r = engine.recalibrate(site, s)
            json.dump(r, open(os.path.join(site, f"calib_last_{s}.json"), "w"), default=str, indent=1)
        else:
            print(json.dumps(health.build(site, s), default=str)[:2000])


if __name__ == "__main__":
    main()
