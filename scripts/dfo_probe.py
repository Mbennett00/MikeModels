"""Print the structure of Daily Faceoff's page data (for building the parser)."""
import json
import sys

sys.path.insert(0, ".")
import pandas as pd  # noqa: E402

from nhlmodel.data import dailyfaceoff as dfo  # noqa: E402


def walk(x, path="", depth=0, out=None, maxd=7):
    out = [] if out is None else out
    if depth > maxd:
        return out
    if isinstance(x, dict):
        for k, v in x.items():
            walk(v, f"{path}.{k}", depth + 1, out, maxd)
    elif isinstance(x, list):
        out.append(f"{path}: list[{len(x)}]")
        if x:
            if isinstance(x[0], dict):
                out.append(f"{path}[0] keys: {sorted(x[0].keys())}")
                out.append(f"{path}[0] = {json.dumps(x[0], default=str)[:1500]}")
            walk(x[0], f"{path}[0]", depth + 1, out, maxd)
    return out


date = sys.argv[1] if len(sys.argv) > 1 else str(pd.Timestamp.now(tz="America/New_York").date())
for url in [dfo.goalies_url(date), dfo.lines_url("TOR"), dfo.lines_url("COL")]:
    print("=" * 100, "\n", url)
    try:
        js = dfo.next_data(url)
    except Exception as e:
        print("FAILED:", e)
        continue
    pp = js.get("props", {}).get("pageProps", {})
    print("pageProps keys:", list(pp.keys()))
    for line in walk(pp)[:120]:
        print(line[:1800])
