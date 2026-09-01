"""run_organization — 애널리스트 크루 → [PM ↔ Risk 반려] → CIO (mock LLM). 시나리오 6.

DeepSeek 미사용 (ScriptedLLM). 반려 루프·PM 클램프·org_orders 검증.
"""

from __future__ import annotations

import json

import pytest

from aegisvest.agents.organization import run_organization
from aegisvest.diary.logger import load_entries
from aegisvest.schemas import PaperPortfolio, PipelineResult
from tests.test_agents.conftest import ScriptedLLM

_MACRO = json.dumps(
    {
        "regime": "BULL",
        "confidence": "high",
        "axis_conflicts": [],
        "risk_scenarios": ["금리"],
        "watch_items": [],
    }
)
_FUND = json.dumps({"notes": []})
_THEMATIC = json.dumps({"notes": []})
_NEWS = json.dumps({"weekly_summary": "위험선호.", "event_risks": []})
_RD = json.dumps(
    {
        "sleeve_stance": {
            "low": {"stance": "neutral", "reason": "x"},
            "mid": {"stance": "overweight", "reason": "성장"},
            "high": {"stance": "underweight", "reason": "밸류"},
        },
        "cross_risks": [],
        "excluded_tickers": [],
        "notes": "n",
    }
)
# PM: 풀 안 종목으로 mid 를 늘림 (RD overweight). ZZZ 는 풀 밖 (제거되어야).
_PM = json.dumps(
    {
        "category_weights": {"low": 0.40, "mid": 0.38, "high": 0.14, "cash": 0.08},
        "positions": [
            {"ticker": "L0", "category": "low", "weight": 0.05, "sector": "Healthcare"},
            {"ticker": "L1", "category": "low", "weight": 0.05, "sector": "Utilities"},
            {"ticker": "M0", "category": "mid", "weight": 0.05, "sector": "Technology"},
            {"ticker": "M1", "category": "mid", "weight": 0.05, "sector": "Technology"},
            {"ticker": "M2", "category": "mid", "weight": 0.05, "sector": "Industrials"},
            {"ticker": "ZZZ", "category": "mid", "weight": 0.05, "sector": "Technology"},
        ],
        "tilt_rationale": "mid overweight 하우스뷰 반영",
    }
)
_RISK_OK = json.dumps({"verdict": "APPROVED", "conditions": [], "concerns": []})
_RISK_REJECT = json.dumps(
    {"verdict": "REJECTED", "conditions": ["고위험 축소"], "concerns": ["집중도"]}
)
_CIO_OK = json.dumps(
    {"verdict": "APPROVED", "ic_memo": "승인.", "concerns": [], "hold_reason": None}
)


def _llm(risk: str = _RISK_OK, cio: str = _CIO_OK) -> ScriptedLLM:
    return ScriptedLLM(
        {
            "MacroBrief": _MACRO,
            "FundamentalNotes": _FUND,
            "ThematicNotes": _THEMATIC,
            "MarketNarrative": _NEWS,
            "ResearchView": _RD,
            "PMDraft": _PM,
            "RiskReview": risk,
            "CIODecision": cio,
        }
    )


def _pf() -> PaperPortfolio:
    return PaperPortfolio(cash_usd=1000.0)


def test_org_full_flow(pipeline_result: PipelineResult) -> None:
    out = run_organization(
        pipeline_result, portfolio=_pf(), prices={"L0": 100.0, "M0": 100.0}, llm=_llm()
    )
    assert out.cio.verdict == "APPROVED"
    assert out.risk_review is not None and out.risk_review.verdict == "APPROVED"
    assert out.risk_rounds == 1  # 반려 없음
    assert out.pm_draft is not None
    assert not out.rebalance_held


def test_pm_tilt_clamped_and_ordered(pipeline_result: PipelineResult) -> None:
    prices = {t: 100.0 for t in ("L0", "L1", "M0", "M1", "M2")}
    out = run_organization(pipeline_result, portfolio=_pf(), prices=prices, llm=_llm())
    tickers = {p.ticker for p in out.pm_draft.positions}
    assert "ZZZ" not in tickers  # 풀 밖 제거
    assert tickers <= {"L0", "L1", "M0", "M1", "M2"}
    # 카테고리는 이번 회차 결정론 배분 ±3%p, 단일종목 8% 이내
    for c in ("low", "mid", "high"):
        base = pipeline_result.draft.category_weights.get(c, 0.0)
        assert out.pm_draft.category_weights.get(c, 0.0) <= base + 0.03 + 1e-6
    assert all(p.weight <= 0.08 + 1e-6 for p in out.pm_draft.positions)
    assert out.org_orders  # 매수 주문 생성


def test_risk_reject_triggers_one_retry(pipeline_result: PipelineResult) -> None:
    out = run_organization(
        pipeline_result,
        portfolio=_pf(),
        prices={"L0": 100.0, "M0": 100.0},
        llm=_llm(risk=_RISK_REJECT),
    )
    assert out.risk_rounds == 2  # 1회 재시도
    assert out.rebalance_held is True  # 2회차도 REJECTED
    assert out.org_orders == []
    vet = [e for e in load_entries() if e.claim_type == "risk_veto"]
    assert vet and vet[0].decision["held"] is True


def test_diary_tags_include_macro_signals(make_pipeline_result_crisis: PipelineResult) -> None:
    """위기 매크로(fixture) → regime_call 태그에 crisis_shift + signal 자동 평가."""
    run_organization(
        make_pipeline_result_crisis, portfolio=_pf(), prices={"L0": 100.0, "M0": 100.0}, llm=_llm()
    )
    rc = next(e for e in load_entries() if e.claim_type == "regime_call")
    assert "regime:crisis" in rc.tags
    assert "action:crisis_shift" in rc.tags
    assert "rates_dir:hiking" in rc.tags
    assert "signal:credit_spread_widening" in rc.tags
    assert "signal:vix_term_backwardation" in rc.tags
    assert rc.data_snapshot["hy_oas_bp"] == 800.0  # macro 원자료가 snapshot 에 그대로


def test_allocation_tilt_logged_when_material(pipeline_result: PipelineResult) -> None:
    # 결정론 초안 mid 4% → PM 이 36% 로 대폭 틸트 (클램프되지만 여전히 material)
    run_organization(
        pipeline_result, portfolio=_pf(), prices={"L0": 100.0, "M0": 100.0}, llm=_llm()
    )
    tilts = [e for e in load_entries() if e.claim_type == "allocation_tilt"]
    assert tilts and tilts[0].decision["enforced"] is True
    assert tilts[0].shadow_link.startswith("state/shadow.json#")


@pytest.mark.llm
def test_live_deepseek_org(pipeline_result: PipelineResult) -> None:
    """실 DeepSeek (`pytest -m llm`). 계정 잔액 필요."""
    out = run_organization(
        pipeline_result, portfolio=_pf(), prices={"L0": 100.0, "M0": 100.0}, run_id="2026-09-01"
    )
    assert out.cio.verdict in {"APPROVED", "HOLD"}
    assert out.risk_review is not None
