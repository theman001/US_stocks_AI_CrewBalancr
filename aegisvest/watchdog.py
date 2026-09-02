"""일일 감시견 — 위기 감지 + 매크로 점수 누적 + 일일 NAV 평가. LLM 미사용.

근거: report/phase-2 §3.2, phase-3 §7.3. 매일:
  1. macro_data() + regime_score() 계산
  2. crisis_state / (low_confidence 아니면) regime_history persist
  3. 모의 포트폴리오·벤치마크 일일 mark-to-market (거래일 종가 기준)
  4. CRISIS 신규 발동 이면 crisis_flag.json 기록 + 알림 + 주간 크루 즉시 트리거
"""

from __future__ import annotations

import logging

from aegisvest.broker import benchmarks as bm
from aegisvest.broker import paper
from aegisvest.config import ensure_runtime_dirs, get_settings
from aegisvest.notify import post
from aegisvest.schemas import (
    BenchmarkState,
    CrisisFlag,
    CrisisState,
    PaperPortfolio,
    RegimeHistoryPoint,
    RegimeResult,
    ShadowState,
    ToolError,
)
from aegisvest.state import load_list, load_model, save_list, save_model
from aegisvest.tools._prices import latest_close_date
from aegisvest.tools.fx import usd_krw
from aegisvest.tools.macro_data import macro_data
from aegisvest.tools.market_data import market_data
from aegisvest.tools.regime import regime_score

_HISTORY = "regime_history.json"
_CRISIS_STATE = "crisis_state.json"
_CRISIS_FLAG = "crisis_flag.json"
# EMA span 5 에는 40이면 충분하나, diary/evaluate._score_regime_call 이 regime_call 12주
# 채점창(≈60거래일, diary/schema._HORIZON_SCHEDULE)을 이 파일에서 재구성한다 → 12주 + 여유.
_MAX_HISTORY = 70

_log = logging.getLogger("aegisvest.watchdog")


def _update_history(history: list[RegimeHistoryPoint], result: RegimeResult, as_of: str) -> None:
    if result.low_confidence:
        _log.info("low_confidence (%d축) — history 미기록", result.n_axes_present)
        return
    if history and history[-1].date == as_of:
        history[-1] = RegimeHistoryPoint(date=as_of, total_score=result.total_score)
    else:
        history.append(RegimeHistoryPoint(date=as_of, total_score=result.total_score))
    save_list(_HISTORY, list(history[-_MAX_HISTORY:]))


def _handle_crisis(result: RegimeResult, as_of: str) -> None:
    prior = load_model(_CRISIS_FLAG, CrisisFlag)
    if result.crisis_active:
        save_model(
            _CRISIS_FLAG, CrisisFlag(active=True, reason=result.crisis_reason, detected_at=as_of)
        )
        if not (prior and prior.active):  # 신규 발동 → 알림 + 주간 크루 즉시
            post(
                f"🆘 **CRISIS 발동** ({as_of})\n{result.crisis_reason}\n"
                f"regime={result.regime.value} · score_smooth={result.score_smooth:.1f}\n"
                f"주간 크루 즉시 실행",
                channel="aegis-alerts",
            )
            _trigger_weekly_crew()
    elif prior and prior.active:
        save_model(_CRISIS_FLAG, CrisisFlag(active=False, cleared_at=as_of))
        post(f"✅ CRISIS 해제 ({as_of}) · regime={result.regime.value}", channel="aegis-alerts")


def _trigger_weekly_crew() -> None:
    try:
        from aegisvest.main import run as run_weekly  # noqa: PLC0415  # 지연 import (순환·무게)

        run_weekly(trigger="crisis")
    except Exception:
        _log.exception("위기 트리거 주간 크루 실행 실패 — 다음 정기 실행에서 처리")


def _mark_nav(fallback_date: str) -> None:
    """섀도 양쪽 포트·벤치마크 일일 mark-to-market. 모의투자 미시작이면 아무것도 안 함."""
    shadow = load_model("shadow.json", ShadowState)
    if shadow is None:
        return
    pfs = [shadow.deterministic, shadow.organization]
    if all(not p.positions and p.cash_usd <= 0 for p in pfs):
        return
    as_of = _trading_day(fallback_date)
    marked = max((p.history[-1].date for p in pfs if p.history), default="")
    if marked >= as_of:
        return  # 이미 이 거래일 마감 반영 (주말·중복 실행) — 마킹된 포트 기준
    fx_rate = _fx_or_carry(pfs)
    held = {t for p in pfs for t, pos in p.positions.items() if pos.shares > 0}
    prices: dict[str, float] = {}
    for t in sorted(held | set(bm.BENCH_TICKERS)):
        md = market_data(t)
        if not isinstance(md, ToolError) and md.last_price > 0:
            prices[t] = md.last_price
    for p in pfs:
        paper.mark_to_market(p, prices, as_of, fx_rate)
    save_model("shadow.json", shadow)
    bench = load_model("benchmarks.json", BenchmarkState)
    if bench is not None:
        bm.mark_to_market(bench, prices, as_of, fx_rate)
        save_model("benchmarks.json", bench)


def _trading_day(default: str) -> str:
    """가장 최근 미국장 거래일 (NAV 타임라인 인덱스). 실패 시 default(macro.as_of)."""
    return latest_close_date(float(get_settings().cache_ttl_hours)) or default


def _fx_or_carry(pfs: list[PaperPortfolio]) -> float:
    """USD/KRW — 조회 실패 시 마지막 NavPoint 의 암시 환율 이월 (1400 고정 점프 방지)."""
    fx = usd_krw()
    if not isinstance(fx, ToolError):
        return fx
    for p in pfs:
        if p.history and p.history[-1].nav_usd > 0:
            return p.history[-1].nav_krw / p.history[-1].nav_usd
    return 1400.0


def run() -> RegimeResult:
    ensure_runtime_dirs()
    macro = macro_data()
    history = load_list(_HISTORY, RegimeHistoryPoint)
    crisis_state = load_model(_CRISIS_STATE, CrisisState) or CrisisState()

    result = regime_score(macro, history, crisis_state)

    if get_settings().dry_run:  # 배포 스모크 — 계산·로그만, 상태·알림·트리거 없음 (main 과 동일)
        _log.warning("DRY_RUN — crisis_state/history/nav 미저장, 위기 알림·주간 트리거 스킵")
    else:
        save_model(_CRISIS_STATE, result.crisis_state)
        _update_history(history, result, macro.as_of)
        _mark_nav(macro.as_of)
        _handle_crisis(result, macro.as_of)  # 마지막 — 위기 시 주간 크루 트리거

    _log.info(
        "%s regime=%s total=%d smooth=%.2f n_axes=%d%s stale=%s",
        macro.as_of,
        result.regime.value,
        result.total_score,
        result.score_smooth,
        result.n_axes_present,
        " low_conf" if result.low_confidence else "",
        macro.stale_fields or "-",
    )
    return result


def main() -> None:
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    run()


if __name__ == "__main__":
    main()
