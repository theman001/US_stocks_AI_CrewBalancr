"""주간 조직 실행 — 애널리스트 크루 → [⑥ PM ↔ ⑦ Risk (반려 1회)] → ⑧ CIO.

report/phase-3 §3(⑥⑦⑧)·§4. 반려 루프는 crewai.Flow @router (사용자 결정 2026-09-01).
PM 은 draft 를 제안하고 `pm.clamp_pm_draft` 가 하드 한계로 강제. 섀도 A/B 는 3b-3.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.flow.flow import Flow, listen, router, start
from pydantic import BaseModel

from aegisvest.agents import quiet_crew_console
from aegisvest.agents.crew import (
    _RECALL_TASKS,
    _TASKS,
    AnalystBundle,
    _agents,
    _cfg,
    _diary_snapshot,
    _num_payload,
    _out,
    build_inputs,
    make_task,
    run_analysts,
)
from aegisvest.agents.pm import clamp_pm_draft
from aegisvest.diary import logger as diary
from aegisvest.diary.rag import DiaryRAG, build_query, format_recall
from aegisvest.diary.schema import derive_tags, magnitude_of
from aegisvest.pipeline import build_orders, category_usd
from aegisvest.schemas import (
    CIODecision,
    ConstraintResult,
    CrewOutcome,
    DraftPortfolio,
    Order,
    PaperPortfolio,
    PipelineResult,
    PMDraft,
    Position,
    RiskReview,
    SizingResult,
    ToolError,
)
from aegisvest.tools.constraints import check_constraints
from aegisvest.tools.rebalance import cash_flow_rebalance

_log = logging.getLogger("aegisvest.org")
_MAX_ROUNDS = 2
_CATS = ("low", "mid", "high")


@dataclass
class _Ctx:
    """Flow 스텝이 공유하는 실행 컨텍스트 (crewai Flow state 밖)."""

    agents: dict[str, Agent]
    tdefs: dict[str, Any]
    allowed: dict[str, Any]
    pr: PipelineResult
    run_id: str
    diary_ids: list[str]
    inputs: dict[str, str]
    recall: str = ""
    dry_run: bool = False

    def run(self, key: str, *, extra_desc: str = "") -> Any:
        task: Task = make_task(
            key,
            [],
            agents=self.agents,
            tdefs=self.tdefs,
            allowed=self.allowed,
            pr=self.pr,
            run_id=self.run_id,
            diary_ids=self.diary_ids,
            extra_desc=extra_desc,
            recall=self.recall if key in _RECALL_TASKS else "",
            dry_run=self.dry_run,
        )
        Crew(
            agents=[self.agents[self.tdefs[key]["agent"]]],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        ).kickoff(inputs=self.inputs)
        return _out(task, _TASKS[key].model)


class _OrgState(BaseModel):
    rounds: int = 0
    rejection: str = ""
    pm_draft: DraftPortfolio | None = None
    risk_review: RiskReview | None = None
    cio: CIODecision | None = None
    held: bool = False


class _OrgFlow(Flow[_OrgState]):
    """⑥ PM → ⑦ Risk → (@router) 반려 1회 or CIO. crewai.Flow @router."""

    def __init__(self, ctx: _Ctx) -> None:
        super().__init__()
        self._ctx = ctx

    @start("pm_revise")
    def pm(self) -> None:
        self.state.rounds += 1
        extra = (
            f"\n\n[Risk Officer 반려 사유] {self.state.rejection}" if self.state.rejection else ""
        )
        self.state.pm_draft = self._ctx.run("pm_draft", extra_desc=extra)

    @listen(pm)
    def risk(self) -> None:
        self.state.risk_review = self._ctx.run("risk_review")

    @router(risk)
    def route(self) -> str:
        rv = self.state.risk_review
        if rv is not None and rv.verdict == "REJECTED" and self.state.rounds < _MAX_ROUNDS:
            self.state.rejection = "; ".join(rv.concerns) or "리스크 재검토 요청"
            return "pm_revise"
        if rv is not None and rv.verdict == "REJECTED":
            self.state.held = True  # 2회차도 REJECTED → 리밸런싱 보류
        return "to_cio"

    @listen("to_cio")
    def cio(self) -> None:
        self.state.cio = self._ctx.run("cio_decision")


def _pm_inputs(pr: PipelineResult, excluded: list[str]) -> dict[str, str]:
    det = {
        "category_targets_pct": {
            k: round(v * 100, 1) for k, v in pr.allocation.category_targets_total.items()
        },
        "top_pool": {
            cat: [
                s.ticker
                for s in sc.scores[: max(1, round(pr.allocation.max_positions.get(cat, 15) * 1.5))]
            ]
            for cat, sc in pr.scoring.items()
        },
        "det_positions": [
            {"ticker": p.ticker, "category": p.category, "weight_pct": round(p.weight * 100, 2)}
            for p in pr.draft.positions
        ],
    }
    return {
        "det_draft_json": json.dumps(det, ensure_ascii=False),
        "excluded_json": json.dumps(excluded, ensure_ascii=False),
    }


def _clamped(pm_draft: DraftPortfolio, pr: PipelineResult, excluded: list[str]) -> SizingResult:
    # 틸트 기준은 이번 회차 결정론 배분 (램프업 반영) — 최종 목표가 아님.
    # 그래야 max_change_per_rebal(10%p/회) 를 안 깨고 PM 재량이 ±3%p 로 유지된다.
    det = {c: pr.draft.category_weights.get(c, 0.0) for c in _CATS}
    # PM 이 아예 안 건드린 카테고리는 결정론 종목 그대로 (카테고리 전면 제거 = ±3%p 위반 방지)
    pm_cats = {(p.category or "").lower() for p in pm_draft.positions}  # LLM 대소문자 무관
    excl = {t.upper() for t in excluded}
    merged = list(pm_draft.positions) + [
        p for p in pr.draft.positions if p.category not in pm_cats and p.ticker.upper() not in excl
    ]
    return clamp_pm_draft(
        PMDraft(category_weights=pm_draft.category_weights, positions=merged),
        det_targets=det,
        scoring=dict(pr.scoring),
        max_positions=pr.allocation.max_positions,
        excluded=excluded,
        nav_usd=pr.nav_usd,
    )


def _to_draft(sizing: SizingResult, pr: PipelineResult) -> DraftPortfolio:
    return DraftPortfolio(
        category_weights=sizing.category_weights,
        positions=[
            Position(ticker=p.ticker, category=p.category, weight=p.weight, sector=p.sector)
            for p in sizing.positions
        ],
        prior_category_weights={c: round(pr.draft.category_weights.get(c, 0.0), 6) for c in _CATS},
    )


def _org_orders(
    sizing: SizingResult,
    pr: PipelineResult,
    pf: PaperPortfolio,
    prices: dict[str, float],
    pending: float,
) -> list[Order]:
    budgets = {c: sizing.category_weights.get(c, 0.0) for c in _CATS}
    plan = cash_flow_rebalance(
        budgets,
        category_usd(pf, prices),
        pf.cash_usd,
        pending,
        dict(pf.cooldown_days),
        crisis=pr.regime.crisis_active,
    )
    if isinstance(plan, ToolError):
        _log.warning("조직 리밸런싱 실패: %s — 결정론 주문 유지", plan.error)
        return list(pr.orders)
    return build_orders(sizing, pf, prices, plan)


def _recall_block(pr: PipelineResult) -> str:
    """판단 일기 유사 사례 (§6). 콜드 스타트·RAG 오류 시 빈 문자열 — 크루를 막지 않는다."""
    try:
        snap = _diary_snapshot(pr)
        qtext, qtags = build_query(regime=pr.regime.regime.value, snapshot=snap)
        return format_recall(DiaryRAG().recall(qtext, qtags))
    except Exception as e:  # RAG 실패는 크루 중단 사유 아님
        _log.warning("일기 회상 실패: %s", e)
        return ""


def run_organization(
    pr: PipelineResult,
    *,
    portfolio: PaperPortfolio,
    prices: dict[str, float],
    pending_contribution_usd: float = 0.0,
    run_id: str | None = None,
    llm: Any | None = None,
    dry_run: bool = False,
) -> CrewOutcome:
    """`dry_run=True` (DRY_RUN): 크루는 돌지만 일기·RAG·Slack 노트·회상 전부 스킵 —
    `state/` 무접촉. 크루 출력은 리포트·`outputs/<run_id>/crew.json` 에만 남는다."""
    run_id = run_id or pr.as_of
    quiet_crew_console()
    agents = _agents(llm)
    tdefs = _cfg("tasks.yaml")
    allowed = _num_payload(pr)
    diary_ids: list[str] = []
    inputs = build_inputs(pr)
    recall = "" if dry_run else _recall_block(pr)  # 회상 = ChromaDB 접근 → state/chroma 생성

    bundle: AnalystBundle = run_analysts(
        pr,
        agents=agents,
        tdefs=tdefs,
        allowed=allowed,
        run_id=run_id,
        diary_ids=diary_ids,
        inputs=inputs,
        diary_recall=recall,
        dry_run=dry_run,
    )
    inputs.update(_pm_inputs(pr, bundle.research_view.excluded_tickers))
    inputs["research_view_json"] = bundle.research_view.model_dump_json()

    ctx = _Ctx(
        agents=agents,
        tdefs=tdefs,
        allowed=allowed,
        pr=pr,
        run_id=run_id,
        diary_ids=diary_ids,
        inputs=inputs,
        recall=recall,
        dry_run=dry_run,
    )
    flow = _OrgFlow(ctx)
    flow.kickoff()
    st = flow.state

    pm_raw = st.pm_draft or DraftPortfolio(
        category_weights=pr.draft.category_weights, positions=pr.draft.positions
    )
    sizing = _clamped(pm_raw, pr, bundle.research_view.excluded_tickers)
    org_draft = _to_draft(sizing, pr)
    constraints: ConstraintResult = check_constraints(org_draft)
    cio = st.cio or CIODecision(verdict="APPROVED", ic_memo="크루 파싱 실패 — 결정론 유지")
    held = st.held or cio.verdict == "HOLD"
    # 하드 가드레일(고위험캡·섹터캡·단일캡) 위반은 불가침 — 클램프가 못 잡은 위반이면
    # 조직 주문을 버리고 결정론 주문으로 폴백 (CLAUDE.md 절대 규칙 3).
    if constraints.verdict == "FAIL":
        _log.warning(
            "조직 draft 제약 위반 %s — 결정론 주문 폴백", [v.rule for v in constraints.violations]
        )

    if held:
        org_orders: list[Order] = []
    elif constraints.verdict == "FAIL":
        org_orders = list(pr.orders)
    else:
        org_orders = _org_orders(sizing, pr, portfolio, prices, pending_contribution_usd)
    if not dry_run:
        _log_org_diary(st, org_draft, pr, run_id, diary_ids)

    return CrewOutcome(
        run_id=run_id,
        macro_brief=bundle.macro_brief,
        fundamental_notes=bundle.fundamental_notes,
        thematic_notes=bundle.thematic_notes,
        market_narrative=bundle.market_narrative,
        research_view=bundle.research_view,
        pm_draft=org_draft,
        risk_review=st.risk_review,
        risk_rounds=st.rounds,
        cio=cio,
        org_orders=org_orders,
        rebalance_held=held,
        diary_ids=diary_ids,
        llm_used=llm is None,
    )


def _log_org_diary(
    st: _OrgState, org_draft: DraftPortfolio, pr: PipelineResult, run_id: str, sink: list[str]
) -> None:
    reg = pr.regime.regime.value
    snap = _diary_snapshot(pr)
    rates_dir = pr.macro.fed_funds_trend
    det = pr.draft.category_weights
    tilts = {c: round(org_draft.category_weights.get(c, 0.0) - det.get(c, 0.0), 4) for c in _CATS}
    if any(abs(v) > 0.005 for v in tilts.values()):
        dom = max(tilts, key=lambda c: abs(tilts[c]))
        action = (
            "defensive_tilt"
            if tilts.get("high", 0.0) < 0 or tilts.get("low", 0.0) > 0
            else "offensive_tilt"
        )
        e = diary.log(
            run_id=run_id,
            agent="Portfolio Manager",
            claim_type="allocation_tilt",
            claim=f"PM 틸트(%p) {tilts}",
            reasoning=(getattr(st.pm_draft, "tilt_rationale", "") or "하우스뷰 반영")[:400],
            data_snapshot=snap,
            decision={"tilts_pp": tilts, "enforced": True},
            situation_text=f"[상황] {pr.as_of} 레짐 {reg}, NAV ${pr.nav_usd:.0f}",
            shadow_link=f"state/shadow.json#{run_id}",
            tags=derive_tags(
                regime=reg,
                claim_type="allocation_tilt",
                sleeve=dom,
                action=action,
                magnitude=magnitude_of(max(abs(v) for v in tilts.values()) * 100),
                rates_dir=rates_dir,
                data_snapshot=snap,
            ),
        )
        if hasattr(e, "id"):
            sink.append(e.id)
    rv = st.risk_review
    if rv is not None and rv.verdict == "REJECTED":
        e = diary.log(
            run_id=run_id,
            agent="Risk Officer",
            claim_type="risk_veto",
            claim=f"Risk REJECTED (라운드 {st.rounds}): {'; '.join(rv.concerns)}"[:300],
            reasoning=("; ".join(rv.conditions) or "정성 리스크")[:400],
            data_snapshot=snap,
            decision={"verdict": "REJECTED", "held": st.held},
            situation_text=f"[상황] {pr.as_of} 레짐 {reg}",
            tags=derive_tags(
                regime=reg,
                claim_type="risk_veto",
                action="veto",
                rates_dir=rates_dir,
                data_snapshot=snap,
            ),
        )
        if hasattr(e, "id"):
            sink.append(e.id)
