"""Team display data: names and primary colours (for win-probability bars)."""

TEAMS = {
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


def logo_url(team: str) -> str:
    return f"https://assets.nhle.com/logos/nhl/svg/{team}_light.svg"


def nickname(team: str) -> str:
    return TEAMS.get(team, (team, "#888"))[0]


def color(team: str) -> str:
    return TEAMS.get(team, (team, "#888"))[1]
