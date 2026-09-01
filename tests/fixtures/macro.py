"""중립 MacroData 빌더 — 레짐 엔진 테스트에서 한 축씩 바꿔 검증한다."""

from __future__ import annotations

from typing import Any

from aegisvest.schemas import MacroData

# 전부 축 점수 0 이 나오는 중립값
_NEUTRAL: dict[str, Any] = {
    "vix": 20.0,
    "vix3m": 21.0,  # 콘탱고이나 VIX>=15 → 0
    "vix_1d_change_pct": 0.0,
    "spx_last": 100.0,
    "spx_sma_200": 100.0,
    "spx_sma_50": 100.0,
    "spx_50_slope_20d": 0.0,
    "pct_above_200dma": 50.0,
    "pct_above_200dma_4w_change": 0.0,
    "yc_10y_3m_bp": 50.0,
    "yc_10y_3m_4w_change_bp": 0.0,
    "yc_10y_3m_prev_bp": 50.0,
    "yc_10y_2y_bp": 30.0,
    "fed_funds_trend": "hiking",  # +2 는 hold/cutting 만
    "hy_oas_bp": 400.0,
    "hy_oas_4w_change_bp": 0.0,
    "wei": 0.5,
    "regional_fed_mfg_avg": 0.0,
    "claims_4w_trend_pct": 0.0,
    "ism_pmi": None,
    "as_of": "2026-09-01",
    "stale_fields": [],
}


def macro(**overrides: Any) -> MacroData:
    return MacroData(**{**_NEUTRAL, **overrides})
