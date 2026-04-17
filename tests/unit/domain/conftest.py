import pytest


@pytest.fixture(autouse=True, scope="function")
def fresh_db():
    pass
