"""NFL teams: display name, nickname, colours (primary, secondary) and ESPN logo code."""
TEAMS = {
    "ARI": ("Arizona", "Cardinals", "#97233F", "#FFB612"), "ATL": ("Atlanta", "Falcons", "#A71930", "#000000"),
    "BAL": ("Baltimore", "Ravens", "#241773", "#9E7C0C"), "BUF": ("Buffalo", "Bills", "#00338D", "#C60C30"),
    "CAR": ("Carolina", "Panthers", "#0085CA", "#101820"), "CHI": ("Chicago", "Bears", "#0B162A", "#C83803"),
    "CIN": ("Cincinnati", "Bengals", "#FB4F14", "#000000"), "CLE": ("Cleveland", "Browns", "#311D00", "#FF3C00"),
    "DAL": ("Dallas", "Cowboys", "#003594", "#869397"), "DEN": ("Denver", "Broncos", "#FB4F14", "#002244"),
    "DET": ("Detroit", "Lions", "#0076B6", "#B0B7BC"), "GB": ("Green Bay", "Packers", "#203731", "#FFB612"),
    "HOU": ("Houston", "Texans", "#03202F", "#A71930"), "IND": ("Indianapolis", "Colts", "#002C5F", "#A2AAAD"),
    "JAX": ("Jacksonville", "Jaguars", "#006778", "#D7A22A"), "KC": ("Kansas City", "Chiefs", "#E31837", "#FFB81C"),
    "LA": ("Los Angeles", "Rams", "#003594", "#FFA300"), "LAC": ("Los Angeles", "Chargers", "#0080C6", "#FFC20E"),
    "LV": ("Las Vegas", "Raiders", "#000000", "#A5ACAF"), "MIA": ("Miami", "Dolphins", "#008E97", "#FC4C02"),
    "MIN": ("Minnesota", "Vikings", "#4F2683", "#FFC62F"), "NE": ("New England", "Patriots", "#002244", "#C60C30"),
    "NO": ("New Orleans", "Saints", "#D3BC8D", "#101820"), "NYG": ("New York", "Giants", "#0B2265", "#A71930"),
    "NYJ": ("New York", "Jets", "#125740", "#FFFFFF"), "PHI": ("Philadelphia", "Eagles", "#004C54", "#A5ACAF"),
    "PIT": ("Pittsburgh", "Steelers", "#FFB612", "#101820"), "SEA": ("Seattle", "Seahawks", "#002244", "#69BE28"),
    "SF": ("San Francisco", "49ers", "#AA0000", "#B3995D"), "TB": ("Tampa Bay", "Buccaneers", "#D50A0A", "#34302B"),
    "TEN": ("Tennessee", "Titans", "#0C2340", "#4B92DB"), "WAS": ("Washington", "Commanders", "#5A1414", "#FFB612"),
}
ESPN = {"LA": "lar", "WAS": "wsh"}
# Odds API full names -> nflverse codes
FULL = {f"{c} {n}": k for k, (c, n, _, _) in TEAMS.items()}
FULL.update({"Los Angeles Rams": "LA", "Los Angeles Chargers": "LAC", "New York Giants": "NYG", "New York Jets": "NYJ",
             "Washington Commanders": "WAS"})


def logo(code: str) -> str:
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{ESPN.get(code, code.lower())}.png"


def info(code: str) -> dict:
    c, n, p, s = TEAMS.get(code, (code, code, "#555555", "#999999"))
    return dict(abbr=code, city=c, name=n, color=p, color2=s, logo=logo(code))
