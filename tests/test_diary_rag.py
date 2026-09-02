"""diary/rag.py — bge-m3 이중 벡터 저장 (§5). 임베더는 mock, ChromaDB 는 tmp 실제.

TESTING 시나리오 8. 가중치(~2.3GB) 다운로드 회피 위해 `_embed` monkeypatch.
"""

from __future__ import annotations

import re

import pytest

from aegisvest.diary import rag
from aegisvest.diary.logger import load_entries, save_entries
from aegisvest.schemas import DiaryEntry


@pytest.fixture(autouse=True)
def _mock_embed(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """`~c~` 마커 → 쿼리([1,0]) 대비 코사인 c 인 2D 단위벡터. 마커 없으면 [1,0] (쿼리)."""
    calls: list[list[str]] = []

    def fake(texts: list[str]) -> list[list[float]]:
        calls.append(list(texts))
        out: list[list[float]] = []
        for t in texts:
            m = re.search(r"~([0-9.]+)~", t)
            c = min(max(float(m.group(1)) if m else 1.0, 0.0), 1.0)
            out.append([c, (1.0 - c * c) ** 0.5])
        return out

    monkeypatch.setattr(rag, "_embed", fake)
    monkeypatch.setattr(rag, "_MIN_CORPUS", 1)  # 임계는 전용 테스트에서 검증
    rag._client.cache_clear()
    return calls


def _entry(
    eid: str,
    *,
    status: str = "reflected",
    rag_status: str = "auto",
    with_lesson: bool = True,
    tags: list[str] | None = None,
    situation: str | None = None,
    verdict: str = "hit",
    score: int = 1,
    attribution: str = "high",
    created_at: str = "2026-01-01T00:00:00Z",
) -> DiaryEntry:
    return DiaryEntry(
        id=eid,
        run_id="2026-01-01",
        agent="Macro",
        created_at=created_at,
        claim_type="regime_call",
        claim="c",
        reasoning="r",
        horizon_weeks=12,
        situation_text=situation or f"[상황] {eid} 레짐 NEUTRAL HY OAS 355",
        status=status,
        rag_status=rag_status,
        tags=tags or ["regime:neutral", "claim_type:regime_call"],
        outcome={
            "verdict": verdict,
            "score": score,
            "attribution": attribution,
            "evaluated_at": "2026-03-26",
        },
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


# ─────────────────────── 회상 (recall, §6.3·§6.4) ───────────────────────


def _index(*entries: DiaryEntry) -> None:
    save_entries(list(entries))
    rag.backfill()


def test_recall_empty_on_cold_start() -> None:
    assert rag.DiaryRAG().recall("현재 상황", ["regime:neutral"]) == []


def test_recall_skips_below_min_corpus(
    monkeypatch: pytest.MonkeyPatch, _mock_embed: list[list[str]]
) -> None:
    monkeypatch.setattr(rag, "_MIN_CORPUS", 5)
    _index(*(_entry(f"e{i}", situation=f"[상황] e{i} ~0.9~", with_lesson=False) for i in range(3)))
    _mock_embed.clear()
    assert rag.DiaryRAG().recall("현재", ["regime:neutral"]) == []
    assert _mock_embed == []  # bge-m3 임베딩 자체를 안 함 (모델 로드 회피)


def test_recall_returns_above_floor_only() -> None:
    _index(
        _entry("near", situation="[상황] near ~0.90~", with_lesson=False),
        _entry("far", situation="[상황] far ~0.40~", with_lesson=False),
    )
    got = rag.DiaryRAG().recall("현재 상황", ["regime:neutral", "claim_type:regime_call"])
    ids = {c.entry_id for c in got}
    assert "near" in ids
    assert "far" not in ids  # 0.40 < similarity_floor 0.55


def test_recall_attribution_low_needs_higher_cosine() -> None:
    _index(
        _entry("lo58", situation="[상황] lo58 ~0.58~", attribution="low", with_lesson=False),
        _entry("lo65", situation="[상황] lo65 ~0.65~", attribution="low", with_lesson=False),
    )
    ids = {c.entry_id for c in rag.DiaryRAG().recall("현재", ["regime:neutral"])}
    assert ids == {"lo65"}  # 0.58 < 0.62 게이트, 0.65 통과


def test_recall_forces_crisis_diversity() -> None:
    ents = [_entry(f"n{i}", situation=f"[상황] n{i} ~0.88~", with_lesson=False) for i in range(4)]
    ents.append(
        _entry(
            "crisis1",
            situation="[상황] crisis1 ~0.60~",
            tags=["regime:crisis", "claim_type:regime_call"],
            score=-2,
            verdict="miss",
            with_lesson=False,
        )
    )
    _index(*ents)
    got = rag.DiaryRAG().recall("현재", ["regime:neutral"], k=4)
    assert "crisis1" in {c.entry_id for c in got}  # |score|>=2 위기 항목 강제 편입
    assert len(got) == 4


def test_format_recall_mid_summary_then_cards() -> None:
    assert rag.format_recall([]) == ""
    cases = [
        rag.RecalledCase(
            entry_id="a",
            kind="situation",
            cosine=0.82,
            rank=0.7,
            verdict="hit",
            score=1,
            regime="neutral",
            attribution="high",
            month="2026-10",
            tags=["signal:credit_spread_widening", "event:regulation"],
            text="레짐 NEUTRAL, HY OAS 355(+12bp/4주). PM 고위험 방어 틸트, SMCI 제외",
        ),
        rag.RecalledCase(
            entry_id="b",
            kind="lesson",
            cosine=0.61,
            rank=0.5,
            verdict="miss",
            score=-1,
            regime="neutral",
            attribution="high",
            month="2025-07",
            tags=["signal:vix_spike", "sleeve:high"],
            text="단발 VIX 스파이크 컷 → V자 반등 -4%p. 콘탱고 유지 시 컷 아님",
        ),
    ]
    md = rag.format_recall(cases)
    assert "유사 사례" in md
    assert "[2026-10 · hit +1 · 유사도 0.82]" in md  # top-1 중간요약
    assert "· [2025-07 miss-1 |" in md  # 나머지 카드
    assert "맹신 금지" in md


def test_build_query_deterministic_tags_and_text() -> None:
    snap = {"hy_oas_bp": 355.0, "hy_oas_4w_change_bp": 15.0, "vix": 17.0}
    text, tags = rag.build_query(
        regime="NEUTRAL", snapshot=snap, considering="고위험 방어 틸트 검토"
    )
    assert "HY OAS 355" in text
    assert "고위험 방어 틸트 검토" in text
    assert "regime:neutral" in tags
    assert "signal:credit_spread_widening" in tags  # hy_oas_4w_change_bp 15 >= 10
    assert not any(t.startswith(("claim_type:", "sleeve:")) for t in tags)


def test_recall_log_stays_bounded() -> None:
    case = rag.RecalledCase(
        entry_id="x",
        kind="situation",
        cosine=0.9,
        rank=0.9,
        verdict="hit",
        score=1,
        regime="neutral",
        attribution="high",
        month="2026-09",
        tags=[],
        text="t",
    )
    for _ in range(rag._RECALL_LOG_MAX + 40):
        rag._log_recall([case])
    path = rag.get_settings().state_dir / "diary" / "recall_log.jsonl"
    assert len(path.read_text(encoding="utf-8").splitlines()) == rag._RECALL_LOG_MAX


def test_structural_scoring() -> None:
    # {claim_type,sleeve,regime} 완전 일치 → 0.5, {signal,...} Jaccard 1.0 → 0.5 => 1.0
    q = ["regime:neutral", "claim_type:regime_call", "sleeve:high", "signal:vix_spike"]
    assert rag._structural(q, q) == 1.0
    assert rag._structural(["regime:bull"], ["regime:bear"]) == 0.0
