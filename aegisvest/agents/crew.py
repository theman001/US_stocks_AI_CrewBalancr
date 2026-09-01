"""주간 크루 — ① Macro + ②③④ 애널리스트(async) → ⑤ Research Director → ⑧ CIO.

report/phase-3 §3·§4·§9. Process.sequential + 명시적 context (Hierarchical 금지).
에이전트는 판단만 — 숫자는 PipelineResult 에서. 결정론 주문 불변 (CIO HOLD 만 실행 스킵).
3b-2 부터 ⑥ PM 이 ResearchView 로 ±3%p 틸트 + ⑦ Risk 반려 루프.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import yaml
from crewai import Agent, Crew, Process, Task
from pydantic import BaseModel

from aegisvest.agents import quiet_crew_console
from aegisvest.agents import tools as agent_tools
from aegisvest.agents.guardrails import no_fabricated_numbers
from aegisvest.config import CONFIG_DIR
from aegisvest.diary import logger as diary
from aegisvest.diary.schema import derive_tags
from aegisvest.llm import get_llm
from aegisvest.notify import post_agent_note
from aegisvest.schemas import (
    CIODecision,
    FundamentalNotes,
    MacroBrief,
    MarketNarrative,
    PipelineResult,
    PMDraft,
    ResearchView,
    RiskReview,
    ThematicNotes,
)

_log = logging.getLogger("aegisvest.crew")

_ABSOLUTE_RULES = """
## 절대 규칙 (위반 시 출력 폐기)
1. 어떤 숫자도 직접 생성하지 않는다. 모든 수치는 위 페이로드 또는 툴 반환값이어야 한다.
2. 데이터가 없으면 "DATA_UNAVAILABLE: <필드>" 라고만 쓰고 추정하지 마라.
3. 산술(비율·가중평균 포함) 암산 금지.
4. "약", "대략", "추정", "~" 로 수치를 말하면 실패다.
""".strip()

# 에이전트별 툴 (docs/PROMPTS.md 규칙 5 — ①②③ 만 툴 사용, ⑨는 Phase 4)
_AGENT_TOOLS: dict[str, list[Any]] = {
    "macro_strategist": [agent_tools.NEWS],
    "fundamental_analyst": [agent_tools.NEWS, agent_tools.FUNDAMENTALS],
    "thematic_analyst": [agent_tools.NEWS, agent_tools.TECHNICAL],
}


@dataclass(frozen=True)
class _Spec:
    model: type[BaseModel]
    agent_name: str
    emoji: str
    channel: str


_TASKS: dict[str, _Spec] = {
    "macro_brief": _Spec(MacroBrief, "Macro Strategist", "🧭", "aegis-research"),
    "fundamental_notes": _Spec(FundamentalNotes, "Fundamental Analyst", "📊", "aegis-research"),
    "thematic_notes": _Spec(ThematicNotes, "Thematic Analyst", "🚀", "aegis-research"),
    "market_narrative": _Spec(MarketNarrative, "News & Sentiment", "📰", "aegis-research"),
    "research_view": _Spec(ResearchView, "Research Director", "🧩", "aegis-research"),
    "pm_draft": _Spec(PMDraft, "Portfolio Manager", "📐", "aegis-decisions"),
    "risk_review": _Spec(RiskReview, "Risk Officer", "🛡️", "aegis-decisions"),
    "cio_decision": _Spec(CIODecision, "CIO", "⚖️", "aegis-decisions"),
}


def _cfg(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _round_map(d: dict[str, float], n: int = 4) -> dict[str, float]:
    return {k: round(v, n) for k, v in d.items()}


def build_inputs(pr: PipelineResult) -> dict[str, str]:
    """PipelineResult 를 태스크 description 플레이스홀더용 JSON 문자열로."""
    rg = pr.regime
    alloc = pr.allocation
    candidates = {
        cat: [{"ticker": s.ticker, "score": s.score, "subtier": s.subtier} for s in sc.scores[:8]]
        for cat, sc in pr.scoring.items()
    }
    return {
        "regime_json": json.dumps(
            {
                "regime": rg.regime.value,
                "total_score": rg.total_score,
                "score_smooth": round(rg.score_smooth, 2),
                "low_confidence": rg.low_confidence,
                "n_axes_present": rg.n_axes_present,
                "crisis_active": rg.crisis_active,
                "axis_scores": rg.axis_scores,
                "rationale": rg.rationale,
            },
            ensure_ascii=False,
        ),
        "regime_summary": (
            f"{rg.regime.value} (smooth {round(rg.score_smooth, 1)}, crisis={rg.crisis_active})"
        ),
        "allocation_json": json.dumps(
            {
                "equity_sleeve_pct": round(alloc.equity_sleeve_pct * 100, 1),
                "cash_pct": round(alloc.cash_pct * 100, 1),
                "category_targets_pct": {
                    k: round(v * 100, 1) for k, v in alloc.category_targets_total.items()
                },
            },
            ensure_ascii=False,
        ),
        "low_mid_candidates_json": json.dumps(
            {c: candidates.get(c, []) for c in ("low", "mid")}, ensure_ascii=False
        ),
        "high_candidates_json": json.dumps(candidates.get("high", []), ensure_ascii=False),
        "draft_json": json.dumps(
            {
                "category_weights_pct": {
                    k: round(v * 100, 1) for k, v in pr.draft.category_weights.items()
                },
                "positions": [
                    {
                        "ticker": p.ticker,
                        "category": p.category,
                        "weight_pct": round(p.weight * 100, 2),
                    }
                    for p in pr.draft.positions
                ],
            },
            ensure_ascii=False,
        ),
        "constraints_json": json.dumps(
            {
                "verdict": pr.constraints.verdict,
                "violations": [
                    {"rule": v.rule, "detail": v.detail} for v in pr.constraints.violations
                ],
            },
            ensure_ascii=False,
        ),
        "pipeline_notes": json.dumps(pr.notes, ensure_ascii=False),
    }


def _agents(llm: Any) -> dict[str, Agent]:
    quiet_crew_console()
    out: dict[str, Agent] = {}
    for key, d in _cfg("agents.yaml").items():
        out[key] = Agent(
            role=d["role"],
            goal=d["goal"],
            backstory=d["backstory"].replace("{absolute_rules}", _ABSOLUTE_RULES),
            llm=llm or get_llm(temperature=float(d.get("temperature", 0.2))),
            tools=list(_AGENT_TOOLS.get(key, [])),
            allow_delegation=False,
            verbose=False,
        )
    return out


# hedge_only: 툴 반환값 인용(①②③) 또는 클램프될 제안 비중 산출(⑥ PM) → 헤지 표현만 검사
_HEDGE_ONLY_TASKS = {"macro_brief", "fundamental_notes", "thematic_notes", "pm_draft"}


def make_task(
    key: str,
    context: list[Task],
    *,
    agents: dict[str, Agent],
    tdefs: dict[str, Any],
    allowed: dict[str, Any],
    pr: PipelineResult,
    run_id: str,
    diary_ids: list[str],
    is_async: bool = False,
    extra_desc: str = "",
) -> Task:
    td = tdefs[key]
    return Task(
        description=td["description"] + extra_desc,
        expected_output=td["expected_output"],
        agent=agents[td["agent"]],
        context=context,
        output_pydantic=_TASKS[key].model,
        guardrail=no_fabricated_numbers(allowed, hedge_only=key in _HEDGE_ONLY_TASKS),
        callback=_callback(key, pr, run_id, diary_ids),
        async_execution=is_async,
    )


@dataclass
class AnalystBundle:
    macro_brief: MacroBrief
    fundamental_notes: FundamentalNotes
    thematic_notes: ThematicNotes
    market_narrative: MarketNarrative
    research_view: ResearchView


def run_analysts(
    pr: PipelineResult,
    *,
    agents: dict[str, Agent],
    tdefs: dict[str, Any],
    allowed: dict[str, Any],
    run_id: str,
    diary_ids: list[str],
    inputs: dict[str, str],
) -> AnalystBundle:
    """① Macro + ②③④ (async 병렬) → ⑤ Research Director. Process.sequential."""

    def mk(key: str, ctx: list[Task], *, is_async: bool = False) -> Task:
        return make_task(
            key,
            ctx,
            agents=agents,
            tdefs=tdefs,
            allowed=allowed,
            pr=pr,
            run_id=run_id,
            diary_ids=diary_ids,
            is_async=is_async,
        )

    t_macro = mk("macro_brief", [], is_async=True)
    t_fund = mk("fundamental_notes", [], is_async=True)
    t_thematic = mk("thematic_notes", [], is_async=True)
    t_news = mk("market_narrative", [], is_async=True)
    t_rd = mk("research_view", [t_macro, t_fund, t_thematic, t_news])
    Crew(
        agents=list(agents.values()),
        tasks=[t_macro, t_fund, t_thematic, t_news, t_rd],
        process=Process.sequential,
        verbose=False,
    ).kickoff(inputs=inputs)
    return AnalystBundle(
        macro_brief=_out(t_macro, MacroBrief),
        fundamental_notes=_out(t_fund, FundamentalNotes),
        thematic_notes=_out(t_thematic, ThematicNotes),
        market_narrative=_out(t_news, MarketNarrative),
        research_view=_out(t_rd, ResearchView),
    )


def _num_payload(pr: PipelineResult) -> dict[str, Any]:
    """guardrail 이 허용할 수치 전체 — 에이전트가 인용할 수 있는 파이프라인 값."""
    a = pr.allocation
    return {
        "targets": _round_map(a.category_targets_total),
        "targets_sleeve": _round_map(a.category_targets_sleeve),
        "sleeve_pct": a.equity_sleeve_pct,
        "cash_pct": a.cash_pct,
        "guardrails": a.guardrails,
        "weights": _round_map(pr.draft.category_weights),
        "position_weights": [round(p.weight, 4) for p in pr.draft.positions],
        "scores": [s.score for sc in pr.scoring.values() for s in sc.scores],
        "screen_counts": pr.screen_counts,
        "axis_scores": pr.regime.axis_scores,
        "nav": pr.nav_usd,
        "score_smooth": pr.regime.score_smooth,
        "total_score": pr.regime.total_score,
        "n_axes_present": pr.regime.n_axes_present,
    }


def _coerce(o: Any, model: type[Any]) -> Any:
    """TaskOutput → Pydantic 모델. crewai 자동 변환 실패 시 raw JSON 파싱 (mock 경로)."""
    if o is None:
        return None
    if getattr(o, "pydantic", None) is not None:
        return o.pydantic
    if getattr(o, "json_dict", None):
        return model.model_validate(o.json_dict)
    raw = (getattr(o, "raw", "") or "").strip()
    if raw and (start := raw.find("{")) >= 0:
        with suppress(ValueError):
            return model.model_validate_json(raw[start : raw.rfind("}") + 1])
    return None


def _out(task: Task, model: type[Any]) -> Any:
    parsed = _coerce(task.output, model)
    if parsed is None:
        raise RuntimeError(f"{task.name or model.__name__}: 크루 출력 파싱 실패")
    return parsed


def _callback(key: str, pr: PipelineResult, run_id: str, sink: list[str]) -> Callable[[Any], None]:
    spec = _TASKS[key]

    def cb(task_output: Any) -> None:
        model = _coerce(task_output, spec.model)
        raw = getattr(task_output, "raw", "") or ""
        post_agent_note(
            spec.agent_name, spec.emoji, _summary(key, model), raw[:1500], channel=spec.channel
        )
        entry = _log_diary(key, model, pr, run_id, spec.agent_name)
        if entry is not None:
            sink.append(entry)

    return cb


def _summary(key: str, model: Any) -> str:
    if model is None:
        return "(출력 파싱 전)"
    fns: dict[str, Callable[[Any], str]] = {
        "macro_brief": lambda m: f"{m.regime} · {m.confidence} · 상충 {len(m.axis_conflicts)}",
        "fundamental_notes": lambda m: (
            f"{len(m.notes)}종목 · exclude {sum(n.exclude_recommended for n in m.notes)}"
            f" · trap {sum(n.valuation_trap for n in m.notes)}"
        ),
        "thematic_notes": lambda m: (
            f"{len(m.notes)}종목 · 크라우딩 {sum(n.crowding_flag for n in m.notes)}"
        ),
        "market_narrative": lambda m: f"이벤트 리스크 {len(m.event_risks)}",
        "research_view": lambda m: (
            f"스탠스 {{{', '.join(f'{k}:{v.stance}' for k, v in m.sleeve_stance.items())}}}"
            f" · 교차리스크 {len(m.cross_risks)}"
        ),
        "pm_draft": lambda m: (
            f"{len(m.positions)}종목 · "
            + ", ".join(
                f"{k} {round(v * 100, 1)}%" for k, v in m.category_weights.items() if k != "cash"
            )
        ),
        "risk_review": lambda m: f"{m.verdict} · 우려 {len(m.concerns)}",
        "cio_decision": lambda m: (
            m.verdict + (f" · {m.hold_reason}" if m.verdict == "HOLD" else "")
        ),
    }
    return fns.get(key, lambda _m: key)(model)


def _dc_macro(m: Any, pr: PipelineResult) -> dict[str, Any]:
    return {
        "claim": f"레짐 {m.regime} 유지 전망 (confidence {m.confidence})",
        "reasoning": " / ".join(m.risk_scenarios[:3]) or m.regime,
        "decision": {"regime": m.regime, "watch_items": m.watch_items},
        "action": "crisis_shift" if pr.regime.crisis_active else None,
    }


def _dc_fundamental(m: Any, pr: PipelineResult) -> dict[str, Any] | None:
    ex = [n.ticker for n in m.notes if n.exclude_recommended]
    if not ex:
        return None
    why = "; ".join(f"{n.ticker}: {n.thesis_1line}" for n in m.notes if n.exclude_recommended)
    return {
        "claim": f"펀더멘털 제외 권고: {', '.join(ex)}",
        "reasoning": why[:400],
        "decision": {"excluded": ex, "enforced": False},
        "action": "exclusion",
    }


def _dc_thematic(m: Any, pr: PipelineResult) -> dict[str, Any] | None:
    cats = [n for n in m.notes if n.catalyst]
    if not cats:
        return None
    dates = "; ".join(f"{n.ticker}: {n.catalyst} ({n.catalyst_date or '미정'})" for n in cats)
    mom = "; ".join(f"{n.ticker} 모멘텀 {n.momentum_durability}" for n in cats)
    return {
        "claim": dates[:300],
        "reasoning": mom[:400],
        "decision": {"catalysts": [{"ticker": n.ticker, "date": n.catalyst_date} for n in cats]},
        "action": "catalyst_bet",
        "sleeve": "high",
    }


def _dc_news(m: Any, pr: PipelineResult) -> dict[str, Any] | None:
    if not m.event_risks:
        return None
    return {
        "claim": "; ".join(f"{e.event} ({e.severity})" for e in m.event_risks)[:300],
        "reasoning": m.weekly_summary[:400],
        "decision": {"events": [e.model_dump() for e in m.event_risks]},
    }


def _dc_research(m: Any, pr: PipelineResult) -> dict[str, Any] | None:
    if not m.sleeve_stance:
        return None
    return {
        "claim": "; ".join(f"{k} {v.stance}" for k, v in m.sleeve_stance.items()),
        "reasoning": "; ".join(f"{k}: {v.reason}" for k, v in m.sleeve_stance.items())[:400],
        "decision": {
            "sleeve_stance": {k: v.stance for k, v in m.sleeve_stance.items()},
            "enforced": False,
        },
    }


def _dc_cio(m: Any, pr: PipelineResult) -> dict[str, Any] | None:
    if m.verdict != "HOLD":
        return None
    return {
        "claim": f"이번 주 리밸런싱 HOLD: {m.hold_reason}",
        "reasoning": m.ic_memo[:600],
        "decision": {"verdict": "HOLD"},
        "action": "hold",
    }


# key → (claim_type, 빌더). None 반환 시 기록 안 함.
_DIARY: dict[str, tuple[str, Callable[[Any, PipelineResult], dict[str, Any] | None]]] = {
    "macro_brief": ("regime_call", _dc_macro),
    "fundamental_notes": ("exclusion", _dc_fundamental),
    "thematic_notes": ("catalyst", _dc_thematic),
    "market_narrative": ("event_risk", _dc_news),
    "research_view": ("sleeve_stance", _dc_research),
    "cio_decision": ("cio_override", _dc_cio),
}


def _log_diary(
    key: str, model: Any, pr: PipelineResult, run_id: str, agent_name: str
) -> str | None:
    if model is None or key not in _DIARY:
        return None
    claim_type, builder = _DIARY[key]
    kw = builder(model, pr)
    if kw is None:
        return None
    reg = pr.regime.regime.value
    sleeve = kw.get("sleeve") or ("high" if claim_type == "catalyst" else None)
    snap = _diary_snapshot(pr)
    entry = diary.log(
        run_id=run_id,
        agent=agent_name,
        claim_type=claim_type,
        data_snapshot=snap,
        situation_text=_situation(pr),
        tags=derive_tags(
            regime=reg,
            claim_type=claim_type,
            sleeve=sleeve,
            action=kw.get("action"),
            rates_dir=pr.macro.fed_funds_trend,
            data_snapshot=snap,
        ),
        claim=kw["claim"],
        reasoning=kw["reasoning"],
        decision=kw["decision"],
    )
    return entry.id if hasattr(entry, "id") else None


def _diary_snapshot(pr: PipelineResult) -> dict[str, float | int | str | None]:
    rg = pr.regime
    snap: dict[str, float | int | str | None] = pr.macro.model_dump(exclude={"stale_fields"})
    snap.update(
        {
            "regime": rg.regime.value,
            "score_smooth": round(rg.score_smooth, 2),
            "total_score": rg.total_score,
            "n_axes_present": rg.n_axes_present,
            "nav_usd": pr.nav_usd,
            "constraints": pr.constraints.verdict,
            **{f"target_{k}": round(v, 4) for k, v in pr.allocation.category_targets_total.items()},
        }
    )
    return snap


def _situation(pr: PipelineResult) -> str:
    rg = pr.regime
    return (
        f"[상황] {pr.as_of}, 레짐 {rg.regime.value}(score_smooth {round(rg.score_smooth, 1)}). "
        f"n_axes {rg.n_axes_present}. NAV ${pr.nav_usd:.0f}. 제약 {pr.constraints.verdict}."
    )
