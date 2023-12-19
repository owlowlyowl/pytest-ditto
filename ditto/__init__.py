import pytest

from ditto._unittest import DittoTestCase

dev = pytest.mark.env("dev")

record = pytest.mark.record