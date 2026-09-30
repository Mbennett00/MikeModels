"""Section 8: fair odds, no-vig book prices, edge, flags."""
from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np


def american_to_prob(price: float) -> float:
    """Implied probability (with vig) of an American price."""
    price = float(price)
    if price < 0:
        return -price / (-price + 100.0)
    return 100.0 / (price + 100.0)


def american_to_decimal(price: float) -> float:
    price = float(price)
    return 1.0 + (price / 100.0 if price > 0 else 100.0 / -price)


def fair_american(p: float) -> float:
    """Fair American odds: P>=0.5 -> -100P/(1-P); else +100(1-P)/P."""
    p = min(max(float(p), 1e-9), 1 - 1e-9)
    if p >= 0.5:
        return -100.0 * p / (1.0 - p)
    return 100.0 * (1.0 - p) / p


def format_american(x: float) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{x:+.0f}"


def novig_two_way(price_a: float, price_b: float) -> tuple[float, float]:
    """Normalise both sides' implied probabilities to sum to 1 (multiplicative)."""
    pa, pb = american_to_prob(price_a), american_to_prob(price_b)
    s = pa + pb
    return pa / s, pb / s


def novig_n_way(prices: Sequence[float]) -> list[float]:
    ps = [american_to_prob(p) for p in prices]
    s = sum(ps)
    return [p / s for p in ps]


def novig_one_sided(price: float, assumed_hold: float) -> float:
    """Only one side posted: remove a *conservative* (small) assumed hold.

    p_novig = p_implied / (1 + hold). A small hold keeps the book's probability
    high, which shrinks our measured edge rather than inflating it.
    """
    return american_to_prob(price) / (1.0 + assumed_hold)


def edge(p_model: float, p_book_novig: float) -> float:
    return float(p_model) - float(p_book_novig)


def expected_value(p_model: float, price: float) -> float:
    """EV per 1 unit staked at the given American price."""
    return p_model * (american_to_decimal(price) - 1.0) - (1.0 - p_model)


def consensus_novig(book_probs: Iterable[float]) -> float:
    """Median of each book's own no-vig probability (robust to one stale book)."""
    arr = np.asarray(list(book_probs), dtype=float)
    arr = arr[~np.isnan(arr)]
    return float(np.median(arr)) if arr.size else float("nan")
