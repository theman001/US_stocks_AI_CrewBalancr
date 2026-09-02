"""판단 일기 거버넌스 — 분기 1회 인간 검토. report/phase-4 §8.

`python -m aegisvest.diary review` (인자 없음) → 리포트 출력:
- `pending_review` 큐 (대형 틸트·위기·레짐 콜·모호 플래그) → 승인/은퇴/수정
- `state/diary/pending_tags.json` 신규 SEMI-OPEN 태그
- 가장 많이 회상된 교훈 top-N + claim_type 별 base rate (`state/diary/recall_log.jsonl`)

액션은 플래그로: `--approve <id>` / `--retire <id>` / `--edit <id> --lesson "..."` /
`--ack-tags`. 여러 건은 반복 호출. RAG 재색인은 다음 `python -m aegisvest.diary.rag` 배치.

교훈 충돌 탐지(§8 "고신뢰 교훈과 충돌")는 4-6 (임베딩 유사도 기반) — 지금은 `post_mortem.flags`
표시만.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

from aegisvest.config import get_settings
from aegisvest.diary.logger import diary_lock, load_entries, save_entries
from aegisvest.schemas import DiaryEntry

_log = logging.getLogger("aegisvest.diary.governance")
_TOP_LESSONS = 20


def pending_review_queue(entries: list[DiaryEntry]) -> list[DiaryEntry]:
    return [e for e in entries if e.rag_status == "pending_review"]


def _pending_tags() -> dict[str, list[str]]:
    path = get_settings().state_dir / "diary" / "pending_tags.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _recall_counts() -> Counter[str]:
    path = get_settings().state_dir / "diary" / "recall_log.jsonl"
    counts: Counter[str] = Counter()
    if not path.exists():
        return counts
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            counts.update(str(x) for x in row.get("ids", []))
    return counts


def _base_rate(entries: list[DiaryEntry], claim_type: str) -> str:
    graded = [
        (e.outcome or {}).get("verdict")
        for e in entries
        if e.claim_type == claim_type and e.status in {"evaluated", "reflected", "gated"}
    ]
    graded = [v for v in graded if v]
    if not graded:
        return "n/a"
    hits = sum(1 for v in graded if v == "hit")
    return f"{hits}/{len(graded)} hit"


def report_text() -> str:
    entries = load_entries()
    by_id = {e.id: e for e in entries}
    lines: list[str] = ["# 판단 일기 거버넌스 리포트", ""]

    queue = pending_review_queue(entries)
    lines.append(f"## pending_review 큐 ({len(queue)}건)")
    for e in queue:
        pm = e.post_mortem or {}
        flags = pm.get("flags")
        lines.append(f"- [{e.id}] {e.claim_type} · {(e.outcome or {}).get('verdict', '?')}")
        lines.append(f"    교훈: {pm.get('lesson') or '(없음)'}")
        if flags:
            lines.append(f"    ⚠️ 플래그: {flags}")
    if not queue:
        lines.append("- (없음)")

    tags = _pending_tags()
    total_new = sum(len(v) for v in tags.values())
    lines += ["", f"## 신규 SEMI-OPEN 태그 ({total_new}건)"]
    for dim, vals in tags.items():
        if vals:
            lines.append(f"- {dim}: {', '.join(vals)}")
    if not total_new:
        lines.append("- (없음)")

    counts = _recall_counts()
    lines += ["", f"## 가장 많이 회상된 교훈 top {_TOP_LESSONS}"]
    for eid, n in counts.most_common(_TOP_LESSONS):
        entry = by_id.get(eid)
        if entry is None:
            continue
        pm = entry.post_mortem or {}
        card = entry.lesson_card or pm.get("lesson") or entry.claim
        lines.append(
            f"- {n}회 · [{eid}] {card}  (base rate {_base_rate(entries, entry.claim_type)})"
        )
    if not counts:
        lines.append("- (회상 로그 없음)")

    return "\n".join(lines)


def _mutate(entry_id: str, fn: Any) -> bool:
    with diary_lock():
        entries = load_entries()
        for e in entries:
            if e.id == entry_id:
                fn(e)
                save_entries(entries)
                return True
    _log.warning("항목 없음: %s", entry_id)
    return False


def approve(entry_id: str) -> bool:
    """pending_review → approved (다음 rag 배치가 색인)."""
    return _mutate(entry_id, lambda e: setattr(e, "rag_status", "approved"))


def retire(entry_id: str) -> bool:
    """검색 제외 (이력 보존). 다음 rag 배치가 벡터 삭제."""
    return _mutate(entry_id, lambda e: setattr(e, "rag_status", "retired"))


def edit_lesson(entry_id: str, lesson: str, *, lesson_card: str | None = None) -> bool:
    """교훈 문구 수정 → lesson_vector_id 초기화 (다음 배치가 재임베딩)."""

    def _apply(e: DiaryEntry) -> None:
        pm = dict(e.post_mortem or {})
        pm["lesson"] = lesson
        e.post_mortem = pm
        if lesson_card is not None:
            e.lesson_card = lesson_card
        e.lesson_vector_id = None

    return _mutate(entry_id, _apply)


def acknowledge_tags() -> None:
    """pending_tags.json 을 비운다 (검토 완료 표시 — taxonomy 반영은 수동)."""
    path = get_settings().state_dir / "diary" / "pending_tags.json"
    try:
        if path.exists():
            path.write_text("{}\n", encoding="utf-8")
    except OSError as e:
        _log.warning("pending_tags 초기화 실패: %s", e)


def run_cli(
    *,
    approve_id: str | None = None,
    retire_id: str | None = None,
    edit_id: str | None = None,
    lesson: str | None = None,
    lesson_card: str | None = None,
    ack_tags: bool = False,
) -> None:
    acted = False
    if approve_id:
        acted = approve(approve_id) or acted
        _log.info("approve %s", approve_id)
    if retire_id:
        acted = retire(retire_id) or acted
        _log.info("retire %s", retire_id)
    if edit_id:
        if not lesson:
            raise SystemExit("--edit 에는 --lesson 이 필요합니다")
        acted = edit_lesson(edit_id, lesson, lesson_card=lesson_card) or acted
        _log.info("edit %s", edit_id)
    if ack_tags:
        acknowledge_tags()
        acted = True
        _log.info("pending_tags 초기화")
    if not acted:
        print(report_text())  # CLI 출력
