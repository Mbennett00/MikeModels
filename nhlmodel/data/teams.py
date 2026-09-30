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


# display names and primary colours (dashboard / web page)
DISPLAY = {
    "ANA": ("Ducks", "#F47A38"), "BOS": ("Bruins", "#FFB81C"), "BUF": ("Sabres", "#2B5BD7"),
    "CAR": ("Hurricanes", "#CE1126"), "CBJ": ("Blue Jackets", "#2F5DA8"), "CGY": ("Flames", "#D2001C"),
    "CHI": ("Blackhawks", "#CF0A2C"), "COL": ("Avalanche", "#8A2432"), "DAL": ("Stars", "#1E8C5A"),
    "DET": ("Red Wings", "#CE1126"), "EDM": ("Oilers", "#FF4C00"), "FLA": ("Panthers", "#C8102E"),
    "LAK": ("Kings", "#A2AAAD"), "MIN": ("Wild", "#2E7D4F"), "MTL": ("Canadiens", "#AF1E2D"),
    "NJD": ("Devils", "#CE1126"), "NSH": ("Predators", "#FFB81C"), "NYI": ("Islanders", "#F47D30"),
    "NYR": ("Rangers", "#2F6FD6"), "OTT": ("Senators", "#C52032"), "PHI": ("Flyers", "#F74902"),
    "PIT": ("Penguins", "#FCB514"), "SEA": ("Kraken", "#68A2B9"), "SJS": ("Sharks", "#00889A"),
    "STL": ("Blues", "#2F6FD6"), "TBL": ("Lightning", "#2D5BB5"), "TOR": ("Maple Leafs", "#2A5CAA"),
    "UTA": ("Mammoth", "#6CACE4"), "VAN": ("Canucks", "#00843D"), "VGK": ("Golden Knights", "#B4975A"),
    "WPG": ("Jets", "#4B8BD6"), "WSH": ("Capitals", "#C8102E"),
}
