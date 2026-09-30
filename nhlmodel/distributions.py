"""Score and count distributions: bivariate Poisson, negative binomial."""
from __future__ import annotations

import numpy as np
from scipy import stats
from scipy.special import gammaln

MAX_GOALS = 15


def bivariate_poisson_matrix(lam_h: float, lam_a: float, lam3: float,
                             n: int = MAX_GOALS) -> np.ndarray:
    """P(H=h, A=a) with H = X1+X3, A = X2+X3, Xi ~ Poisson.

    The marginal means stay (lam_h, lam_a); lam3 is the covariance. lam3 is
    clipped so that lam1, lam2 stay positive.
    """
    lam3 = float(np.clip(lam3, 0.0, 0.9 * min(lam_h, lam_a)))
    l1, l2 = lam_h - lam3, lam_a - lam3
    k = np.arange(n + 1)
    p1 = stats.poisson.pmf(k, l1)
    p2 = stats.poisson.pmf(k, l2)
    p3 = stats.poisson.pmf(k, lam3)
    m = np.zeros((n + 1, n + 1))
    for z in range(n + 1):
        if p3[z] < 1e-14:
            continue
        # shift the independent outer product by (z, z)
        m[z:, z:] += p3[z] * np.outer(p1[: n + 1 - z], p2[: n + 1 - z])
    return m / m.sum()


def bivariate_poisson_logpmf(h, a, lam_h, lam_a, lam3: float) -> np.ndarray:
    """Vectorised log P(h, a); used to fit lam3 by maximum likelihood."""
    h = np.asarray(h, int); a = np.asarray(a, int)
    lam_h = np.asarray(lam_h, float); lam_a = np.asarray(lam_a, float)
    l3 = np.maximum(np.minimum(lam3, 0.9 * np.minimum(lam_h, lam_a)), 1e-12)
    l1, l2 = lam_h - l3, lam_a - l3
    zmax = int(np.minimum(h, a).max()) if len(h) else 0
    terms = np.full((zmax + 1, len(h)), -np.inf)
    for z in range(zmax + 1):
        ok = np.minimum(h, a) >= z
        hz, az = np.where(ok, h - z, 0), np.where(ok, a - z, 0)
        t = (stats.poisson.logpmf(hz, l1) + stats.poisson.logpmf(az, l2)
             + stats.poisson.logpmf(z, l3))
        terms[z] = np.where(ok, t, -np.inf)
    return np.logaddexp.reduce(terms, axis=0)


def nb_params(mean: np.ndarray | float, r: float):
    """scipy nbinom(n=r, p) with the given mean. Var = mean + mean^2 / r."""
    mean = np.asarray(mean, float)
    p = r / (r + mean)
    return r, p


def nb_sf(x: float, mean, r: float):
    """P(X > x) under NB(mean, r). For line X.5 pass x = floor(X.5)."""
    n, p = nb_params(mean, r)
    return stats.nbinom.sf(np.floor(x), n, p)


def nb_logpmf(k, mean, r: float):
    n, p = nb_params(mean, r)
    return stats.nbinom.logpmf(k, n, p)


def poisson_sf(x: float, mean):
    return stats.poisson.sf(np.floor(x), mean)


def fit_nb_r(counts: np.ndarray, means: np.ndarray, grid=None) -> tuple[float, float]:
    """MLE of NB dispersion r given out-of-sample means. Returns (r, loglik).

    r = inf (returned as 1e6) means no overdispersion: Poisson is adequate.
    """
    counts = np.asarray(counts, float); means = np.clip(np.asarray(means, float), 1e-6, None)
    if grid is None:
        grid = np.concatenate([np.geomspace(0.5, 200, 60), [1e6]])
    best = (None, -np.inf)
    for r in grid:
        ll = float(np.sum(_nb_ll(counts, means, r)))
        if ll > best[1]:
            best = (float(r), ll)
    return best


def _nb_ll(k, mu, r):
    return (gammaln(k + r) - gammaln(r) - gammaln(k + 1)
            + r * np.log(r / (r + mu)) + k * np.log(mu / (r + mu)))
