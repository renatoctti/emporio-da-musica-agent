import pytest

from emporio.results import error, is_error, round_brl


def test_error_round_trip():
    result = error("not_verified", "Verify first.")
    assert result == {"error": {"code": "not_verified", "message": "Verify first."}}
    assert is_error(result)
    assert not is_error({"results": []})


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.125, 0.13), (2.675, 2.68), (439.2, 439.2), (10924.049999999999, 10924.05), (0.0, 0.0)],
)
def test_round_brl_is_half_up(value, expected):
    assert round_brl(value) == expected
