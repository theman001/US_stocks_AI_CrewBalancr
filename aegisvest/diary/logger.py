"""판단 일기 로거 — state/diary/entries.jsonl 에 한 줄씩 append. report/phase-4 §2.3.

기록만 한다 (채점·벡터화·RAG 는 Phase 4). 예외 raise 안 함 (크루 콜백에서 호출).
"""

from __future__ import annotations

import datetime as dt
import fcntl
import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from aegisvest.config import get_settings
from aegisvest.diary.schema import (
    CLAIM_TYPES,
    default_horizon_weeks,
    derive_tags,
    entry_id,
    evaluate_dates,
)
from aegisvest.schemas import DiaryEntry, ToolError
from aegisvest.tools._io import _write_atomic

_FILE = "diary/entries.jsonl"
_log = logging.getLogger("aegisvest.diary")


def _path() -> Path:
    d = get_settings().state_dir / "diary"
    d.mkdir(parents=True, exist_ok=True)
    return d / "entries.jsonl"


@contextmanager
def diary_lock() -> Iterator[None]:
    """일기 read-modify-write 직렬화 (fcntl.flock). 호출자가 load_entries()..save_entries()
    전체를 감싸고, log() 의 append 도 이 락을 짧게 잡는다.

    ponytail: 단일 호스트 파일락 — 위기 크루가 주간 배치·`diary review` CLI 와 겹칠 때
    entries.jsonl 전체 rewrite 가 append 를 삼키는 것을 막는다. 크로스 호스트는 해당 없음
    (OMV 단일 스택). 배치 중에는 크루 콜백의 log() 가 잠깐 블록될 수 있음 (배치는 오프타임).
    """
    lock = _path().with_name(".lock")
    with lock.open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def log(
    *,
    run_id: str,
    agent: str,
    claim_type: str,
    claim: str,
    reasoning: str,
    data_snapshot: dict[str, float | int | str | None],
    decision: dict[str, object],
    situation_text: str = "",
    horizon_weeks: int | None = None,
    supporting_refs: Sequence[str] = (),
    tags: Sequence[str] | None = None,
    shadow_link: str | None = None,
) -> DiaryEntry | ToolError:
    """일기 항목 하나 기록. `run_id` = YYYY-MM-DD (또는 접두)."""
    if claim_type not in CLAIM_TYPES:
        return ToolError(error=f"미등록 claim_type: {claim_type}", field="claim_type")
    try:
        run_date = dt.date.fromisoformat(run_id[:10])
    except ValueError:
        return ToolError(error=f"run_id 에서 날짜 파싱 실패: {run_id}", field="run_id")

    hw = horizon_weeks if horizon_weeks is not None else default_horizon_weeks(claim_type)
    entry = DiaryEntry(
        id=entry_id(run_id, agent, claim_type),
        run_id=run_id,
        agent=agent,
        created_at=dt.datetime.now(dt.UTC).isoformat(),
        claim_type=claim_type,
        claim=claim,
        reasoning=reasoning,
        supporting_refs=list(supporting_refs),
        data_snapshot=data_snapshot,
        decision=decision,
        horizon_weeks=hw,
        evaluate_after=evaluate_dates(run_date, claim_type, hw),
        shadow_link=shadow_link,
        situation_text=situation_text,
        tags=list(tags) if tags is not None else [],
    )
    try:
        with diary_lock(), _path().open("a", encoding="utf-8") as fh:
            fh.write(entry.model_dump_json() + "\n")
    except OSError as e:  # 디스크 문제로 크루를 멈추지 않는다
        _log.warning("일기 기록 실패 (%s): %s", entry.id, e)
    return entry


def load_entries() -> list[DiaryEntry]:
    p = _path()
    if not p.exists():
        return []
    # id 로 dedup — 같은 날 crisis 재실행이 스케줄분과 같은 entry_id 를 append 할 수 있다.
    # 마지막(최신 append) 을 유지, 원래 위치는 보존 (dict 재대입).
    by_id: dict[str, DiaryEntry] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            e = DiaryEntry.model_validate_json(line)
        except ValueError:
            _log.warning("일기 라인 파싱 실패 — 건너뜀")
            continue
        by_id[e.id] = e
    return list(by_id.values())


def save_entries(entries: list[DiaryEntry]) -> None:
    """전체 재기록 (append-only 원칙의 실용적 축소판 — ~연 수백 건 규모라 rewrite 충분).

    ponytail: report/phase-4 §2.3 은 항목당 개별 파일을 명시하나, 갱신(채점·반성)이
    필요한 필드가 있어 단일 jsonl + 전체 rewrite 로 단순화 (3a-9 부터 유지된 결정).
    **호출자는 `diary_lock()` 안에서 load_entries()..save_entries() 를 감싸야 한다**
    (동시 append 유실 방지 — evaluate/reviewer/rag/governance 가 그렇게 함).
    """
    try:
        text = "\n".join(e.model_dump_json() for e in entries)
        _write_atomic(_path(), (text + ("\n" if entries else "")).encode("utf-8"))
    except OSError as e:
        _log.warning("일기 갱신 실패: %s", e)


__all__ = ["derive_tags", "diary_lock", "load_entries", "log", "save_entries"]
