"""Game-time weather from Open-Meteo (https://open-meteo.com, free, no key): forecast for the hours around kickoff.

What moves games, measured on 2018-25 (see README): rain at kickoff takes about 6 points off the total; wind over
10 mph and temperatures under 40F take a little more. For props, wind and rain cut passing and receiving
(receptions, receiving yards, passing yards) by up to ~15%; rushing is unaffected.

Domes are ignored. Retractable roofs are treated as closed (teams close them in bad weather, and in good weather
the conditions don't move anything). nflverse marks some open-air international venues as domes; those are fixed here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import requests

URL = "https://api.open-meteo.com/v1/forecast"
STADIUMS = {   # stadium_id: (lat, lon)
    "ATL97": (33.755, -84.401), "BAL00": (39.278, -76.623), "BOS00": (42.091, -71.264), "BUF00": (42.774, -78.787),
    "CAR00": (35.226, -80.853), "CHI98": (41.862, -87.617), "CIN00": (39.095, -84.516), "CLE00": (41.506, -81.700),
    "DAL00": (32.748, -97.093), "DEN00": (39.744, -105.020), "DET00": (42.340, -83.046), "GNB00": (44.501, -88.062),
    "HOU00": (29.685, -95.411), "IND00": (39.760, -86.164), "JAX00": (30.324, -81.637), "KAN00": (39.049, -94.484),
    "LAX01": (33.953, -118.339), "LON00": (51.556, -0.280), "LON02": (51.604, -0.066), "MAD01": (40.453, -3.688),
    "MEL00": (-37.820, 144.983), "MEX00": (19.303, -99.150), "MIA00": (25.958, -80.239), "MIN01": (44.974, -93.258),
    "MUN01": (48.219, 11.625), "NAS00": (36.166, -86.771), "NOR00": (29.951, -90.081), "NYC01": (40.814, -74.074),
    "PAR00": (48.924, 2.360), "PHI00": (39.901, -75.168), "PHO00": (33.528, -112.263), "PIT00": (40.447, -80.016),
    "RIO00": (-22.912, -43.230), "SEA00": (47.595, -122.332), "SFO01": (37.403, -121.970), "TAM00": (27.976, -82.503),
    "VEG00": (36.091, -115.184), "WAS00": (38.908, -76.864), "FRA00": (50.069, 8.645), "GER00": (48.219, 11.625),
    "SAO00": (-23.545, -46.474),
}
INDOOR = {"DET00", "LAX01", "MIN01", "NOR00", "VEG00"}
RETRACTABLE = {"ATL97", "DAL00", "HOU00", "IND00", "PHO00", "MAD01"}
OPEN_AIR = {"MEL00", "PAR00", "MUN01", "GER00", "FRA00", "RIO00", "SAO00", "LON00", "LON02", "MEX00"}


def exposure(stadium_id, roof) -> str:
    """'outdoor', 'dome' or 'retractable' (treated as closed)."""
    if stadium_id in OPEN_AIR:
        return "outdoor"
    if stadium_id in INDOOR or str(roof) == "dome":
        return "dome"
    if stadium_id in RETRACTABLE or str(roof) in ("closed", "open", "retractable"):
        return "retractable"
    return "outdoor"


def rain_flag(weather_text) -> float:
    """Historical (play-by-play gamebook text at kickoff): 1 if it was raining."""
    return float(bool(isinstance(weather_text, str) and any(k in weather_text.lower() for k in ("rain", "shower", "drizzle", "storm"))))


def forecast(stadium_id: str, kick_utc: pd.Timestamp, log=print) -> dict | None:
    """Kickoff-to-+3h forecast: temp F, wind / gust mph, chance of rain, rain mm/h, snow cm/h, and the rain input
    the model uses (chance of rain, discounted when the forecast amount is light)."""
    if stadium_id not in STADIUMS:
        return None
    lat, lon = STADIUMS[stadium_id]
    try:
        r = requests.get(URL, timeout=20, params=dict(
            latitude=lat, longitude=lon, timezone="UTC", forecast_days=16, temperature_unit="fahrenheit",
            wind_speed_unit="mph", hourly="temperature_2m,wind_speed_10m,wind_gusts_10m,precipitation_probability,"
                                           "rain,showers,snowfall,weather_code"))
        r.raise_for_status()
        h = pd.DataFrame(r.json()["hourly"])
    except Exception as e:
        log(f"weather {stadium_id}: {e}")
        return None
    h["time"] = pd.to_datetime(h.time).dt.tz_localize("UTC")
    k = pd.Timestamp(kick_utc).floor("h")
    w = h[(h.time >= k) & (h.time < k + pd.Timedelta(hours=3))]
    if w.empty:
        return None
    pp = float(w.precipitation_probability.fillna(0).mean()) / 100
    rain_mm = float((w.rain.fillna(0) + w.showers.fillna(0)).mean())
    snow = float(w.snowfall.fillna(0).mean())
    rain = pp if (w.rain.fillna(0) + w.showers.fillna(0)).max() >= 0.1 else 0.3 * pp
    return dict(temp=round(float(w.temperature_2m.mean()), 1), wind=round(float(w.wind_speed_10m.mean()), 1),
                gust=round(float(w.wind_gusts_10m.max()), 1), pp=round(pp, 2), rain_mm=round(rain_mm, 2),
                snow_cm=round(snow, 2), rain=round(float(np.clip(rain, 0, 1)), 2), code=int(w.weather_code.mode().iat[0]))


def describe(w: dict | None, expo: str) -> tuple[str, str]:
    """(icon, short text) for the game card."""
    if expo != "outdoor":
        return "🏟️", "Dome" if expo == "dome" else "Roof (closed in bad weather)"
    if not w:
        return "🌤️", "Forecast not out yet"
    icon = "❄️" if w["snow_cm"] > 0.05 else "🌧️" if w["rain"] >= 0.35 else "🌬️" if w["wind"] >= 15 else \
        "🥶" if w["temp"] < 35 else "☁️" if w["code"] in (2, 3, 45, 48) else "☀️"
    txt = f"{round(w['temp'])}° · {round(w['wind'])} mph"
    if w["pp"] >= 0.2:
        txt += f" · {round(100 * w['pp'])}% rain"
    return icon, txt


# props: share of the calm-weather projection that survives (measured on 2022-26 projections vs results)
PROP_WX = {"pass_yds": dict(w12=0.91, w18=0.85, rain=0.85), "rec_yds": dict(w12=0.92, w18=0.83, rain=0.84),
           "rec": dict(w12=0.94, w18=0.89, rain=0.89)}


def prop_factor(market: str, wind: float, rain: float) -> float:
    f = PROP_WX.get(market)
    if not f:
        return 1.0
    fw = 1.0 if wind < 12 else f["w12"] if wind < 18 else f["w18"]
    fr = 1.0 - rain * (1 - f["rain"])
    return max(fw * fr, 0.7)
