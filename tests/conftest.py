import pytest

from mtg_prices.db import Database


@pytest.fixture
def db():
    database = Database(":memory:")
    database.init()
    yield database
    database.close()
