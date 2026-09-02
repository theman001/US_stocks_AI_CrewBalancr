"""주간 크루 엔트리 — `python -m aegisvest.main`. 근거: report/phase-2 §3.3·§7, phase-3 §4·§9.

일요일 22:00 KST (또는 감시견 위기 트리거). 흐름:
  적금 납입(월 1회) → run_pipeline(결정론) → run_crew(LLM, 키 있을 때) →
  CIO APPROVED 면 주문 체결 · HOLD 면 스킵 → mark-to-market → 리포트 + 알림.
결정론 주문은 크루가 못 바꾼다 (CIO 는 승인/보류만).
"""

from __future__ import annotations

import datetime as dt
import logging

from aegisvest.broker import benchmarks as bm
from aegisvest.broker import paper
from aegisvest.config import ensure_runtime_dirs, get_settings
from aegisvest.notify import post
from aegisvest.pipeline import run_pipeline
from aegisvest.report import mattermost_summary, weekly_report_md, write_run
from aegisvest.schemas import (
    BenchmarkState,
    CrewOutcome,
    CrisisState,
    ExecutionResult,
    Order,
    PaperPortfolio,
    RegimeHistoryPoint,
    RegimeResult,
    ShadowState,
    ToolError,
    WeeklyRunResult,
)
from aegisvest.state import load_list, load_model, save_list, save_model
from aegisvest.tools._prices import latest_close_date
from aegisvest.tools.fx import usd_krw
from aegisvest.tools.market_data import market_data

_log = logging.getLogger("aegisvest.main")
_MAX_HISTORY = 40


def _bump_cooldown(pf: PaperPortfolio, executed: list[Order], held: bool) -> None:
    """카테고리별 '마지막 매도 후 경과 거래일'. 주간 실행 ≈ 5거래일. 매도한 카테고리는 0 리셋."""
    sold = (
        set()
        if held
        else {(o.category or "").lower() for o in executed if o.side == "sell" and o.category}
    )
    pf.cooldown_days = {
        c: 0 if c in sold else min(pf.cooldown_days.get(c, 999) + 5, 999)
        for c in ("low", "mid", "high")
    }


def _contribution_due(pf: PaperPortfolio, ref: dt.date) -> bool:
    """`ref` = 이번 회차 기여를 스탬프할 날짜 (거래일 기준). 달이 바뀌면 납입."""
    if get_settings().monthly_contribution_krw <= 0:
        return False
    if not pf.contributions:
        return True
    last = dt.date.fromisoformat(pf.contributions[-1].date)
    return (last.year, last.month) != (ref.year, ref.month)


def _maybe_contribute(
    shadow: ShadowState,
    bench: BenchmarkState,
    bench_prices: dict[str, float],
    stamp: str,
    fx: float,
) -> float:
    """월 납입이 도래했으면 org·det 포트 + 벤치에 동일 현금흐름 반영. 반환 = USD 납입액."""
    if not _contribution_due(shadow.organization, dt.date.fromisoformat(stamp)):
        return 0.0
    krw = get_settings().monthly_contribution_krw
    c = paper.add_contribution(shadow.organization, krw, fx, stamp)
    paper.add_contribution(shadow.deterministic, krw, fx, stamp)
    bm.contribute(bench, c.usd, bench_prices)
    _log.info("적금 납입 ₩%.0f → $%.2f (환율 %.1f)", c.krw, c.usd, c.fx_rate)
    return c.usd


def _fx_rate() -> float:
    r = usd_krw()
    if isinstance(r, ToolError):
        _log.warning("환율 조회 실패 (%s) — 폴백 1400", r.error)
        return 1400.0
    return r


def _bench_prices() -> dict[str, float]:
    out: dict[str, float] = {}
    for t in bm.BENCH_TICKERS:
        md = market_data(t)
        if not isinstance(md, ToolError) and md.last_price > 0:
            out[t] = md.last_price
    return out


def _load_shadow() -> ShadowState:
    """섀도 A/B state. 구버전 paper_portfolio.json 있으면 organization 으로 1회 이관."""
    shadow = load_model("shadow.json", ShadowState)
    if shadow is not None:
        return shadow
    old = load_model("paper_portfolio.json", PaperPortfolio)
    if old is not None:
        _log.info("paper_portfolio.json → shadow.json 이관 (양쪽 동일 시작)")
        return ShadowState(deterministic=old.model_copy(deep=True), organization=old)
    return ShadowState()


def _execute_and_mark(
    shadow: ShadowState,
    bench: BenchmarkState,
    org_orders: list[Order],
    det_orders: list[Order],
    prices: dict[str, float],
    *,
    held: bool,
    fx: float,
    mark_date: str,
    execute: bool = True,
) -> ExecutionResult | None:
    """조직·결정론 포트 각각 체결 후 mark-to-market (+벤치). 조직 execution 만 반환.

    `execute=False` (DRY_RUN): 체결은 건너뛰고 마킹만 (리포트용 평가). 호출자가 저장 안 함.
    """
    org_pf, det_pf = shadow.organization, shadow.deterministic
    org_exec: ExecutionResult | None = None
    if execute and not held and org_orders:
        org_exec = paper.execute(org_pf, org_orders, prices)
    if execute and det_orders:  # 결정론 병행 시뮬은 CIO HOLD 와 무관하게 진행
        paper.execute(det_pf, det_orders, prices)
    paper.mark_to_market(org_pf, prices, mark_date, fx)
    paper.mark_to_market(det_pf, prices, mark_date, fx)
    bm.mark_to_market(bench, prices, mark_date, fx)
    return org_exec


