import pytest

from nhlmodel.data.synthetic import generate


@pytest.fixture(scope="session")
def league():
    tables, truth = generate(seed=3, seasons=(2024,), n_days=70)
    return tables, truth
