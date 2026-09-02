"""RegimeScoreCalculator — TEST_GUIDE 시나리오 2 (필수: 경계값·결정성·CRISIS·EMA)."""

from __future__ import annotations

import pytest

from aegisvest.schemas import CrisisState, Regime, RegimeHistoryPoint
from aegisvest.tools.regime import _ema, regime_score
from tests.fixtures.macro import macro

# ─────────────── 축별 경계값 ───────────────


def test_vix_axis_boundaries() -> None:
    assert regime_score(macro(vix=14.9, vix3m=20.0)).axis_scores["vix"] == 2
    assert regime_score(macro(vix=15.0, vix3m=20.0)).axis_scores["vix"] == 0  # <15 아님
    assert regime_score(macro(vix=28.0, vix3m=30.0)).axis_scores["vix"] == 0
    assert regime_score(macro(vix=28.1, vix3m=30.0)).axis_scores["vix"] == -2


def test_vix_backwardation_is_minus2() -> None:
    r = regime_score(macro(vix=18.0, vix3m=17.0))  # vix >= vix3m
    assert r.axis_scores["vix"] == -2


def test_vix_no_vix3m_caps_at_neutral() -> None:
    r = regime_score(macro(vix=12.0, vix3m=None))  # 콘탱고 판정 불가 → +2 불가
    assert r.axis_scores["vix"] == 0


def test_spx_trend_axis() -> None:
    up = regime_score(macro(spx_last=110.0, spx_sma_200=100.0, spx_50_slope_20d=0.01))
    assert up.axis_scores["spx_trend"] == 2
    down = regime_score(macro(spx_last=90.0, spx_sma_200=100.0, spx_50_slope_20d=-0.01))
    assert down.axis_scores["spx_trend"] == -2
    mixed = regime_score(macro(spx_last=110.0, spx_sma_200=100.0, spx_50_slope_20d=-0.01))
    assert mixed.axis_scores["spx_trend"] == 0


def test_breadth_axis() -> None:
    assert regime_score(macro(pct_above_200dma=61.0)).axis_scores["breadth"] == 2
    assert regime_score(macro(pct_above_200dma=60.0)).axis_scores["breadth"] == 0
    assert regime_score(macro(pct_above_200dma=34.9)).axis_scores["breadth"] == -2
    assert regime_score(macro(pct_above_200dma=None)).axis_scores["breadth"] is None


def test_yield_axis() -> None:
    pos = regime_score(macro(yc_10y_3m_bp=40.0, fed_funds_trend="hold"))
    assert pos.axis_scores["yield_policy"] == 2
    deep = regime_score(macro(yc_10y_3m_bp=-60.0))
    assert deep.axis_scores["yield_policy"] == -2
    resteepen = regime_score(
        macro(yc_10y_3m_bp=5.0, yc_10y_3m_prev_bp=-20.0, yc_10y_3m_4w_change_bp=25.0)
    )
    assert resteepen.axis_scores["yield_policy"] == -2


def test_credit_axis() -> None:
    calm = regime_score(macro(hy_oas_bp=300.0, hy_oas_4w_change_bp=-10.0))
    assert calm.axis_scores["credit"] == 2
    wide = regime_score(macro(hy_oas_bp=520.0))
    assert wide.axis_scores["credit"] == -2
    spike = regime_score(macro(hy_oas_bp=400.0, hy_oas_4w_change_bp=80.0))
    assert spike.axis_scores["credit"] == -2


def test_economy_subscores_boundaries() -> None:
    # WEI 상향
    r = regime_score(macro(wei=2.0, regional_fed_mfg_avg=11.0, claims_4w_trend_pct=-0.06))
    assert r.economy_subscores == {"wei": 2, "regional": 2, "claims": 2}
    assert r.axis_scores["economy"] == 2
    # claims 하향 의미 (값 낮을수록 +)
    r2 = regime_score(macro(wei=-1.5, regional_fed_mfg_avg=-11.0, claims_4w_trend_pct=0.15))
    assert r2.economy_subscores == {"wei": -2, "regional": -2, "claims": -2}


# ─────────────── 합산 / 정규화 / 라벨 ───────────────


