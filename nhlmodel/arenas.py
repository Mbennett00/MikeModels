"""Approximate arena coordinates (lat, lon) for travel distance in rest_factor."""
import math

ARENAS = {
    "ANA": (33.808, -117.877), "BOS": (42.366, -71.062), "BUF": (42.875, -78.876), "CAR": (35.803, -78.722),
    "CBJ": (39.969, -83.006), "CGY": (51.037, -114.052), "CHI": (41.881, -87.674), "COL": (39.749, -105.008),
    "DAL": (32.790, -96.810), "DET": (42.341, -83.055), "EDM": (53.547, -113.498), "FLA": (26.158, -80.326),
    "LAK": (34.043, -118.267), "MIN": (44.945, -93.101), "MTL": (45.496, -73.569), "NJD": (40.734, -74.171),
    "NSH": (36.159, -86.778), "NYI": (40.723, -73.591), "NYR": (40.751, -73.994), "OTT": (45.297, -75.927),
    "PHI": (39.901, -75.172), "PIT": (40.440, -79.989), "SEA": (47.622, -122.354), "SJS": (37.333, -121.901),
    "STL": (38.627, -90.203), "TBL": (27.943, -82.452), "TOR": (43.643, -79.379), "UTA": (40.768, -111.901),
    "VAN": (49.278, -123.109), "VGK": (36.103, -115.178), "WPG": (49.893, -97.144), "WSH": (38.898, -77.021),
}


def distance_km(a: str, b: str) -> float:
    if a not in ARENAS or b not in ARENAS:
        return 0.0
    (la1, lo1), (la2, lo2) = ARENAS[a], ARENAS[b]
    p1, p2 = math.radians(la1), math.radians(la2)
    dphi, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))
