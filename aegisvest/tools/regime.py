"""RegimeScoreCalculator — 매크로 6축 → 레짐 점수·라벨. 순수 계산, LLM 관여 0.

근거: report/phase-2-macro-and-rebalancing.md §1. 임계값은 config/regime_rules.yaml.
데이터 없는 축은 제외하고 나머지로 정규화한다: total = round(sum * 6 / n_present).
"""

from __future__ import annotations

import math

import numpy as np

from aegisvest.rules import (
    CreditAxis,
    EconomyAxis,
    FiveLevel,
    RegimeRules,
    VixAxis,
    YieldAxis,
    regime_rules,
)
from aegisvest.schemas import CrisisState, MacroData, Regime, RegimeHistoryPoint, RegimeResult

_AXES = ("vix", "spx_trend", "breadth", "yield_policy", "credit", "economy")


def _round_half_up(x: float) -> int:
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)


def _trading_days_between(start: str, end: str) -> int:
    return int(np.busday_count(np.datetime64(start), np.datetime64(end)))


def _elapsed_trading_days(
    history: list[RegimeHistoryPoint], triggered_date: str | None, as_of: str
) -> int:
    """트리거 후 경과 거래일. regime_history(실제 거래일 기록)가 조밀하면 그걸로 세고
    (공휴일 정확 반영), 부족하면 busday_count 폴백 (감시견 미가동 기간·truncate 대비).
    """
    if triggered_date is None:
        return 0
    busday = _trading_days_between(triggered_date, as_of)
    dates = sorted(h.date for h in history)
    if dates and dates[0] <= triggered_date:
        hist_count = sum(1 for d in dates if triggered_date < d <= as_of)
        if hist_count >= busday - 3:  # 히스토리 조밀 → 정확값 사용
            return hist_count
    return busday


def _ema(scores: list[int], span: int) -> float:
    alpha = 2.0 / (span + 1)
    ema = float(scores[0])
    for x in scores[1:]:
        ema = alpha * x + (1.0 - alpha) * ema
    return ema


# ─────────────────────── 축별 채점 ───────────────────────


def _axis_vix(m: MacroData, r: VixAxis) -> tuple[int | None, str]:
    if m.vix is None:
        return None, "VIX 데이터 없음"
    v3 = m.vix3m
    contango = v3 is not None and m.vix < v3
    backwardation = v3 is not None and m.vix >= v3  # 명세: vix >= vix3m (config/regime_rules.yaml)
    if m.vix < r.calm_max and contango:
        return 2, f"VIX {m.vix:.1f} < {r.calm_max} & 콘탱고"
    if m.vix > r.stress_max or backwardation:
        why = f"> {r.stress_max}" if m.vix > r.stress_max else "백워데이션"
        return -2, f"VIX {m.vix:.1f} {why}"
    tail = "" if v3 is not None else " (VIX3M 없음)"
    return 0, f"VIX {m.vix:.1f} 중립{tail}"


def _axis_spx_trend(m: MacroData) -> tuple[int | None, str]:
    if m.spx_last is None or m.spx_sma_200 is None:
        return None, "S&P 데이터 없음"
    above = m.spx_last > m.spx_sma_200
    slope = m.spx_50_slope_20d
    rising = slope is not None and slope > 0
    falling = slope is not None and slope < 0
    if above and rising:
        return 2, f"종가 > 200SMA & 50SMA 상승 ({slope:+.2%})"
    if (not above) and falling:
        return -2, f"종가 < 200SMA & 50SMA 하락 ({slope:+.2%})"
    return 0, f"종가/200SMA {m.spx_last / m.spx_sma_200 - 1:+.2%}, 추세 혼조"


def _axis_breadth(m: MacroData, strong_min: float, weak_max: float) -> tuple[int | None, str]:
    b = m.pct_above_200dma
    if b is None:
        return None, "시장 폭 데이터 없음 (3a-5)"
    if b > strong_min:
        return 2, f"{b:.0f}% > {strong_min:.0f}%"
    if b < weak_max:
        return -2, f"{b:.0f}% < {weak_max:.0f}%"
    return 0, f"{b:.0f}% 중립"


