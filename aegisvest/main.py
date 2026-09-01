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
    PaperPortfolio,
    PipelineResult,
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


def _bump_cooldown(pf: PaperPortfolio, pr: PipelineResult, held: bool) -> None:
    """카테고리별 '마지막 매도 후 경과 거래일'. 주간 실행 ≈ 5거래일. 매도한 카테고리는 0 리셋."""
    sold = set() if held else {o.category for o in pr.rebalance_plan.sell_orders}
    pf.cooldown_days = {
        c: 0 if c in sold else min(pf.cooldown_days.get(c, 999) + 5, 999)
        for c in ("low", "mid", "high")
    }


def _contribution_due(pf: PaperPortfolio, today: dt.date) -> bool:
    if get_settings().monthly_contribution_krw <= 0:
        return False
    if not pf.contributions:
        return True
    last = dt.date.fromisoformat(pf.contributions[-1].date)
    return (last.year, last.month) != (today.year, today.month)


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


def _persist_regime(history: list[RegimeHistoryPoint], regime: RegimeResult, as_of: str) -> None:
    """감시견과 동일 규칙 — crisis_state 항상, history 는 low_confidence 아닌 날만."""
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

    pf = load_model("paper_portfolio.json", PaperPortfolio) or PaperPortfolio()
    bench = load_model("benchmarks.json", BenchmarkState) or BenchmarkState()
    shadow = load_model("shadow.json", ShadowState) or ShadowState()
    history = load_list("regime_history.json", RegimeHistoryPoint)
    crisis_state = load_model("crisis_state.json", CrisisState) or CrisisState()

    fx = _fx_rate()
    contribution_usd = 0.0
    if _contribution_due(pf, today):
        c = paper.add_contribution(pf, s.monthly_contribution_krw, fx, run_id)
        contribution_usd = c.usd
        bm.contribute(bench, contribution_usd, _bench_prices())
        _log.info("적금 납입 ₩%.0f → $%.2f (환율 %.1f)", c.krw, c.usd, c.fx_rate)

    pr = run_pipeline(portfolio=pf, regime_history=history, crisis_state=crisis_state, mode=s.mode)
    _persist_regime(history, pr.regime, pr.as_of)

    crew: CrewOutcome | None = None
    if s.deepseek_api_key:
        try:
            # 지연 import — 키 없으면 crewai(무거움) 를 안 불러온다
            from aegisvest.agents.crew import run_crew  # noqa: PLC0415

            crew = run_crew(pr, run_id=run_id)
        except Exception:  # 크루 실패가 결정론 파이프라인·모의투자를 막지 않는다
            _log.exception("크루 실행 실패 — 결정론 결과로 진행")
    else:
        _log.info("DEEPSEEK_API_KEY 없음 — 크루 스킵, 결정론 주문만")

    held = crew is not None and crew.cio.verdict == "HOLD"
    execution: ExecutionResult | None = None
    if held:
        _log.warning("CIO HOLD: %s — 매매 스킵", crew.cio.hold_reason if crew else "")
    elif pr.orders:
        execution = paper.execute(pf, pr.orders, pr.prices)
        _log.info("체결 %d건 (스킵 %d)", len(execution.fills), len(execution.skipped))

    _bump_cooldown(pf, pr, held)
    all_prices = {**pr.prices, **_bench_prices()}
    mark_date = latest_close_date(float(s.cache_ttl_hours)) or pr.as_of  # 감시견과 동일 인덱스
    nav = paper.mark_to_market(pf, all_prices, mark_date, fx)
    bm.mark_to_market(bench, all_prices, mark_date, fx)
    shadow.deterministic = pf  # 3a: 조직 포트 비어있음 → deterministic = 실제 모의포트

    for name, obj in (
        ("paper_portfolio.json", pf),
        ("benchmarks.json", bench),
        ("shadow.json", shadow),
    ):
        save_model(name, obj)

    report_md = weekly_report_md(
        pr,
        crew,
        execution,
        held=held,
        contribution_usd=contribution_usd,
        nav_usd=nav.nav_usd,
        nav_krw=nav.nav_krw,
    )
    report_path = write_run(run_id, pr, crew, execution, report_md)
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
        held=held,
        crew_ran=crew is not None,
        contribution_usd=round(contribution_usd, 2),
        nav_usd=nav.nav_usd,
        nav_krw=nav.nav_krw,
        n_orders=len(pr.orders),
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