def test_total_score_full_bull() -> None:
    r = regime_score(
        macro(
            vix=12.0,
            vix3m=20.0,
            spx_last=110.0,
            spx_sma_200=100.0,
            spx_50_slope_20d=0.02,
            pct_above_200dma=70.0,
            yc_10y_3m_bp=40.0,
            fed_funds_trend="cutting",
            hy_oas_bp=300.0,
            hy_oas_4w_change_bp=-20.0,
            wei=2.5,
            regional_fed_mfg_avg=12.0,
            claims_4w_trend_pct=-0.08,
        )
    )
    assert r.axis_scores == {
        "vix": 2,
        "spx_trend": 2,
        "breadth": 2,
        "yield_policy": 2,
        "credit": 2,
        "economy": 2,
    }
    assert r.n_axes_present == 6
    assert r.total_score == 12
    assert r.regime is Regime.BULL


def test_low_confidence_demotes_label_to_neutral() -> None:
    # vix + spx 만 present (FRED 축 전부 None) → 2축 < 4 → low_confidence
    r = regime_score(
        macro(
            vix=12.0,
            vix3m=20.0,
            spx_last=110.0,
            spx_sma_200=100.0,
            spx_50_slope_20d=0.02,
            pct_above_200dma=None,
            yc_10y_3m_bp=None,
            hy_oas_bp=None,
            wei=None,
            regional_fed_mfg_avg=None,
            claims_4w_trend_pct=None,
        )
    )
    assert r.n_axes_present == 2
    assert r.low_confidence is True
    assert r.total_score == 12  # 여전히 계산됨 (history/EMA 연속성)
    assert r.regime is Regime.NEUTRAL  # 라벨은 강등


def test_low_confidence_still_allows_crisis() -> None:
    r = regime_score(
        macro(
            vix=40.0,
            vix3m=45.0,
            yc_10y_3m_bp=None,
            hy_oas_bp=None,
            wei=None,
            regional_fed_mfg_avg=None,
            claims_4w_trend_pct=None,
            pct_above_200dma=None,
        )
    )
    assert r.low_confidence is True
    assert r.regime is Regime.CRISIS  # CRISIS 오버라이드는 raw 값이라 영향 없음


def test_normalization_when_axis_missing() -> None:
    # breadth None → 5축. 나머지 전부 +2 → sum 10 → round(10 * 6/5) = 12
    r = regime_score(
        macro(
            vix=12.0,
            vix3m=20.0,
            spx_last=110.0,
            spx_sma_200=100.0,
            spx_50_slope_20d=0.02,
            pct_above_200dma=None,
            yc_10y_3m_bp=40.0,
            fed_funds_trend="cutting",
            hy_oas_bp=300.0,
            hy_oas_4w_change_bp=-20.0,
            wei=2.5,
            regional_fed_mfg_avg=12.0,
            claims_4w_trend_pct=-0.08,
        )
    )
    assert r.n_axes_present == 5
    assert r.total_score == 12  # clamp


def test_label_boundaries() -> None:
    # 중립 baseline = 0 → NEUTRAL
    assert regime_score(macro()).regime is Regime.NEUTRAL
    # vix+2, credit+2, economy+1(하위 3신호 모두 +1) → sum 5, 6축 → 5 → BULL
    r_bull = regime_score(
        macro(
            vix=12.0,
            vix3m=20.0,
            hy_oas_bp=300.0,
            hy_oas_4w_change_bp=-1.0,
            wei=1.5,
            regional_fed_mfg_avg=4.0,
            claims_4w_trend_pct=-0.02,
        )
    )
    assert r_bull.axis_scores["economy"] == 1
    assert r_bull.total_score == 5
    assert r_bull.regime is Regime.BULL

    # sum 4 → NEUTRAL (BULL 문턱 미달)
    r_neutral = regime_score(macro(vix=12.0, vix3m=20.0, hy_oas_bp=300.0, hy_oas_4w_change_bp=-1.0))
    assert r_neutral.total_score == 4
    assert r_neutral.regime is Regime.NEUTRAL


# ─────────────── CRISIS 오버라이드 ───────────────


def test_crisis_vix_override() -> None:
    r = regime_score(macro(vix=36.0, vix3m=40.0))
    assert r.crisis_active is True
    assert r.regime is Regime.CRISIS
    assert r.crisis_state.active is True
    assert r.crisis_state.triggered_date == "2026-09-01"


def test_crisis_hy_oas_override() -> None:
    r = regime_score(macro(hy_oas_bp=750.0))
    assert r.regime is Regime.CRISIS


