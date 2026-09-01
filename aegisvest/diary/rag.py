"""판단 일기 RAG 저장 — bge-m3 이중 벡터 + ChromaDB. report/phase-4 §5. (회상은 4-4.)

- **이중 벡터** (§5.1): `situation` 벡터 (`situation_text`, 기록 시) + `lesson` 벡터
  (`post_mortem.lesson` + `lesson_card` + event/theme/mistake·signal 태그, 반성 시).
  컬렉션 2개(`diary_situations`/`diary_lessons`), 공유 키 = 항목 `id`. 벡터는 각 1회
  생성 — `situation_vector_id`/`lesson_vector_id` 필드로 재계산 방지.
- **저장 자격**: `rag_status ∈ {auto, approved}` (§4.3 — 회상은 auto+approved 만) 그리고
  `status ∈ {reflected, gated}`. `retired` → 기존 벡터 삭제. lesson 은 `post_mortem.lesson` 필요.
- **인프라** (§5.2): `PersistentClient(state/chroma)` 임베디드, cosine space, ARM64 OK.

임베딩 모델은 지연 로드 (~2.3GB). 테스트는 `_embed` 를 monkeypatch (가중치 다운로드 회피).
cron: `evaluate && reviewer && python -m aegisvest.diary.rag` (주간 배치).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import chromadb

from aegisvest.config import get_settings
from aegisvest.diary.logger import load_entries, save_entries
from aegisvest.schemas import DiaryEntry

_log = logging.getLogger("aegisvest.diary.rag")

_SITUATIONS = "diary_situations"
_LESSONS = "diary_lessons"
_COSINE = {"hnsw:space": "cosine"}
_RAG_ELIGIBLE = frozenset({"auto", "approved"})
_INDEXED_STATUS = frozenset({"reflected", "gated"})


# ─────────────────────── 임베딩 (bge-m3, 지연 로드) ───────────────────────


@lru_cache(maxsize=1)
def _model() -> Any:
    from FlagEmbedding import BGEM3FlagModel  # noqa: PLC0415  # ~2.3GB, 지연 로드

    return BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)


def _embed(texts: list[str]) -> list[list[float]]:
    """bge-m3 dense 벡터 (1024차원, 정규화됨). 테스트에서 monkeypatch."""
    vecs = _model().encode(texts, batch_size=4, max_length=1024)["dense_vecs"]
    out = [list(map(float, v)) for v in vecs]
    if len(out) != len(texts):  # 부분 임베딩 → id/vector 정렬 깨짐 방지
        raise RuntimeError(f"임베딩 개수 불일치: {len(out)} != {len(texts)}")
    return out


# ─────────────────────── ChromaDB ───────────────────────


@lru_cache(maxsize=4)
def _client(path: str) -> Any:
    return chromadb.PersistentClient(path=path)


def collections() -> tuple[Any, Any]:
    """(diary_situations, diary_lessons) 컬렉션. 4-4 recall 도 재사용."""
    d = get_settings().state_dir / "chroma"
    d.mkdir(parents=True, exist_ok=True)
    client = _client(str(d))
    return (
        client.get_or_create_collection(_SITUATIONS, metadata=_COSINE),
        client.get_or_create_collection(_LESSONS, metadata=_COSINE),
    )


# ─────────────────────── 텍스트·메타 ───────────────────────


def _tag_val(tags: list[str], dim: str) -> str:
    for t in tags:
        if t.startswith(f"{dim}:"):
            return t.split(":", 1)[1]
    return ""


def lesson_text(entry: DiaryEntry) -> str:
    """lesson 벡터 임베딩 텍스트 (§5.1). post_mortem.lesson 없으면 빈 문자열."""
    pm = entry.post_mortem or {}
    lesson = str(pm.get("lesson") or "").strip()
    if not lesson:
        return ""
    parts = [lesson]
    if entry.lesson_card:
        parts.append(str(entry.lesson_card))
    tags = sorted(
        t.replace(":", " ")
        for t in entry.tags
        if t.split(":", 1)[0] in ("event", "theme", "mistake", "signal")
    )
    if tags:
        parts.append("태그: " + ", ".join(tags))
    return " / ".join(parts)


def _meta(entry: DiaryEntry) -> dict[str, str | int | float | bool]:
    o = entry.outcome or {}
    score = o.get("score")
    return {
        "entry_id": entry.id,
        "claim_type": entry.claim_type,
        "tags": " ".join(entry.tags),
        "regime": _tag_val(entry.tags, "regime"),
        "sleeve": _tag_val(entry.tags, "sleeve"),
        "verdict": str(o.get("verdict") or ""),
        "score": score if isinstance(score, int) else 0,
        "attribution": str(o.get("attribution") or ""),
        "created_at": entry.created_at,
        "evaluated_at": str(o.get("evaluated_at") or ""),
        "rag_status": entry.rag_status,
    }


# ─────────────────────── 저장 (index / backfill) ───────────────────────


class DiaryRAG:
    def __init__(self) -> None:
        self.situations, self.lessons = collections()

    def _purge(self, entry: DiaryEntry) -> bool:
        hit = False
        if entry.situation_vector_id:
            self.situations.delete(ids=[entry.situation_vector_id])
            entry.situation_vector_id = None
            hit = True
        if entry.lesson_vector_id:
            self.lessons.delete(ids=[entry.lesson_vector_id])
            entry.lesson_vector_id = None
            hit = True
        return hit

    def index(self, entries: list[DiaryEntry]) -> dict[str, int]:
        """자격 있는 미색인 항목을 upsert, vector_id 필드를 채운다 (in-place). 배치 임베딩."""
        counts = {"situations": 0, "lessons": 0, "retired": 0}
        need_sit: list[DiaryEntry] = []
        need_les: list[tuple[DiaryEntry, str]] = []
        for e in entries:
            if e.rag_status == "retired":
                counts["retired"] += int(self._purge(e))
                continue
            if e.rag_status not in _RAG_ELIGIBLE or e.status not in _INDEXED_STATUS:
                continue
            if e.situation_vector_id is None and e.situation_text.strip():
                need_sit.append(e)
            if e.lesson_vector_id is None and (lt := lesson_text(e)):
                need_les.append((e, lt))

        if need_sit:
            self.situations.upsert(
                ids=[e.id for e in need_sit],
                embeddings=_embed([e.situation_text for e in need_sit]),
                metadatas=[_meta(e) for e in need_sit],
                documents=[e.situation_text for e in need_sit],
            )
            for e in need_sit:
                e.situation_vector_id = e.id
            counts["situations"] = len(need_sit)

        if need_les:
            self.lessons.upsert(
                ids=[f"{e.id}#lesson" for e, _ in need_les],
                embeddings=_embed([lt for _, lt in need_les]),
                metadatas=[_meta(e) for e, _ in need_les],
                documents=[lt for _, lt in need_les],
            )
            for e, _ in need_les:
                e.lesson_vector_id = f"{e.id}#lesson"
            counts["lessons"] = len(need_les)

        return counts


def backfill() -> dict[str, int]:
    """전체 일기를 훑어 미색인 자격 항목을 벡터화. 주간 배치 (CLI)."""
    entries = load_entries()
    counts = DiaryRAG().index(entries)
    save_entries(entries)
    return counts


def main() -> None:
    logging.basicConfig(
        level=get_settings().log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    _log.info("일기 RAG 백필: %s", backfill())


if __name__ == "__main__":
    main()
