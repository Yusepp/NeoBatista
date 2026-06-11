"""Container heartbeat tests."""

from __future__ import annotations

import time
from pathlib import Path

from pytest import MonkeyPatch

from scripts import healthcheck


def test_healthcheck_fresh_and_stale(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    heartbeat = tmp_path / "heartbeat"
    monkeypatch.setattr(healthcheck, "HEARTBEAT_FILE", heartbeat)

    assert healthcheck.main() == 1
    heartbeat.write_text(str(time.time()), encoding="ascii")
    assert healthcheck.main() == 0
    heartbeat.write_text(str(time.time() - 100), encoding="ascii")
    assert healthcheck.main() == 1
