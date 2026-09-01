"""run_crew — 스크립트 LLM 통합 (TESTING 시나리오 6). DeepSeek 미사용."""

from __future__ import annotations

import json

import pytest

from aegisvest.agents.crew import build_inputs, run_crew
from aegisvest.diary.logger import load_entries
from aegisvest.schemas import PipelineResult
from tests.test_agents.conftest import ScriptedLLM, make_pipeline_result

_MACRO = json.dumps(
    {
        "regime": "BULL",
        "confidence": "high",
        "axis_conflicts": ["변동성 안정 vs 폭 보통"],
        "risk_scenarios": ["금리 재상승", "실적 실망"],
        "watch_items": ["HY OAS", "고용"],
    }
)
_ANALYST = json.dumps(
    {
        "low_mid_notes": [
            {
                "ticker": "L0",
                "thesis_1line": "배당 성장 견고",
                "quality_flags": [],
                "exclude_recommended": False,
            }
        ],
        "high_notes": [],
        "weekly_narrative": "위험선호 유지. 기술주 주도.",
        "event_risks": ["FOMC"],
        "excluded_tickers": [],
    }
)
_CIO_APPROVE = json.dumps(
    {
        "verdict": "APPROVED",
        "ic_memo": "프로세스 신뢰. 이견 없음.",
        "concerns": [],
        "hold_reason": None,
    }
)
_CIO_HOLD = json.dumps(
    {
        "verdict": "HOLD",
        "ic_memo": "CRISIS 레짐. 이번 주 리밸런싱 보류, 현 포트 유지.",
        "concerns": ["신용 스프레드 급확대"],
        "hold_reason": "CRISIS 레짐 진입",
    }
)


def _llm(cio: str = _CIO_APPROVE) -> ScriptedLLM:
    return ScriptedLLM({"MacroBrief": _MACRO, "AnalystView": _ANALYST, "CIODecision": cio})


def test_build_inputs_all_placeholders(pipeline_result: PipelineResult) -> None:
    inp = build_inputs(pipeline_result)
    for key in (
        "regime_json",
        "allocation_json",
        "candidates_json",
        "draft_json",
        "constraints_json",
    ):
        assert inp.get(key)
    # 배분은 퍼센트로 노출 (에이전트가 %로 인용)
    assert "40.0" in inp["allocation_json"]


def test_crew_returns_valid_schema(pipeline_result: PipelineResult) -> None:
    out = run_crew(pipeline_result, llm=_llm())
    assert out.macro_brief.regime == "BULL"
    assert out.analyst_view.weekly_narrative
    assert out.cio.verdict == "APPROVED"
    assert out.llm_used is False


def test_cio_hold_on_crisis() -> None:
    pr = make_pipeline_result(crisis=True)
    out = run_crew(pr, llm=_llm(cio=_CIO_HOLD))
    assert out.cio.verdict == "HOLD"
    assert out.cio.hold_reason
    # HOLD 는 일기에 cio_override 로 기록
    ids = [e.claim_type for e in load_entries()]
    assert "cio_override" in ids


def test_diary_logged_regime_call(pipeline_result: PipelineResult) -> None:
    run_crew(pipeline_result, llm=_llm())
    entries = load_entries()
    kinds = {e.claim_type for e in entries}
    assert "regime_call" in kinds
    rc = next(e for e in entries if e.claim_type == "regime_call")
    assert rc.evaluate_after and len(rc.evaluate_after) == 2  # 4주 + 12주
    assert rc.status == "open"
    assert "regime:bull" in rc.tags


@pytest.mark.llm
def test_live_deepseek_crew(pipeline_result: PipelineResult) -> None:
    """실 DeepSeek 크루 (수동: `uv run pytest -m llm`). 계정 잔액 필요."""
    out = run_crew(pipeline_result, run_id="2026-09-01")
    assert out.cio.verdict in {"APPROVED", "HOLD"}
    assert out.macro_brief.regime
    assert out.llm_used is True


def test_analyst_exclusion_logged_when_recommended(pipeline_result: PipelineResult) -> None:
    analyst_excl = json.dumps(
        {
            "low_mid_notes": [],
            "high_notes": [],
            "weekly_narrative": "L0 회계 이슈 제기.",
            "event_risks": [],
            "excluded_tickers": ["L0"],
        }
    )
    llm = ScriptedLLM(
        {"MacroBrief": _MACRO, "AnalystView": analyst_excl, "CIODecision": _CIO_APPROVE}
    )
    run_crew(pipeline_result, llm=llm)
    excl = [e for e in load_entries() if e.claim_type == "exclusion"]
    assert excl and excl[0].decision["enforced"] is False  # 3a-9: 권고만
