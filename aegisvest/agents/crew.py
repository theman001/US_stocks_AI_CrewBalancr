"""주간 크루 — ① Macro Strategist → ②③④ 통합 Analyst → ⑧ CIO. report/phase-3 §4·§9.

Process.sequential + 명시적 context (Hierarchical 금지). 에이전트는 판단만 —
숫자는 전부 PipelineResult 에서 온다. 3a-9: CIO HOLD 시 실행만 스킵, 주문은 불변.
"""

from __future__ import annotations

import json
import logging
from contextlib import suppress
from typing import Any

import yaml
from crewai import Agent, Crew, Process, Task

from aegisvest.agents.guardrails import no_fabricated_numbers
from aegisvest.config import CONFIG_DIR
from aegisvest.diary import logger as diary
from aegisvest.diary.schema import derive_tags
from aegisvest.llm import get_llm
from aegisvest.notify import post_agent_note
from aegisvest.schemas import (
    AnalystView,
    CIODecision,
    CrewOutcome,
    MacroBrief,
    PipelineResult,
)

_log = logging.getLogger("aegisvest.crew")

_ABSOLUTE_RULES = """
## 절대 규칙 (위반 시 출력 폐기)
1. 어떤 숫자도 직접 생성하지 않는다. 모든 수치는 위에 주어진 페이로드 값이어야 한다.
2. 데이터가 없으면 "DATA_UNAVAILABLE: <필드>" 라고만 쓰고 추정하지 마라.
3. 산술(비율·가중평균 포함) 암산 금지.
4. "약", "대략", "추정", "~" 로 수치를 말하면 실패다.
""".strip()


