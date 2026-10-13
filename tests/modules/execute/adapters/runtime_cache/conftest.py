from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database() -> Iterator[None]:
    yield
