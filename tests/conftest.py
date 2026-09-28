import pytest

from connie_lite.graph.build import build_graph
from connie_lite.graph.ingest import build_alias_table, load_corpus


@pytest.fixture(scope="session")
def corpus():
    return load_corpus()


@pytest.fixture(scope="session")
def profile(corpus):
    return corpus[0]


@pytest.fixture(scope="session")
def alerts(corpus):
    return corpus[1]


@pytest.fixture(scope="session")
def aliases(profile):
    return build_alias_table(profile)


@pytest.fixture(scope="session")
def store(profile, alerts):
    return build_graph(profile, alerts)
