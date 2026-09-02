"""diary/reviewer.py — ⑨ Performance Reviewer 반성 배치 (mock LLM). TESTING 시나리오 8.

DeepSeek 미사용 (ScriptedLLM). RAG 게이트·하인드사이트 검증·태그 위생·토큰 절삭.
"""

from __future__ import annotations

import json

import pytest

from aegisvest.config import get_settings
from aegisvest.diary import logger as diary
from aegisvest.diary import reviewer
from aegisvest.diary.logger import load_entries, save_entries
from aegisvest.diary.reviewer import rag_status_for
from aegisvest.schemas import DiaryEntry
from tests.test_agents.conftest import ScriptedLLM

_GOOD = json.dumps(
    {
        "what_happened": "XYZ -18%, 제외로 손실 회피. HY OAS 355에서 470으로 상승",
        "missed_signal": "당시 스냅샷의 hy_oas_4w_change_bp +40 이 방어 강도에 반영 안 됨",
        "underestimated_because": "규제 헤드라인을 단발성으로 봄, 신용 스프레드 동반 상승 미연결",
        "what_would_change": (
            "hy_oas_4w_change_bp +25 이상 + 섹터 규제 헤드라인 동시 발생 시 해당 슬리브 -1노치"
        ),
        "root_cause": None,
        "lesson": "신용 스프레드 상승 추세와 섹터 규제가 겹치면 방어 틸트가 유효하다",
        "base_rate_note": "규제 공포 셋업 과거 3건 중 2건 hit",
        "lesson_card": "[HYspread상승·섹터규제] 방어 틸트 유효",
        "event_tags": ["regulation"],
        "theme_tags": ["ai_software"],
        "mistake_tag": "crowding_blindspot",
    }
)


def _llm(payload: str = _GOOD) -> ScriptedLLM:
    return ScriptedLLM({"ReviewerOutput": payload})


def _mk(claim_type: str, *, tags: list[str] | None = None) -> DiaryEntry:
    return DiaryEntry(
        id="t",
        run_id="2026-01-01",
        agent="a",
        created_at="2026-01-01T00:00:00Z",
        claim_type=claim_type,
        claim="c",
        reasoning="r",
        horizon_weeks=12,
        tags=tags or [],
    )


def _seed(
    claim_type: str = "exclusion",
    *,
    tags: list[str] | None = None,
    outcome: dict[str, object] | None = None,
    status: str = "evaluated",
) -> DiaryEntry:
    e = diary.log(
        run_id="2026-01-01",
        agent="Fund",
        claim_type=claim_type,
        claim="AI 규제 리스크로 XYZ 제외",
        reasoning="HY OAS 상승 추세 + 규제 헤드라인",
        data_snapshot={"hy_oas_bp": 470.0, "hy_oas_4w_change_bp": 40.0},
        decision={"excluded": ["XYZ"], "regime": "BEAR"},
        tags=tags or [],
    )
    assert isinstance(e, DiaryEntry)
    e.status = status
    e.outcome = outcome or {
        "evaluated_at": "2026-03-26",
        "verdict": "miss",
        "score": -1,
        "attribution": "high",
    }
    save_entries([e])
    return e


# ─────────────────────── RAG 진입 게이트 (§4.3) ───────────────────────


def test_rag_gate_pending_review_and_auto() -> None:
    assert rag_status_for(_mk("regime_call")) == "pending_review"
    assert rag_status_for(_mk("cio_override")) == "pending_review"
    assert rag_status_for(_mk("exclusion")) == "auto"
    assert rag_status_for(_mk("catalyst")) == "auto"
    assert rag_status_for(_mk("allocation_tilt", tags=["magnitude:large"])) == "pending_review"
    assert rag_status_for(_mk("allocation_tilt", tags=["magnitude:minor"])) == "auto"
    assert rag_status_for(_mk("exclusion", tags=["action:crisis_shift"])) == "pending_review"


# ─────────────────────── 반성 실행 ───────────────────────


def test_reflection_writes_post_mortem_without_touching_score() -> None:
    _seed("exclusion")
    counts = reviewer.run(llm=_llm())
    assert counts["reflected"] == 1
    assert counts["flagged"] == 0
    e = load_entries()[0]
    assert e.status == "reflected"
    assert e.rag_status == "auto"
    assert e.post_mortem is not None
    assert e.post_mortem["what_would_change"].startswith("hy_oas_4w_change_bp")
    assert e.lesson_card
    # 채점 결과 불변 — what_happened 만 append
    assert e.outcome is not None
    assert e.outcome["verdict"] == "miss"
    assert e.outcome["score"] == -1
    assert e.outcome["what_happened"].startswith("XYZ")
    assert "event:regulation" in e.tags
    assert "theme:ai_software" in e.tags
    assert "mistake:crowding_blindspot" in e.tags


