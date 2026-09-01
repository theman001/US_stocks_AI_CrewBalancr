"""공용 pytest fixture."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from aegisvest import config


@pytest.fixture(autouse=True)
def _isolate_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """모든 테스트를 격리된 임시 state/output/cache 로 실행하고 설정 캐시를 리셋한다."""
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    for key in ("MODE", "DRY_RUN", "UNIVERSE", "MATTERMOST_WEBHOOK_URL", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()
