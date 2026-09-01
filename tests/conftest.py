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
    # 개발자 .env 에 의존하지 않도록 키·모드를 제거. 필요한 테스트는 monkeypatch.setenv.
    for key in (
        "MODE",
        "DRY_RUN",
        "UNIVERSE",
        "MATTERMOST_WEBHOOK_URL",
        "MM_WEBHOOK_RESEARCH",
        "MM_WEBHOOK_DECISIONS",
        "MM_WEBHOOK_ALERTS",
        "DEEPSEEK_API_KEY",
        "FMP_API_KEY",
        "FRED_API_KEY",
        "NASDAQ_DATA_LINK_API_KEY",
        "MANUAL_ISM_PMI",
        "MONTHLY_CONTRIBUTION_KRW",
    ):
        monkeypatch.delenv(key, raising=False)
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()
