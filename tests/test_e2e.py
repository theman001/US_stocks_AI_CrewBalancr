"""E2E — 주간 전체 생애주기를 한 번에 태운다 (모듈 단위 테스트가 못 잡는 크로스모듈 배선).

실행: 실 `run_pipeline` (데이터 소스만 mock) + 실 `run_organization` (ScriptedLLM) +
실 일기 로깅 → `evaluate` → `reviewer` → `rag.backfill` → 2차 실행에서 회상 주입 확인.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from aegisvest import config, main, state
from aegisvest import pipeline as pl
from aegisvest.agents import crew as crew_mod
from aegisvest.agents import organization as org_mod
from aegisvest.diary import evaluate as ev
from aegisvest.diary import rag
from aegisvest.diary import reviewer as rv
from aegisvest.diary.logger import load_entries
from aegisvest.schemas import (
    MarketData,
    NavPoint,
    RegimeHistoryPoint,
    ScoredTicker,
    ScoringResult,
    ScreenedTicker,
    ScreenResult,
    ShadowState,
)
from aegisvest.tools import portfolio_math
from tests.fixtures.macro import macro
from tests.test_agents.conftest import ScriptedLLM

_UNIVERSE = [f"T{i:02d}" for i in range(30)]


# ─────────────────────── 데이터 소스 mock (실 파이프라인 로직은 그대로) ───────────────────────


def _screen(cat: str, universe: str = "combined", limit: int | None = None) -> ScreenResult:
    idx = {"LOW": (0, 12), "MID": (12, 22), "HIGH": (22, 30)}[cat.upper()]
    picks = _UNIVERSE[idx[0] : idx[1]]
    return ScreenResult(
        category=cat.upper(),
        passed=[ScreenedTicker(ticker=t, passed=True, checks={}) for t in picks],
        failed_count=0,
        evaluated_count=len(picks),
        errored=[],
        as_of="2026-09-01",
    )


def _score(cat: str, tickers: list[str], *_a: object, **_k: object) -> ScoringResult:
    return ScoringResult(
        category=cat.upper(),
        scores=[
            ScoredTicker(ticker=t, score=90.0 - i, rank=i + 1, subtier=None, component_scores={})
            for i, t in enumerate(tickers)
        ],
        errored=[],
        as_of="2026-09-01",
    )


def _md(ticker: str) -> MarketData:
    return MarketData(
        ticker=ticker,
        last_price=100.0,
        sma_50=100.0,
        sma_200=95.0,
        sma_50_prev=99.0,
        sma_200_prev=94.0,
        rsi_14=55.0,
        atr_14=3.0,
        beta_60m=1.0,
        adv_20d_usd=5e7,
        rs_vs_spx_6m=0.05,
        mom_12_1=0.1,
        pct_from_52w_high=-0.05,
        vol_20d_avg=1e6,
        vol_ratio_latest=1.1,
        as_of="2026-09-01",
    )


# ─────────────────────── ScriptedLLM canned 응답 (일기 항목 6종 유발) ───────────────────────

_RESP: dict[str, str] = {
    "MacroBrief": '{"regime": "BULL", "confidence": "high", "axis_conflicts": [],'
    ' "risk_scenarios": ["금리 재상승", "규제 헤드라인"], "watch_items": ["FOMC"]}',
    "FundamentalNotes": '{"notes": [{"ticker": "L1", "thesis_1line": "이익 피크아웃",'
    ' "quality_flags": ["일회성 이익"], "valuation_trap": true, "exclude_recommended": true}]}',
    "ThematicNotes": '{"notes": [{"ticker": "M1", "themes": ["ai_infra"], "catalyst": "실적 발표",'
    ' "catalyst_date": "2026-10-20", "crowding_flag": false, "momentum_durability": "high",'
    ' "theme_strength_adj": 0.1, "exclude_recommended": false}]}',
    "MarketNarrative": '{"weekly_summary": "위험선호 지속.",'
    ' "event_risks": [{"event": "CPI", "date": "2026-10-10", "affected_sleeve": "all",'
    ' "severity": "medium"}]}',
    "ResearchView": '{"sleeve_stance": {"low": {"stance": "neutral", "reason": "x"},'
    ' "mid": {"stance": "overweight", "reason": "성장 우위"},'
    ' "high": {"stance": "neutral", "reason": "y"}}, "cross_risks": [], "excluded_tickers": ["L1"],'
    ' "notes": "mid 비중 상향"}',
    "PMDraft": '{"category_weights": {"low": 0.05, "mid": 0.07, "high": 0.0, "cash": 0.88},'
    ' "positions": [{"ticker": "M0", "category": "mid", "weight": 0.04, "sector": "Technology"},'
    ' {"ticker": "M1", "category": "mid", "weight": 0.03, "sector": "Technology"}],'
    ' "tilt_rationale": "mid overweight 반영"}',
    "RiskReview": '{"verdict": "APPROVED", "conditions": [], "concerns": []}',
    "CIODecision": '{"verdict": "APPROVED", "ic_memo": "승인.", "concerns": [],'
    ' "hold_reason": null}',
    "ReviewerOutput": '{"what_happened": "규제 리스크 현실화, L1 -12% 회피",'
    ' "missed_signal": "스냅샷의 hy_oas_bp 400 이 방어에 반영 안 됨",'
    ' "underestimated_because": "규제 헤드라인을 단발성으로 봄",'
    ' "what_would_change": "hy_oas_bp 상승 + 규제 헤드라인 동시 시 해당 슬리브 -1노치",'
    ' "root_cause": null, "lesson": "신용 스프레드와 규제가 겹치면 방어 유효",'
    ' "base_rate_note": "규제 공포 3건 중 2건 hit", "lesson_card": "[HYspread·규제] 방어 유효",'
    ' "event_tags": ["regulation"], "theme_tags": ["ai_software"], "mistake_tag": "none"}',
}


def _frame(run_d: dt.date, end_price: float) -> pd.DataFrame:
    # 채점창 [run_id, evaluate_after] 안에 두 점이 들어와야 초과수익 채점이 의미를 가진다.
    idx = pd.to_datetime([run_d.isoformat(), (run_d + dt.timedelta(weeks=10)).isoformat()])
    return pd.DataFrame({"Close": [100.0, end_price]}, index=idx)


@pytest.fixture
def e2e(monkeypatch: pytest.MonkeyPatch) -> ScriptedLLM:
    scripted = ScriptedLLM(_RESP)
    # 파이프라인 데이터 소스
    monkeypatch.setattr(pl, "macro_data", lambda: macro(fed_funds_trend="hold"))
    monkeypatch.setattr(
        pl,
        "market_breadth",
        lambda ts: {
            "pct_above_200dma": 58.0,
            "pct_above_200dma_4w_change": 3.0,
            "n": 20,
            "as_of": "2026-09-01",
        },
    )
    monkeypatch.setattr(pl, "get_universe", lambda name="combined": list(_UNIVERSE))
    monkeypatch.setattr(pl, "screen", _screen)
    monkeypatch.setattr(pl, "score_category", _score)
    monkeypatch.setattr(pl, "market_data", _md)
    monkeypatch.setattr(portfolio_math, "market_data", _md)
    monkeypatch.setattr(portfolio_math, "_sectors", lambda ts: {t: "Technology" for t in ts})
    # main I/O
    monkeypatch.setattr(main, "usd_krw", lambda: 1400.0)
    monkeypatch.setattr(main, "market_data", _md)
    monkeypatch.setattr(main, "latest_close_date", lambda ttl: "2026-09-01")
    monkeypatch.setattr(main, "post", lambda *_a, **_k: True)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DRY_RUN", "false")
    config.get_settings.cache_clear()
    # 크루 LLM (분석가·PM·Risk·CIO·⑨ Reviewer 전부)
    monkeypatch.setattr(crew_mod, "get_llm", lambda *, temperature: scripted)
    # RAG 임베더 (bge-m3 다운로드 회피) — 배선 테스트라 벡터는 균일 (랭킹은 test_diary_rag 소관)
    monkeypatch.setattr(rag, "_embed", lambda texts: [[1.0, 0.1, 0.1] for _ in texts])
    monkeypatch.setattr(rag, "_MIN_CORPUS", 1)
    rag._client.cache_clear()  # 이전 테스트의 tmp chroma 클라이언트 폐기
    return scripted


def test_full_weekly_lifecycle(e2e: ScriptedLLM, monkeypatch: pytest.MonkeyPatch) -> None:
    # ─── Phase 1: 주간 실행 (실 파이프라인 + 실 크루 + 일기 로깅) ───
    res1 = main.run()
    assert res1.crew_ran is True
    assert res1.cio_verdict == "APPROVED"
    assert res1.contribution_usd > 0  # 첫 실행 → 적금
    assert res1.n_fills >= 1  # 결정론/조직 주문 체결

    shadow = state.load_model("shadow.json", ShadowState)
    assert shadow is not None and shadow.organization.positions  # 저장됨

    entries = load_entries()
    claim_types = {e.claim_type for e in entries}
    assert {"regime_call", "exclusion", "catalyst", "event_risk", "sleeve_stance"} <= claim_types
    rc = next(e for e in entries if e.claim_type == "regime_call")
    assert "regime:neutral" in rc.tags  # 결정론 레짐 (LLM 의 "BULL" 주장 아님 — Layer 0)
    assert "rates_dir:hold" in rc.tags
    assert rc.data_snapshot.get("hy_oas_bp") == 400.0  # macro 원자료가 스냅샷에 그대로

    # ─── Phase 2: 시간 경과 + 채점 (섀도 이력·레짐 이력 시드) ───
    sh = state.load_model("shadow.json", ShadowState)
    assert sh is not None
    run_d = dt.date.fromisoformat(res1.run_id)  # 벽시계 비의존 — 시드·채점일을 run_id 기준으로
    # sleeve_stance/allocation_tilt 채점창 = [run_id, run_id+12주]. 종료 NAV 를 그 안에 둔다.
    nav_date = (run_d + dt.timedelta(weeks=10)).isoformat()
    for pf, mult in ((sh.organization, 1.15), (sh.deterministic, 1.05)):  # org 가 아웃퍼폼
        end = pf.history[-1].nav_usd * mult
        pf.history.append(NavPoint(date=nav_date, nav_usd=end, nav_krw=end * 1400))
    state.save_model("shadow.json", sh)
    state.save_list(
        "regime_history.json",
        [
            RegimeHistoryPoint(date=(run_d + dt.timedelta(weeks=w)).isoformat(), total_score=0)
            for w in (2, 5, 8)
        ],
    )
    monkeypatch.setattr(
        ev,
        "history",
        lambda t, ttl: _frame(run_d, 80.0 if t == "L1" else 105.0),  # L1 하락, SPY 소폭 상승
    )

    due = max(e.evaluate_after[-1] for e in load_entries() if e.evaluate_after)
    counts = ev.run(today=due)  # 모든 horizon 도래
    assert counts["evaluated"] >= 3
    graded = [e for e in load_entries() if e.status == "evaluated"]
    assert any(e.claim_type == "regime_call" and e.outcome for e in graded)
    tilt = next((e for e in graded if e.claim_type == "sleeve_stance"), None)
    assert tilt is not None and (tilt.outcome or {})["verdict"] == "hit"  # org(+15%) > det(+5%)

    # ─── Phase 3: 반성 (⑨ Reviewer, ScriptedLLM) ───
    rcounts = rv.run(llm=e2e)
    assert rcounts["reflected"] >= 1
    reflected = [e for e in load_entries() if e.status == "reflected"]
    assert reflected and all(e.post_mortem and e.post_mortem["lesson"] for e in reflected)

    # ─── Phase 4: RAG 색인 ───
    icounts = rag.backfill()
    assert icounts["situations"] >= 1
    indexed = [e for e in load_entries() if e.situation_vector_id]
    assert len(indexed) >= 3
    assert any(e.lesson_vector_id for e in load_entries())  # 반성분은 lesson 벡터도

    # ─── Phase 5: 2차 주간 실행 — 회상이 판단 태스크에 주입되는지 ───
    seen: list[tuple[str, str]] = []
    real_make = crew_mod.make_task

    def spy(key: str, ctx: object, **kw: object) -> object:
        seen.append((key, f"{kw.get('recall', '')}{kw.get('extra_desc', '')}"))
        return real_make(key, ctx, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(crew_mod, "make_task", spy)
    monkeypatch.setattr(org_mod, "make_task", spy)
    res2 = main.run()
    assert res2.crew_ran

    injected = {k for k, txt in seen if "판단 일기" in txt}
    assert {"macro_brief", "research_view", "pm_draft"} <= injected  # ①⑤⑥ 에 주입
    assert "cio_decision" not in injected  # ⑧ 제외


def test_crew_failure_absorbed_by_deterministic(
    e2e: ScriptedLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    """크루가 던지면 결정론 파이프라인·모의투자는 계속 (main 이 흡수)."""

    def boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("crew down")

    monkeypatch.setattr(org_mod, "run_organization", boom)
    res = main.run()
    assert res.crew_ran is False  # 크루 실패
    assert res.n_fills >= 1  # 결정론 주문은 체결됨
    assert res.cio_verdict is None
    assert state.load_model("shadow.json", ShadowState) is not None


def test_dry_run_full_chain_no_persistence(
    e2e: ScriptedLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DRY_RUN", "true")
    config.get_settings.cache_clear()
    res = main.run()
    assert res.dry_run is True
    assert res.crew_ran is True  # 크루는 돌지만
    assert state.load_model("shadow.json", ShadowState) is None  # shadow 미저장
    assert state.load_list("regime_history.json", RegimeHistoryPoint) == []  # regime 미저장
    assert load_entries() == []  # 엄격 계약 — 일기·RAG 도 미기록 (persist_diary=False)
