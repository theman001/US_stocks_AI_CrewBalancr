"""diary/governance.py — 분기 거버넌스 CLI (§8). 합성 데이터."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegisvest.config import get_settings
from aegisvest.diary import governance
from aegisvest.diary.logger import load_entries, save_entries
from aegisvest.schemas import DiaryEntry


def _entry(
    eid: str, *, rag_status: str = "auto", claim_type: str = "allocation_tilt"
) -> DiaryEntry:
    return DiaryEntry(
        id=eid,
        run_id="2026-01-01",
        agent="PM",
        created_at="2026-01-01T00:00:00Z",
        claim_type=claim_type,
        claim="c",
        reasoning="r",
        horizon_weeks=12,
        status="reflected",
        rag_status=rag_status,
        situation_text="[상황] x",
        outcome={
            "verdict": "miss",
            "score": -1,
            "attribution": "high",
            "evaluated_at": "2026-03-26",
        },
        post_mortem={"lesson": "원래 교훈", "flags": ["missed_signal: 모호"]},
        lesson_card="원래 카드",
        lesson_vector_id="x1#lesson",
    )


def _diary_dir() -> Path:
    d = get_settings().state_dir / "diary"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_report_lists_pending_and_tags() -> None:
    save_entries([_entry("p1", rag_status="pending_review"), _entry("a1")])
    (_diary_dir() / "pending_tags.json").write_text(
        json.dumps({"event": ["new_thing"], "theme": []}), encoding="utf-8"
    )
    txt = governance.report_text()
    assert "[p1] allocation_tilt" in txt
    assert "원래 교훈" in txt
    assert "missed_signal: 모호" in txt
    assert "event: new_thing" in txt
    assert "[a1]" not in txt  # auto 는 큐에 없음


def test_approve_and_retire() -> None:
    save_entries([_entry("p1", rag_status="pending_review")])
    assert governance.approve("p1") is True
    assert load_entries()[0].rag_status == "approved"
    assert governance.retire("p1") is True
    assert load_entries()[0].rag_status == "retired"
    assert governance.approve("nope") is False


def test_edit_lesson_clears_vector_id() -> None:
    save_entries([_entry("p1", rag_status="pending_review")])
    governance.edit_lesson("p1", "새 교훈", lesson_card="새 카드")
    e = load_entries()[0]
    assert e.post_mortem is not None
    assert e.post_mortem["lesson"] == "새 교훈"
    assert e.post_mortem["flags"] == ["missed_signal: 모호"]  # 다른 키 보존
    assert e.lesson_card == "새 카드"
    assert e.lesson_vector_id is None  # 다음 rag 배치가 재임베딩


def test_acknowledge_tags_empties_file() -> None:
    path = _diary_dir() / "pending_tags.json"
    path.write_text(json.dumps({"event": ["x"]}), encoding="utf-8")
    governance.acknowledge_tags()
    assert json.loads(path.read_text(encoding="utf-8")) == {}


def test_recall_counts_feed_top_lessons() -> None:
    save_entries([_entry("L1"), _entry("L2")])
    log = _diary_dir() / "recall_log.jsonl"
    log.write_text(
        '{"at": "2026-04-01T00:00:00Z", "ids": ["L1", "L2"]}\n'
        '{"at": "2026-04-08T00:00:00Z", "ids": ["L1"]}\n',
        encoding="utf-8",
    )
    txt = governance.report_text()
    assert "2회 · [L1]" in txt
    assert "1회 · [L2]" in txt
    assert "base rate 0/2 hit" in txt  # 둘 다 miss


def test_run_cli_prints_report_when_no_action(capsys: pytest.CaptureFixture[str]) -> None:
    save_entries([_entry("p1", rag_status="pending_review")])
    governance.run_cli()
    out = capsys.readouterr().out
    assert "거버넌스 리포트" in out
