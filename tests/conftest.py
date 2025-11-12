import warnings

import pytest


@pytest.fixture
def captured_warnings():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        yield w