def test_crisis_vix_1d_spike_override() -> None:
    r = regime_score(macro(vix=22.0, vix3m=23.0, vix_1d_change_pct=0.60))  # +60% > 50%
    assert r.regime is Regime.CRISIS
    assert "급등" in (r.crisis_reason or "")
    # 경계: 정확히 50% 는 아님
    r2 = regime_score(macro(vix=22.0, vix3m=23.0, vix_1d_change_pct=0.50))
    assert r2.crisis_active is False


def test_crisis_spx_drawdown_override() -> None:
    r = regime_score(macro(spx_last=85.0, spx_sma_200=100.0))  # -15%
    assert r.regime is Regime.CRISIS


def test_crisis_latch_and_exit() -> None:
    prior = CrisisState(active=True, triggered_date="2026-08-20")
    # 조건 해소, 스무딩 -3 (>= -5), 8거래일 경과 (8/20→9/1) → 해제
    r = regime_score(macro(as_of="2026-09-01"), crisis_state=prior)
    assert r.crisis_active is False
    assert r.regime is Regime.NEUTRAL

    # 3거래일만 경과 → 래치 유지
    prior2 = CrisisState(active=True, triggered_date="2026-08-27")
    r2 = regime_score(macro(as_of="2026-09-01"), crisis_state=prior2)
    assert r2.crisis_active is True

    # 경과했으나 스무딩이 낮음(-6) → 래치 유지
    hist = [RegimeHistoryPoint(date=f"2026-08-{d:02d}", total_score=-8) for d in range(10, 21)]
    r3 = regime_score(macro(as_of="2026-09-01"), history=hist, crisis_state=prior)
    assert r3.score_smooth < -5
    assert r3.crisis_active is True


# ─────────────── EMA / 결정성 ───────────────


def test_ema_known_sequence() -> None:
    # span=5 → alpha = 1/3. adjust=False
    # [3, 3, 3] → 3.0
    assert _ema([3, 3, 3], 5) == pytest.approx(3.0)
    # [0, 6] → 1/3*6 + 2/3*0 = 2.0
    assert _ema([0, 6], 5) == pytest.approx(2.0)


def test_score_smooth_uses_history() -> None:
    hist = [RegimeHistoryPoint(date="2026-08-31", total_score=6)]
    r = regime_score(macro(), history=hist)  # 오늘 total 0
    # [6, 0] → 1/3*0 + 2/3*6 = 4.0
    assert r.score_smooth == pytest.approx(4.0)


def test_low_confidence_score_smooth_uses_raw_sum_not_extrapolation() -> None:
    # vix+spx 만 (+2,+2) → total_score 12 (외삽) 이지만 EMA 입력은 원합 4
    r = regime_score(
        macro(
            vix=12.0,
            vix3m=20.0,
            spx_last=110.0,
            spx_sma_200=100.0,
            spx_50_slope_20d=0.02,
            pct_above_200dma=None,
            yc_10y_3m_bp=None,
            hy_oas_bp=None,
            wei=None,
            regional_fed_mfg_avg=None,
            claims_4w_trend_pct=None,
        )
    )
    assert r.total_score == 12
    assert r.score_smooth == pytest.approx(4.0)  # 외삽이면 12 였을 것


def test_same_day_history_point_not_double_counted() -> None:
    # 히스토리에 이미 오늘(as_of) 포인트가 있어도 EMA 에 한 번만
    hist = [
        RegimeHistoryPoint(date="2026-08-31", total_score=6),
        RegimeHistoryPoint(date="2026-09-01", total_score=0),  # == macro as_of
    ]
    r = regime_score(macro(), history=hist)  # 오늘 total 0
    assert r.score_smooth == pytest.approx(4.0)  # [6, 0] — 9/01 히스토리 무시


def test_crisis_exit_counts_holidays_via_history() -> None:
    # busday 로는 5거래일이지만 실제 거래일 기록은 4일 → 래치 유지 (공휴일 1일 반영)
    prior = CrisisState(active=True, triggered_date="2026-08-24")  # 월
    hist = [
        RegimeHistoryPoint(date=d, total_score=0)
        for d in ("2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-31")
    ]  # 8/28(금) 공휴일 가정 → 트리거 후 4거래일
    r = regime_score(macro(as_of="2026-08-31"), history=hist, crisis_state=prior)
    assert r.crisis_active is True  # 4 < exit_trading_days(5)


def test_determinism() -> None:
    m = macro(vix=13.0, vix3m=20.0, hy_oas_bp=310.0, hy_oas_4w_change_bp=-5.0)
    outs = [regime_score(m).model_dump() for _ in range(3)]
    assert outs[0] == outs[1] == outs[2]
