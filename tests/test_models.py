"""Small model behavior tests."""

from neobatista.models import format_duration


def test_format_duration() -> None:
    assert format_duration(None) == "live/unknown"
    assert format_duration(65) == "1:05"
    assert format_duration(3661) == "1:01:01"
    assert format_duration(-1) == "0:00"