def _axis_yield(m: MacroData, r: YieldAxis) -> tuple[int | None, str]:
    yc = m.yc_10y_3m_bp
    if yc is None:
        return None, "일드커브 데이터 없음"
    chg = m.yc_10y_3m_4w_change_bp
    prev = m.yc_10y_3m_prev_bp
    if yc > 0 and m.fed_funds_trend in ("hold", "cutting"):
        return 2, f"10Y-3M {yc:+.0f}bp 정상 & Fed {m.fed_funds_trend}"
    deep = yc < r.deep_inversion_bp
    deepening = yc < 0 and chg is not None and chg <= r.deepening_4w_bp
    resteepen = prev is not None and prev < 0 and chg is not None and chg >= r.resteepen_4w_bp
    if deep or deepening or resteepen:
        cause = "역전 심화" if (deep or deepening) else "역전 후 급격 재정상화"
        return -2, f"10Y-3M {yc:+.0f}bp: {cause}"
    return 0, f"10Y-3M {yc:+.0f}bp 중립"


def _axis_credit(m: MacroData, r: CreditAxis) -> tuple[int | None, str]:
    oas = m.hy_oas_bp
    if oas is None:
        return None, "신용 스프레드 데이터 없음"
    chg = m.hy_oas_4w_change_bp
    if oas < r.calm_max_bp and chg is not None and chg < 0:
        return 2, f"HY OAS {oas:.0f}bp < {r.calm_max_bp:.0f} & 축소 ({chg:+.0f}bp/4주)"
    if oas > r.stress_max_bp or (chg is not None and chg >= r.spike_4w_bp):
        why = f"> {r.stress_max_bp:.0f}bp" if oas > r.stress_max_bp else f"4주 {chg:+.0f}bp 급등"
        return -2, f"HY OAS {oas:.0f}bp: {why}"
    return 0, f"HY OAS {oas:.0f}bp 중립"


def _sub_score(value: float | None, lv: FiveLevel) -> int | None:
    """5단계 채점. p2>p1>z0>n1 이면 상향(값 클수록 +), 역이면 하향(값 작을수록 +)."""
    if value is None:
        return None
    thresholds = [(lv.p2, 2), (lv.p1, 1), (lv.z0, 0), (lv.n1, -1)]
    ascending = lv.p2 > lv.n1
    for thr, score in thresholds:
        if (value >= thr) if ascending else (value <= thr):
            return score
    return -2


def _axis_economy(m: MacroData, r: EconomyAxis) -> tuple[int | None, dict[str, int | None], str]:
    subs = {
        "wei": _sub_score(m.wei, r.wei),
        "regional": _sub_score(m.regional_fed_mfg_avg, r.regional),
        "claims": _sub_score(m.claims_4w_trend_pct, r.claims_3m),
    }
    present = [s for s in subs.values() if s is not None]
    if not present:
        return None, subs, "경기 하위 신호 데이터 없음"
    score = _round_half_up(sum(present) / len(present))
    return score, subs, f"하위신호 {subs} → 평균 {sum(present) / len(present):.2f} → {score}"


# ─────────────────────── CRISIS 래치 ───────────────────────


def _crisis(
    m: MacroData, score_smooth: float, prior: CrisisState, r: RegimeRules, elapsed: int
) -> tuple[bool, str | None, CrisisState]:
    c = r.crisis
    reasons: list[str] = []
    if m.vix is not None and m.vix > c.vix_max:
        reasons.append(f"VIX {m.vix:.1f} > {c.vix_max}")
    if m.vix_1d_change_pct is not None and m.vix_1d_change_pct > c.vix_1d_spike_pct:
        reasons.append(f"VIX 1일 {m.vix_1d_change_pct:+.0%} 급등")
    if m.hy_oas_bp is not None and m.hy_oas_bp > c.hy_oas_max_bp:
        reasons.append(f"HY OAS {m.hy_oas_bp:.0f}bp > {c.hy_oas_max_bp:.0f}")
    if (
        m.spx_last is not None
        and m.spx_sma_200 is not None
        and m.spx_last < m.spx_sma_200 * (1.0 - c.spx_below_200sma_frac)
    ):
        reasons.append(f"S&P500 200SMA 대비 -{c.spx_below_200sma_frac:.0%} 초과 이탈")

    if reasons:
        return True, "; ".join(reasons), CrisisState(active=True, triggered_date=m.as_of)
    if prior.active:
        if score_smooth >= c.exit_score_smooth_min and elapsed >= c.exit_trading_days:
            return False, None, CrisisState(active=False, triggered_date=None)
        return (
            True,
            f"CRISIS 래치 유지 (경과 {elapsed}거래일, 스무딩 {score_smooth:.1f})",
            prior,
        )
    return False, None, CrisisState(active=False, triggered_date=None)


