"""run_crew — 스크립트 LLM 통합 (TESTING 시나리오 6). DeepSeek 미사용.

3b-1: ① Macro + ②③④ 애널리스트(async) → ⑤ Research Director → ⑧ CIO.
"""

from __future__ import annotations

import json

import pytest

from aegisvest.agents.crew import build_inputs, run_crew
from aegisvest.diary.logger import load_entries
from aegisvest.schemas import PipelineResult
from tests.test_agents.conftest import ScriptedLLM

_MACRO = json.dumps(
    {
        "regime": "BULL",
        "confidence": "high",
        "axis_conflicts": ["변동성 안정 vs 폭 보통"],
        "risk_scenarios": ["금리 재상승", "실적 실망"],
        "watch_items": ["HY OAS"],
    }
)
_FUND = json.dumps(
    {
        "notes": [
            {
                "ticker": "L0",
                "thesis_1line": "배당 성장 견고",
                "quality_flags": [],
                "valuation_trap": False,
                "exclude_recommended": False,
            }
        ]
    }
)
_THEMATIC = json.dumps({"notes": []})
_NEWS = json.dumps(
    {"weekly_summary": "위험선호 유지.", "event_risks": [{"event": "FOMC", "severity": "medium"}]}
)
_RD = json.dumps(
    {
        "sleeve_stance": {
            "low": {"stance": "neutral", "reason": "안정"},
            "mid": {"stance": "overweight", "reason": "성장"},
            "high": {"stance": "underweight", "reason": "밸류 부담"},
        },
        "cross_risks": ["기술주 집중"],
        "excluded_tickers": [],
        "notes": "중립~약공격",
    }
)
_CIO_APPROVE = json.dumps(
    {"verdict": "APPROVED", "ic_memo": "프로세스 신뢰.", "concerns": [], "hold_reason": None}
)
_CIO_HOLD = json.dumps(
    {
        "verdict": "HOLD",
        "ic_memo": "CRISIS 레짐. 리밸런싱 보류.",
        "concerns": ["신용 스프레드"],
        "hold_reason": "CRISIS 레짐 진입",
    }
)


def _llm(cio: str = _CIO_APPROVE, fund: str = _FUND, thematic: str = _THEMATIC) -> ScriptedLLM:
    return ScriptedLLM(
        {
            "MacroBrief": _MACRO,
            "FundamentalNotes": fund,
            "ThematicNotes": thematic,
            "MarketNarrative": _NEWS,
            "ResearchView": _RD,
            "CIODecision": cio,
        }
    )


def test_build_inputs_all_placeholders(pipeline_result: PipelineResult) -> None:
    inp = build_inputs(pipeline_result)
    for key in (
        "regime_json",
        "allocation_json",
        "low_mid_candidates_json",
        "high_candidates_json",
        "draft_json",
        "constraints_json",
    ):
        assert inp.get(key)
    assert "40.0" in inp["allocation_json"]


def test_crew_returns_all_six_outputs(pipeline_result: PipelineResult) -> None:
    out = run_crew(pipeline_result, llm=_llm())
    assert out.macro_brief.regime == "BULL"
    assert out.fundamental_notes.notes[0].ticker == "L0"
    assert out.market_narrative.event_risks[0].event == "FOMC"
    assert out.research_view.sleeve_stance["mid"].stance == "overweight"
    assert out.cio.verdict == "APPROVED"
    assert out.llm_used is False


def test_cio_hold_on_crisis(make_pipeline_result_crisis: PipelineResult) -> None:
    out = run_crew(make_pipeline_result_crisis, llm=_llm(cio=_CIO_HOLD))
    assert out.cio.verdict == "HOLD"
    assert "cio_override" in {e.claim_type for e in load_entries()}


def test_diary_regime_call_and_sleeve_stance(pipeline_result: PipelineResult) -> None:
    run_crew(pipeline_result, llm=_llm())
    kinds = {e.claim_type for e in load_entries()}
    assert "regime_call" in kinds
    assert "sleeve_stance" in kinds  # RD 하우스뷰
    assert "event_risk" in kinds  # News 이벤트
    rc = next(e for e in load_entries() if e.claim_type == "regime_call")
    assert len(rc.evaluate_after) == 2 and rc.status == "open"


def test_fundamental_exclusion_logged(pipeline_result: PipelineResult) -> None:
    fund_excl = json.dumps(
        {
            "notes": [
                {
                    "ticker": "L0",
                    "thesis_1line": "회계 이슈",
                    "quality_flags": ["회계"],
                    "valuation_trap": True,
                    "exclude_recommended": True,
                }
            ]
        }
    )
    run_crew(pipeline_result, llm=_llm(fund=fund_excl))
    excl = [e for e in load_entries() if e.claim_type == "exclusion"]
    assert excl and excl[0].decision["enforced"] is False


def test_thematic_catalyst_logged(pipeline_result: PipelineResult) -> None:
    thematic = json.dumps(
        {
            "notes": [
                {
                    "ticker": "H0",
                    "themes": ["AI"],
                    "catalyst": "실적 발표",
                    "catalyst_date": "2026-10-20",
                    "crowding_flag": True,
                    "momentum_durability": "med",
                    "theme_strength_adj": -0.1,
                    "exclude_recommended": False,
                }
            ]
        }
    )
    run_crew(pipeline_result, llm=_llm(thematic=thematic))
    cat = [e for e in load_entries() if e.claim_type == "catalyst"]
    assert cat and "sleeve:high" in cat[0].tags


@pytest.mark.llm
def test_live_deepseek_crew(pipeline_result: PipelineResult) -> None:
    """실 DeepSeek 크루 (수동: `uv run pytest -m llm`). 계정 잔액 필요."""
    out = run_crew(pipeline_result, run_id="2026-09-01")
    assert out.cio.verdict in {"APPROVED", "HOLD"}
    assert out.research_view.sleeve_stance
    assert out.llm_used is True