def _cfg(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _round_map(d: dict[str, float], n: int = 4) -> dict[str, float]:
    return {k: round(v, n) for k, v in d.items()}


def build_inputs(pr: PipelineResult) -> dict[str, str]:
    """PipelineResult 를 태스크 description 플레이스홀더용 JSON 문자열로."""
    rg = pr.regime
    regime_json = json.dumps(
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
    )
    alloc = pr.allocation
    allocation_json = json.dumps(
        {
            "equity_sleeve_pct": round(alloc.equity_sleeve_pct * 100, 1),
            "cash_pct": round(alloc.cash_pct * 100, 1),
            "category_targets_pct": {
                k: round(v * 100, 1) for k, v in alloc.category_targets_total.items()
            },
        },
        ensure_ascii=False,
    )
    candidates = {
        cat: [{"ticker": s.ticker, "score": s.score, "subtier": s.subtier} for s in sc.scores[:8]]
        for cat, sc in pr.scoring.items()
    }
    draft_json = json.dumps(
        {
            "category_weights_pct": {
                k: round(v * 100, 1) for k, v in pr.draft.category_weights.items()
            },
            "positions": [
                {"ticker": p.ticker, "category": p.category, "weight_pct": round(p.weight * 100, 2)}
                for p in pr.draft.positions
            ],
        },
        ensure_ascii=False,
    )
    constraints_json = json.dumps(
        {
            "verdict": pr.constraints.verdict,
            "violations": [{"rule": v.rule, "detail": v.detail} for v in pr.constraints.violations],
        },
        ensure_ascii=False,
    )
    regime_summary = (
        f"{rg.regime.value} (score_smooth {round(rg.score_smooth, 1)}, crisis={rg.crisis_active})"
    )
    return {
        "regime_json": regime_json,
        "regime_summary": regime_summary,
        "allocation_json": allocation_json,
        "candidates_json": json.dumps(candidates, ensure_ascii=False),
        "draft_json": draft_json,
        "constraints_json": constraints_json,
        "pipeline_notes": json.dumps(pr.notes, ensure_ascii=False),
    }


def _agents(llm: Any) -> dict[str, Agent]:
    defs = _cfg("agents.yaml")
    out: dict[str, Agent] = {}
    for key, d in defs.items():
        agent_llm = llm or get_llm(temperature=float(d.get("temperature", 0.2)))
        out[key] = Agent(
            role=d["role"],
            goal=d["goal"],
            backstory=d["backstory"].replace("{absolute_rules}", _ABSOLUTE_RULES),
            llm=agent_llm,
            tools=[],
            allow_delegation=False,
            verbose=False,
        )
    return out


def _diary_snapshot(pr: PipelineResult) -> dict[str, float | int | str | None]:
    rg = pr.regime
    return {
        "regime": rg.regime.value,
        "score_smooth": round(rg.score_smooth, 2),
        "total_score": rg.total_score,
        "n_axes_present": rg.n_axes_present,
        "nav_usd": pr.nav_usd,
        "constraints": pr.constraints.verdict,
        **{f"target_{k}": round(v, 4) for k, v in pr.allocation.category_targets_total.items()},
    }


def run_crew(
    pr: PipelineResult, *, run_id: str | None = None, llm: Any | None = None
) -> CrewOutcome:
    """주간 크루 실행. `llm` 지정 시 전 에이전트 오버라이드 (테스트용 스크립트 LLM)."""
    run_id = run_id or pr.as_of
    inputs = build_inputs(pr)
    agents = _agents(llm)
    tdefs = _cfg("tasks.yaml")
    diary_ids: list[str] = []

    def _mk(key: str, model: type[Any], context: list[Task], channel: str) -> Task:
        td = tdefs[key]
        payload = json.loads(inputs.get("regime_json", "{}"))
        return Task(
            description=td["description"],
            expected_output=td["expected_output"],
            agent=agents[td["agent"]],
            context=context,
            output_pydantic=model,
            guardrail=no_fabricated_numbers({**payload, **_num_payload(pr)}),
            callback=_callback(key, pr, run_id, channel, diary_ids),
        )

    t_macro = _mk("macro_brief", MacroBrief, [], "aegis-research")
    t_analyst = _mk("analyst_view", AnalystView, [t_macro], "aegis-research")
    t_cio = _mk("cio_decision", CIODecision, [t_macro, t_analyst], "aegis-decisions")

    crew = Crew(
        agents=list(agents.values()),
        tasks=[t_macro, t_analyst, t_cio],
        process=Process.sequential,
        verbose=False,
    )
    crew.kickoff(inputs=inputs)

    macro_out = _out(t_macro, MacroBrief)
    analyst_out = _out(t_analyst, AnalystView)
    cio_out = _out(t_cio, CIODecision)
    return CrewOutcome(
        run_id=run_id,
        macro_brief=macro_out,
        analyst_view=analyst_out,
        cio=cio_out,
        diary_ids=diary_ids,
        llm_used=llm is None,
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
    """TaskOutput → Pydantic 모델. crewai 가 자동 변환 못 하면 raw JSON 파싱."""
    if o is None:
        return None
    if getattr(o, "pydantic", None) is not None:
        return o.pydantic
    if getattr(o, "json_dict", None):
        return model.model_validate(o.json_dict)
    raw = (getattr(o, "raw", "") or "").strip()
    if raw:
        start = raw.find("{")
        if start >= 0:
            with suppress(ValueError):
                return model.model_validate_json(raw[start : raw.rfind("}") + 1])
    return None


def _out(task: Task, model: type[Any]) -> Any:
    parsed = _coerce(task.output, model)
    if parsed is None:
        raise RuntimeError(f"{task.name or model.__name__}: 크루 출력 파싱 실패")
    return parsed


def _callback(
    key: str,
    pr: PipelineResult,
    run_id: str,
    channel: str,
    sink: list[str],
) -> Any:
    _MODEL = {"macro_brief": MacroBrief, "analyst_view": AnalystView, "cio_decision": CIODecision}

    def cb(task_output: Any) -> None:
        model = _coerce(task_output, _MODEL[key])
        raw = getattr(task_output, "raw", "") or ""
        agent_name = {
            "macro_brief": "Macro Strategist",
            "analyst_view": "통합 Analyst",
            "cio_decision": "CIO",
        }[key]
        emoji = {"macro_brief": "🧭", "analyst_view": "🔬", "cio_decision": "⚖️"}[key]
        post_agent_note(agent_name, emoji, _summary(key, model), raw[:1500], channel=channel)
        _entry = _log_diary(key, model, pr, run_id, agent_name)
        if _entry is not None:
            sink.append(_entry)

    return cb


def _summary(key: str, model: Any) -> str:
    if model is None:
        return "(출력 파싱 전)"
    if key == "macro_brief":
        return f"{model.regime} · confidence {model.confidence} · 상충 {len(model.axis_conflicts)}"
    if key == "analyst_view":
        return f"exclude 권고 {len(model.excluded_tickers)} · 이벤트 {len(model.event_risks)}"
    return f"{model.verdict}" + (f" · {model.hold_reason}" if model.verdict == "HOLD" else "")


def _log_diary(
    key: str, model: Any, pr: PipelineResult, run_id: str, agent_name: str
) -> str | None:
    if model is None:
        return None
    snap = _diary_snapshot(pr)
    rg = pr.regime
    if key == "macro_brief":
        e = diary.log(
            run_id=run_id,
            agent=agent_name,
            claim_type="regime_call",
            claim=f"레짐 {model.regime} 유지 전망 (confidence {model.confidence})",
            reasoning=" / ".join(model.risk_scenarios[:3]) or model.regime,
            data_snapshot=snap,
            decision={"regime": model.regime, "watch_items": model.watch_items},
            situation_text=_situation(pr),
            tags=derive_tags(regime=rg.regime.value, claim_type="regime_call"),
        )
    elif key == "analyst_view" and model.excluded_tickers:
        e = diary.log(
            run_id=run_id,
            agent=agent_name,
            claim_type="exclusion",
            claim=f"정성 제외 권고: {', '.join(model.excluded_tickers)}",
            reasoning=model.weekly_narrative[:400],
            data_snapshot=snap,
            decision={"excluded": model.excluded_tickers, "enforced": False},
            situation_text=_situation(pr),
            tags=derive_tags(regime=rg.regime.value, claim_type="exclusion"),
        )
    elif key == "cio_decision" and model.verdict == "HOLD":
        e = diary.log(
            run_id=run_id,
            agent=agent_name,
            claim_type="cio_override",
            claim=f"이번 주 리밸런싱 HOLD: {model.hold_reason}",
            reasoning=model.ic_memo[:600],
            data_snapshot=snap,
            decision={"verdict": "HOLD", "orders_suppressed": len(pr.orders)},
            situation_text=_situation(pr),
            tags=derive_tags(regime=rg.regime.value, claim_type="cio_override"),
        )
    else:
        return None
    return e.id if hasattr(e, "id") else None


def _situation(pr: PipelineResult) -> str:
    rg = pr.regime
    return (
        f"[상황] {pr.as_of}, 레짐 {rg.regime.value}(score_smooth {round(rg.score_smooth, 1)}). "
        f"n_axes {rg.n_axes_present}. NAV ${pr.nav_usd:.0f}. "
        f"제약 {pr.constraints.verdict}."
    )
