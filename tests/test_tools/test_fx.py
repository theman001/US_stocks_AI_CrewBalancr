"""tools/fx.py — USD/KRW 환율."""

from __future__ import annotations

import pandas as pd
import pytest

from aegisvest.schemas import ToolError
from aegisvest.tools import fx as mod


def _frame(close: float) -> pd.DataFrame:
    idx = pd.date_range("2026-08-01", periods=3, freq="D")
    return pd.DataFrame({"Close": [close - 1, close - 0.5, close]}, index=idx)


def test_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "history", lambda s, ttl: _frame(1385.0))
    assert mod.usd_krw() == pytest.approx(1385.0)


def test_network_failure_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(s: str, ttl: float) -> pd.DataFrame:
        raise RuntimeError("net down")

    monkeypatch.setattr(mod, "history", _boom)
    r = mod.usd_krw()
    assert isinstance(r, ToolError) and r.field == "fx"


def test_outlier_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "history", lambda s, ttl: _frame(42.0))
    assert isinstance(mod.usd_krw(), ToolError)


def test_empty_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "history", lambda s, ttl: pd.DataFrame())
    assert isinstance(mod.usd_krw(), ToolError)