def _label(total: int, r: RegimeRules) -> Regime:
    if total >= r.label.bull_min:
        return Regime.BULL
    if total <= r.label.bear_max:
        return Regime.BEAR
    return Regime.NEUTRAL


# ─────────────────────── 진입점 ───────────────────────


def regime_score(
    macro: MacroData,
    history: list[RegimeHistoryPoint] | None = None,
    crisis_state: CrisisState | None = None,
) -> RegimeResult:
    """오늘의 MacroData + 누적 히스토리 + 직전 CRISIS 상태 → RegimeResult."""
    r = regime_rules()
    hist = history or []
    # 오늘(as_of) 이후 날짜 포인트는 EMA 에서 제외 — 같은 날 재실행 시 오늘 이중계산 방지
    prior_scores = [h.total_score for h in hist if h.date < macro.as_of]
    prior_crisis = crisis_state or CrisisState()
    ax = r.axes

    vix_s, vix_r = _axis_vix(macro, ax.vix)
    spx_s, spx_r = _axis_spx_trend(macro)
    br_s, br_r = _axis_breadth(macro, ax.breadth.strong_min, ax.breadth.weak_max)
    yc_s, yc_r = _axis_yield(macro, ax.yield_policy)
    cr_s, cr_r = _axis_credit(macro, ax.credit)
    ec_s, ec_subs, ec_r = _axis_economy(macro, ax.economy)

    axis_scores: dict[str, int | None] = {
        "vix": vix_s,
        "spx_trend": spx_s,
        "breadth": br_s,
        "yield_policy": yc_s,
        "credit": cr_s,
        "economy": ec_s,
    }
    present = [v for v in axis_scores.values() if v is not None]
    n_present = len(present)
    normalized = 0 if n_present == 0 else _round_half_up(sum(present) * len(_AXES) / n_present)
    total = max(-12, min(12, normalized))
    low_confidence = n_present < r.min_axes_for_label

    # low_confidence 일엔 EMA·배분에 외삽(±12)이 아닌 관측 축 원합만 반영 — 얇은 데이터로
    # 95% 주식·20% 고위험 스냅 방지. 리포트용 total_score 는 명세대로 외삽값 유지.
    ema_input = sum(present) if low_confidence else total
    score_smooth = _ema([*prior_scores, ema_input], r.ema_span)
    elapsed_td = _elapsed_trading_days(hist, prior_crisis.triggered_date, macro.as_of)
    crisis_active, crisis_reason, new_state = _crisis(
        macro, score_smooth, prior_crisis, r, elapsed_td
    )
    if crisis_active:
        regime = Regime.CRISIS
    elif low_confidence:
        regime = Regime.NEUTRAL
    else:
        regime = _label(total, r)

    rationale = {
        "vix": vix_r,
        "spx_trend": spx_r,
        "breadth": br_r,
        "yield_policy": yc_r,
        "credit": cr_r,
        "economy": ec_r,
        "total": (
            f"present {n_present}축 합 {sum(present)} → 정규화 {total}"
            + (
                f" (low_confidence: {n_present} < {r.min_axes_for_label}, 라벨 NEUTRAL 강등)"
                if low_confidence
                else ""
            )
        ),
        "crisis": crisis_reason or "정상",
    }

    return RegimeResult(
        axis_scores=axis_scores,
        economy_subscores=ec_subs,
        n_axes_present=n_present,
        low_confidence=low_confidence,
        total_score=total,
        score_smooth=score_smooth,
        regime=regime,
        crisis_active=crisis_active,
        crisis_reason=crisis_reason,
        crisis_state=new_state,
        rationale=rationale,
    )
