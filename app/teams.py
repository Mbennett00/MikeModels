"""Team display data for the dashboard (shared with the web page)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from nhlmodel.data.teams import DISPLAY as TEAMS  # noqa: E402


def logo_url(team: str) -> str:
    return f"https://assets.nhle.com/logos/nhl/svg/{team}_light.svg"


def nickname(team: str) -> str:
    return TEAMS.get(team, (team, "#888"))[0]


def color(team: str) -> str:
    return TEAMS.get(team, (team, "#888"))[1]
