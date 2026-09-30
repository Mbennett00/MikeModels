"""Team name <-> abbreviation (for odds feeds that use full names)."""
import re
import unicodedata

FULL = {
    "Anaheim Ducks": "ANA", "Boston Bruins": "BOS", "Buffalo Sabres": "BUF", "Carolina Hurricanes": "CAR",
    "Columbus Blue Jackets": "CBJ", "Calgary Flames": "CGY", "Chicago Blackhawks": "CHI", "Colorado Avalanche": "COL",
    "Dallas Stars": "DAL", "Detroit Red Wings": "DET", "Edmonton Oilers": "EDM", "Florida Panthers": "FLA",
    "Los Angeles Kings": "LAK", "Minnesota Wild": "MIN", "Montreal Canadiens": "MTL", "Montréal Canadiens": "MTL",
    "New Jersey Devils": "NJD", "Nashville Predators": "NSH", "New York Islanders": "NYI", "New York Rangers": "NYR",
    "Ottawa Senators": "OTT", "Philadelphia Flyers": "PHI", "Pittsburgh Penguins": "PIT", "Seattle Kraken": "SEA",
    "San Jose Sharks": "SJS", "St Louis Blues": "STL", "St. Louis Blues": "STL", "Tampa Bay Lightning": "TBL",
    "Toronto Maple Leafs": "TOR", "Utah Hockey Club": "UTA", "Utah Mammoth": "UTA", "Utah Hockey Club ": "UTA",
    "Vancouver Canucks": "VAN", "Vegas Golden Knights": "VGK", "Winnipeg Jets": "WPG", "Washington Capitals": "WSH",
}


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", "", s.lower().replace("-", " "))
    return " ".join(s.split())


_BY_NORM = {norm_name(k): v for k, v in FULL.items()}


def abbrev(full_name: str) -> str | None:
    n = norm_name(full_name)
    if n in _BY_NORM:
        return _BY_NORM[n]
    for k, v in _BY_NORM.items():   # e.g. "Utah" variants
        if k.split()[0] == n.split()[0] and n.split()[-1] == k.split()[-1]:
            return v
    return None
