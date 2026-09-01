"""diary/rag.py — bge-m3 이중 벡터 저장 (§5). 임베더는 mock, ChromaDB 는 tmp 실제.

TESTING 시나리오 8. 가중치(~2.3GB) 다운로드 회피 위해 `_embed` monkeypatch.
"""

from __future__ import annotations

import pytest

from aegisvest.diary import rag
from aegisvest.diary.logger import load_entries, save_entries
from aegisvest.schemas import DiaryEntry


@pytest.fixture(autouse=True)
def _mock_embed(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake(texts: list[str]) -> list[list[float]]:
        calls.append(list(texts))
        return [[float(len(t) % 5), 1.0, 0.0, 0.25] for t in texts]

    monkeypatch.setattr(rag, "_embed", fake)
    rag._client.cache_clear()
    return calls


def _entry(
    eid: str,
    *,
    status: str = "reflected",
    rag_status: str = "auto",
    with_lesson: bool = True,
    tags: list[str] | None = None,
) -> DiaryEntry:
    return DiaryEntry(
        id=eid,
        run_id="2026-01-01",
        agent="Macro",
        created_at="2026-01-01T00:00:00Z",
        claim_type="regime_call",
        claim="c",
        reasoning="r",
        horizon_weeks=12,
        situation_text=f"[상황] {eid} 레짐 NEUTRAL HY OAS 355",
        status=status,
        rag_status=rag_status,
        tags=tags or ["regime:neutral", "claim_type:regime_call"],
        outcome={"verdict": "hit", "score": 1, "attribution": "high", "evaluated_at": "2026-03-26"},
        post_mortem=(
            {"lesson": "신용 스프레드와 규제가 겹치면 방어 유효"} if with_lesson else None
        ),
        lesson_card="[HYspread·규제] 방어 유효" if with_lesson else None,
    )


def test_backfill_indexes_situation_and_lesson(_mock_embed: list[list[str]]) -> None:
    save_entries([_entry("e1")])
    counts = rag.backfill()
    assert counts == {"situations": 1, "lessons": 1, "retired": 0}
    e = load_entries()[0]
    assert e.situation_vector_id == "e1"
    assert e.lesson_vector_id == "e1#lesson"
    sit, les = rag.collections()
    assert sit.count() == 1
    assert les.count() == 1


def test_gated_entry_gets_situation_only() -> None:
    save_entries([_entry("g1", status="gated", with_lesson=False)])
    counts = rag.backfill()
    assert counts["situations"] == 1
    assert counts["lessons"] == 0
    e = load_entries()[0]
    assert e.situation_vector_id == "g1"
    assert e.lesson_vector_id is None


def test_pending_review_not_indexed() -> None:
    save_entries([_entry("p1", rag_status="pending_review")])
    counts = rag.backfill()
    assert counts == {"situations": 0, "lessons": 0, "retired": 0}
    assert load_entries()[0].situation_vector_id is None


def test_backfill_is_idempotent(_mock_embed: list[list[str]]) -> None:
    save_entries([_entry("e1")])
    rag.backfill()
    _mock_embed.clear()
    counts = rag.backfill()
    assert counts == {"situations": 0, "lessons": 0, "retired": 0}
    assert _mock_embed == []  # 재임베딩 없음
    assert rag.collections()[0].count() == 1


def test_retired_entry_is_purged() -> None:
    save_entries([_entry("e1")])
    rag.backfill()
    e = load_entries()[0]
    e.rag_status = "retired"
    save_entries([e])
    counts = rag.backfill()
    assert counts["retired"] == 1
    e2 = load_entries()[0]
    assert e2.situation_vector_id is None
    assert e2.lesson_vector_id is None
    sit, les = rag.collections()
    assert sit.count() == 0
    assert les.count() == 0


def test_embed_called_once_per_batch(_mock_embed: list[list[str]]) -> None:
    save_entries([_entry("e1"), _entry("e2"), _entry("e3", with_lesson=False)])
    rag.backfill()
    # situation 배치 1회 (3건) + lesson 배치 1회 (2건)
    assert [len(c) for c in _mock_embed] == [3, 2]


def test_lesson_text_requires_post_mortem_lesson() -> None:
    assert rag.lesson_text(_entry("x", with_lesson=False)) == ""
    txt = rag.lesson_text(_entry("x", tags=["regime:neutral", "event:regulation"]))
    assert "방어 유효" in txt
    assert "event regulation" in txt