def _persist_regime(
    history: list[RegimeHistoryPoint], regime: RegimeResult, as_of: str, *, persist: bool = True
) -> None:
    """감시견과 동일 규칙 — crisis_state 항상, history 는 low_confidence 아닌 날만."""
    if not persist:
        return
    save_model("crisis_state.json", regime.crisis_state)
    if regime.low_confidence:
        return
    point = RegimeHistoryPoint(date=as_of, total_score=regime.total_score)
    if history and history[-1].date == as_of:
        history[-1] = point
    else:
        history.append(point)
    save_list("regime_history.json", list(history[-_MAX_HISTORY:]))


def run(*, trigger: str = "scheduled") -> WeeklyRunResult:
    ensure_runtime_dirs()
    s = get_settings()
    today = dt.date.today()
    run_id = today.isoformat()

    bench = load_model("benchmarks.json", BenchmarkState) or BenchmarkState()
    shadow = _load_shadow()
    det_pf, org_pf = shadow.deterministic, shadow.organization  # org = "실제" 모의포트
    history = load_list("regime_history.json", RegimeHistoryPoint)
    crisis_state = load_model("crisis_state.json", CrisisState) or CrisisState()

    # NAV·기여·벤치 전부 이 날짜(직전 미국장 마감일)로 스탬프 — TWR 이 기여를 수익으로
    # 오인하지 않으려면 Contribution.date == NavPoint.date 여야 한다 (4-post-review).
    mkt_date = latest_close_date(float(s.cache_ttl_hours))
    bench_prices = _bench_prices()
    fx = _fx_rate()
    contribution_usd = _maybe_contribute(shadow, bench, bench_prices, mkt_date or run_id, fx)

    pr = run_pipeline(
        portfolio=org_pf, regime_history=history, crisis_state=crisis_state, mode=s.mode
    )

    crew: CrewOutcome | None = None
    if s.deepseek_api_key:
        try:
            # 지연 import — 키 없으면 crewai(무거움) 를 안 불러온다
            from aegisvest.agents.organization import run_organization  # noqa: PLC0415

            crew = run_organization(pr, portfolio=org_pf, prices=pr.prices, run_id=run_id)
        except Exception:  # 크루 실패가 결정론 파이프라인·모의투자를 막지 않는다
            _log.exception("조직 크루 실행 실패 — 결정론 결과로 진행")
    else:
        _log.info("DEEPSEEK_API_KEY 없음 — 크루 스킵, 결정론 = 조직")

    held = crew is not None and (crew.rebalance_held or crew.cio.verdict == "HOLD")
    use_org = crew is not None and not held and crew.cio.verdict == "APPROVED"
    org_orders = crew.org_orders if (use_org and crew) else pr.orders

    # ── 결정론 병행 시뮬 (섀도 A/B). 크루 없으면 org 와 동일 경로. ──
    # 주의: regime_history 는 아직 오늘 포인트 미포함이어야 org·det 가 동일 입력을 본다.
    if crew is not None:
        det_pr = run_pipeline(
            portfolio=det_pf, regime_history=history, crisis_state=crisis_state, mode=s.mode
        )
        det_orders = det_pr.orders
    else:
        det_orders = pr.orders

    _persist_regime(history, pr.regime, pr.as_of, persist=not s.dry_run)  # org·det 실행 후 append

    mark_date = mkt_date or pr.as_of
    all_prices = {**pr.prices, **bench_prices}
    execution = _execute_and_mark(
        shadow,
        bench,
        org_orders,
        det_orders,
        all_prices,
        held=held,
        fx=fx,
        mark_date=mark_date,
        execute=not s.dry_run,
    )
    if execution is not None:
        _log.info("체결(조직) %d건 · %s", len(execution.fills), "조직틸트" if use_org else "결정론")
    _bump_cooldown(org_pf, org_orders, held)
    _bump_cooldown(det_pf, det_orders, held=False)
    nav = org_pf.history[-1]
    det_nav = det_pf.history[-1].nav_usd if det_pf.history else None

    if s.dry_run:
        _log.warning(
            "DRY_RUN — 상태 미저장 (shadow/benchmarks/regime_history), 주문 미체결, 알림 스킵"
        )
    else:
        save_model("benchmarks.json", bench)
        save_model("shadow.json", shadow)

    report_md = weekly_report_md(
        pr,
        crew,
        execution,
        held=held,
        contribution_usd=contribution_usd,
        nav_usd=nav.nav_usd,
        nav_krw=nav.nav_krw,
        det_nav_usd=det_nav,
    )
    report_path = write_run(run_id, pr, crew, execution, report_md)
    if not s.dry_run:
        post(
            mattermost_summary(
                pr,
                crew,
                held=held,
                nav_usd=nav.nav_usd,
                n_fills=len(execution.fills) if execution else 0,
            ),
            channel="aegis-alerts",
        )

    return WeeklyRunResult(
        run_id=run_id,
        trigger=trigger,
        dry_run=s.dry_run,
        held=held,
        crew_ran=crew is not None,
        contribution_usd=round(contribution_usd, 2),
        nav_usd=nav.nav_usd,
        nav_krw=nav.nav_krw,
        n_orders=len(org_orders),  # 실제 체결 대상 (조직 틸트 시 crew.org_orders)
        n_fills=len(execution.fills) if execution else 0,
        regime=pr.regime.regime.value,
        crisis_active=pr.regime.crisis_active,
        constraints_verdict=pr.constraints.verdict,
        cio_verdict=crew.cio.verdict if crew else None,
        report_path=str(report_path),
        diary_ids=crew.diary_ids if crew else [],
    )


def main() -> None:
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    result = run()
    _log.info(
        "완료 %s regime=%s nav=$%.2f fills=%d held=%s",
        result.run_id,
        result.regime,
        result.nav_usd,
        result.n_fills,
        result.held,
    )


if __name__ == "__main__":
    main()
