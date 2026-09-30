import numpy as np
import pytest
from scipy import stats

from nhlmodel.distributions import bivariate_poisson_logpmf, bivariate_poisson_matrix, fit_nb_r


def test_bivariate_margins_and_covariance():
    m = bivariate_poisson_matrix(3.1, 2.7, 0.15)
    k = np.arange(m.shape[0])
    assert m.sum() == pytest.approx(1)
    assert (m.sum(1) * k).sum() == pytest.approx(3.1, abs=1e-3)
    assert (m.sum(0) * k).sum() == pytest.approx(2.7, abs=1e-3)
    eh, ea = 3.1, 2.7
    cov = sum(m[i, j] * (i - eh) * (j - ea) for i in k for j in k)
    assert cov == pytest.approx(0.15, abs=2e-3)


def test_logpmf_matches_matrix():
    m = bivariate_poisson_matrix(3.0, 2.5, 0.1)
    h, a = np.array([0, 2, 5, 3]), np.array([0, 3, 1, 3])
    lp = bivariate_poisson_logpmf(h, a, np.full(4, 3.0), np.full(4, 2.5), 0.1)
    assert np.exp(lp) == pytest.approx(m[h, a], rel=1e-6)


def test_nb_dispersion_recovered():
    rng = np.random.default_rng(0)
    mu = rng.uniform(1, 4, 20000)
    r = 7.0
    x = stats.nbinom.rvs(r, r / (r + mu), random_state=rng)
    r_hat, _ = fit_nb_r(x, mu)
    assert 5 < r_hat < 10
    y = rng.poisson(mu)
    assert fit_nb_r(y, mu)[0] > 50
