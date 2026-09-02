"""3a-1 스캐폴딩 — 빌드·임포트·설정 로딩 검증."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import aegisvest
from aegisvest import config
from aegisvest.schemas import Category, Regime, ToolError, Verdict


def test_package_imports() -> None:
    assert aegisvest.__version__ == "0.1.0"
    for mod in (
        "aegisvest.tools",
        "aegisvest.agents",
        "aegisvest.broker",
        "aegisvest.diary",
    ):
        assert importlib.import_module(mod) is not None


def test_settings_load_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MANUAL_ISM_PMI", raising=False)
    config.get_settings.cache_clear()
    s = config.get_settings()
    assert s.mode == "paper"
    assert s.dry_run is True
    assert s.universe == "combined"
    assert s.model == "deepseek/deepseek-chat"
    assert s.max_high_risk_exposure == 0.20
    assert isinstance(s.state_dir, Path)
    assert s.manual_ism_pmi is None


def test_bool_env_empty_string_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRY_RUN", "")  # 존재하나 빈 값 → 안전한 기본(True) 유지
    config.get_settings.cache_clear()
    assert config.get_settings().dry_run is True
    monkeypatch.setenv("DRY_RUN", "false")
    config.get_settings.cache_clear()
    assert config.get_settings().dry_run is False


def test_ensure_runtime_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    config.get_settings.cache_clear()
    config.ensure_runtime_dirs()
    assert (tmp_path / "state").is_dir()
    assert (tmp_path / "out").is_dir()
    assert (tmp_path / "cache").is_dir()


def test_schema_enums() -> None:
    assert [c.value for c in Category] == ["LOW", "MID", "HIGH"]
    assert set(Regime) == {Regime.BULL, Regime.NEUTRAL, Regime.BEAR, Regime.CRISIS}
    assert Verdict.REJECTED == "REJECTED"
    err = ToolError(error="not found", field="ticker")
    assert err.model_dump() == {"error": "not found", "field": "ticker"}


def test_config_dir_present() -> None:
    assert config.CONFIG_DIR.is_dir()