def test_regime_call_reflection_is_pending_review() -> None:
    _seed("regime_call", outcome={"verdict": "miss", "score": -2, "attribution": "high"})
    reviewer.run(llm=_llm())
    e = load_entries()[0]
    assert e.status == "reflected"
    assert e.rag_status == "pending_review"  # 게이트 — 반성했어도 인간 확인 대기


def test_hit_not_needing_reflection_is_gated_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed("exclusion", outcome={"verdict": "hit", "score": 2, "attribution": "high"})
    monkeypatch.setattr(reviewer, "needs_reflection", lambda _e: False)
    counts = reviewer.run(llm=_llm())
    assert counts == {"gated": 1, "reflected": 0, "flagged": 0, "skipped_no_llm": 0, "errored": 0}
    e = load_entries()[0]
    assert e.status == "gated"  # 종결 — 반성 불필요
    assert e.rag_status == "auto"  # 게이트는 통과 (상황벡터 RAG 진입)
    assert e.post_mortem is None
    # 재실행해도 다시 처리하지 않음 (idempotent)
    assert reviewer.run(llm=_llm())["gated"] == 0


def test_no_llm_gates_but_skips_reflection() -> None:
    _seed("exclusion")
    counts = reviewer.run()  # llm 없음 + DEEPSEEK_API_KEY 없음 (conftest 격리)
    assert counts["skipped_no_llm"] == 1
    assert counts["reflected"] == 0
    e = load_entries()[0]
    assert e.status == "evaluated"
    assert e.rag_status == "auto"
    assert e.post_mortem is None


def test_vague_post_mortem_flagged_pending_review() -> None:
    _seed("exclusion")
    vague = json.loads(_GOOD)
    vague["missed_signal"] = "더 신중했어야 했다"
    vague["what_would_change"] = "다음엔 주의가 필요하다"
    reviewer.run(llm=_llm(json.dumps(vague)))
    e = load_entries()[0]
    assert e.status == "reflected"
    assert e.rag_status == "pending_review"
    assert e.post_mortem is not None
    assert e.post_mortem["flags"]


def test_lesson_card_truncated_to_token_budget() -> None:
    _seed("exclusion")
    long_card = json.loads(_GOOD)
    long_card["lesson_card"] = "매우 " * 60  # ~180자, 25토큰 초과
    reviewer.run(llm=_llm(json.dumps(long_card)))
    card = load_entries()[0].lesson_card
    assert card is not None
    assert len(card.split()) <= reviewer._LESSON_CARD_TOKENS


def test_new_semi_open_tag_recorded_to_pending() -> None:
    _seed("exclusion")
    novel = json.loads(_GOOD)
    novel["event_tags"] = ["some_new_event"]
    reviewer.run(llm=_llm(json.dumps(novel)))
    e = load_entries()[0]
    assert "event:some_new_event" in e.tags  # §7.4 — 작동하되
    pending = json.loads(
        (get_settings().state_dir / "diary" / "pending_tags.json").read_text(encoding="utf-8")
    )
    assert "some_new_event" in pending["event"]  # 플래그


def test_tag_overflow_sheds_signals_not_reflection_tags() -> None:
    full = [
        "regime:bear",
        "claim_type:exclusion",
        "sleeve:high",
        "action:exclusion",
        "magnitude:large",
        "signal:credit_spread_widening",
        "signal:breadth_deterioration",
        "signal:vix_spike",
    ]  # 이미 8개 (max_tags_per_entry), signal 3
    _seed("exclusion", tags=full)
    reviewer.run(
        llm=_llm()
    )  # _GOOD: event:regulation, theme:ai_software, mistake:crowding_blindspot
    tags = load_entries()[0].tags
    assert len(tags) == 8
    assert {"event:regulation", "theme:ai_software", "mistake:crowding_blindspot"} <= set(tags)
    assert not any(t.startswith("signal:") for t in tags)  # signal 부터 버림


@pytest.mark.llm
def test_live_deepseek_reviewer() -> None:
    """실 DeepSeek (`pytest -m llm`). 계정 잔액 필요."""
    _seed("exclusion")
    counts = reviewer.run()
    assert counts["reflected"] == 1
    e = load_entries()[0]
    assert e.status == "reflected"
    assert e.post_mortem and e.post_mortem["lesson"]


def test_already_reflected_entry_skipped() -> None:
    e = _seed("exclusion")
    e.status = "reflected"
    e.post_mortem = {"lesson": "old"}
    save_entries([e])
    counts = reviewer.run(llm=_llm())
    assert counts["gated"] == 0
    assert load_entries()[0].post_mortem == {"lesson": "old"}
