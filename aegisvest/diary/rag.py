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
import math
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, NamedTuple

import chromadb

from aegisvest.config import get_settings
from aegisvest.diary.logger import load_entries, save_entries
from aegisvest.diary.schema import clip_tokens, derive_tags, diary_taxonomy
from aegisvest.schemas import DiaryEntry

_log = logging.getLogger("aegisvest.diary.rag")

_SITUATIONS = "diary_situations"
_LESSONS = "diary_lessons"
_COSINE = {"hnsw:space": "cosine"}
_RAG_ELIGIBLE = frozenset({"auto", "approved"})
_INDEXED_STATUS = frozenset({"reflected", "gated"})
_PREFILTER = 40  # §6.3 Q-D — 컬렉션별 top-40, 캐스케이드 없음
_ATTR_LOW_MIN_COSINE = 0.62  # §6.3 — attribution:low 는 코사인 0.62 이상만
_MID_SUMMARY_COSINE = 0.75  # §6.4 P — top-1 중간요약 자격
_STRUCT_DIMS = ("claim_type", "sleeve", "regime")
_SET_DIMS = ("signal", "event", "theme")
_W_COSINE, _W_STRUCT, _W_RECENCY = 0.65, 0.20, 0.15  # O-A (§0 결정 O)


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

    # ─────────────────────── 회상 (recall, §6.3) ───────────────────────

    def recall(
        self, query_text: str, situation_tags: list[str], *, k: int = 4
    ) -> list[RecalledCase]:
        """§6.3 — Q-D (메타 필터 없음, 컬렉션별 top-40) → O-A 랭킹 → dedupe → floor → 다양성."""
        if self.situations.count() == 0 and self.lessons.count() == 0:
            return []  # 콜드 스타트 (§9) — 무반환, 기본 지능 작동
        q = _embed([query_text])[0]
        tax = diary_taxonomy()
        best: dict[str, RecalledCase] = {}  # entry_id → 최고 rank 후보
        for meta, cosine, doc, kind in [
            *_hits(self.situations, q, "situation"),
            *_hits(self.lessons, q, "lesson"),
        ]:
            tags = str(meta.get("tags") or "").split()
            rank = (
                _W_COSINE * cosine
                + _W_STRUCT * _structural(tags, situation_tags)
                + _W_RECENCY * _recency(tags, meta, tax.recency_halflife_months)
            )
            eid = str(meta.get("entry_id") or "")
            if eid in best and best[eid].rank >= round(rank, 3):
                continue
            ref = str(meta.get("evaluated_at") or "") or str(meta.get("created_at") or "")
            best[eid] = RecalledCase(
                entry_id=eid,
                kind=kind,
                cosine=round(cosine, 3),
                rank=round(rank, 3),
                verdict=str(meta.get("verdict") or ""),
                score=int(meta.get("score") or 0),
                regime=str(meta.get("regime") or ""),
                attribution=str(meta.get("attribution") or ""),
                month=ref[:7],
                tags=tags,
                text=doc,
            )
        # dedupe 후 필터 (§6.3 순서) — 한 항목의 약한 벡터 하나로 탈락시키지 않는다
        kept = [
            c
            for c in best.values()
            if c.cosine >= tax.similarity_floor
            and not (c.attribution == "low" and c.cosine < _ATTR_LOW_MIN_COSINE)
        ]
        kept.sort(key=lambda c: c.rank, reverse=True)
        return _diversify(kept, k)


def backfill() -> dict[str, int]:
    """전체 일기를 훑어 미색인 자격 항목을 벡터화. 주간 배치 (CLI)."""
    entries = load_entries()
    counts = DiaryRAG().index(entries)
    save_entries(entries)
    return counts


# ─────────────────────── 회상 헬퍼 ───────────────────────


class RecalledCase(NamedTuple):
    entry_id: str
    kind: str  # situation | lesson
    cosine: float
    rank: float
    verdict: str
    score: int
    regime: str
    attribution: str
    month: str  # YYYY-MM
    tags: list[str]
    text: str  # situation_text 또는 lesson_text 문서


def _hits(
    collection: Any, q: list[float], kind: str
) -> list[tuple[dict[str, Any], float, str, str]]:
    n = min(_PREFILTER, collection.count())
    if n == 0:
        return []
    res = collection.query(query_embeddings=[q], n_results=n)
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    out: list[tuple[dict[str, Any], float, str, str]] = []
    for i in range(len(metas)):
        cosine = 1.0 - float(dists[i]) if i < len(dists) else 0.0  # 컬렉션이 cosine space
        out.append((metas[i] or {}, cosine, docs[i] if i < len(docs) else "", kind))
    return out


def _pick(tags: list[str], dims: tuple[str, ...]) -> set[str]:
    return {t for t in tags if t.split(":", 1)[0] in dims}


def _structural(cand_tags: list[str], query_tags: list[str]) -> float:
    """§6.3 — {claim_type,sleeve,regime} 교집합/3 + {signal,event,theme} Jaccard, 각 0.5."""
    inter = len(_pick(cand_tags, _STRUCT_DIMS) & _pick(query_tags, _STRUCT_DIMS)) / 3.0
    sc, sq = _pick(cand_tags, _SET_DIMS), _pick(query_tags, _SET_DIMS)
    union = sc | sq
    jac = len(sc & sq) / len(union) if union else 0.0
    return 0.5 * inter + 0.5 * jac


def _months_since(iso: str) -> float:
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return 999.0
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - then).total_seconds() / (30.44 * 86400))


def _recency(cand_tags: list[str], meta: dict[str, Any], halflife: int) -> float:
    ref = str(meta.get("evaluated_at") or "") or str(meta.get("created_at") or "")
    decay = math.exp(-_months_since(ref) / halflife) if ref else 0.0
    return max(decay, 0.15 if "regime:crisis" in cand_tags else 0.0)  # 위기 항목 상시 후보


def _diversify(ranked: list[RecalledCase], k: int) -> list[RecalledCase]:
    """§6.3 — DB 에 crisis + |score|≥2 가 있는데 top-k 에 없으면 최저 rank 1건 교체."""
    chosen = ranked[:k]
    if any("regime:crisis" in c.tags for c in chosen):
        return chosen
    forced = next((c for c in ranked if "regime:crisis" in c.tags and abs(c.score) >= 2), None)
    if forced is not None and chosen:
        chosen = [*chosen[:-1], forced]
    return chosen


def build_query(
    *, regime: str, snapshot: dict[str, Any], considering: str = ""
) -> tuple[str, list[str]]:
    """현재 상황 → (쿼리 문자열, situation_tags). §6.2 — 동일 결정론 태그 엔진, LLM 불필요.

    event/theme 태그는 애널리스트 출력이 나온 뒤라야 알 수 있어 여기선 생략 (signal 은 스냅샷
    기반이라 포함). 4-4 는 단일 회상 (①②③⑤⑥⑦ 공용), 2단계 회상은 4-6.
    """
    # 현재 상황엔 claim_type·sleeve 가 없음 — regime + signal 태그만 (구조매칭 §7.3)
    tags = [
        t
        for t in derive_tags(regime=regime, claim_type="regime_call", data_snapshot=snapshot)
        if t.startswith(("regime:", "signal:"))
    ]
    labels = (
        ("hy_oas_bp", "HY OAS"),
        ("hy_oas_4w_change_bp", "HY OAS 4주"),
        ("vix", "VIX"),
        ("pct_above_200dma", "200일선 상회%"),
        ("score_smooth", "레짐 smooth"),
    )
    bits = [f"레짐 {regime}"]
    bits += [f"{lab} {snapshot[key]}" for key, lab in labels if snapshot.get(key) is not None]
    if considering:
        bits.append(considering)
    return " · ".join(bits), tags


def _short_tags(tags: list[str]) -> str:
    keep = ("signal", "event", "theme", "sleeve")
    vals = [t.split(":", 1)[1] for t in tags if ":" in t and t.split(":", 1)[0] in keep]
    return "·".join(dict.fromkeys(vals)) or "—"


def format_recall(cases: list[RecalledCase]) -> str:
    """§6.4 P-D — top-1(코사인≥0.75) 중간요약 ~120토큰 + 나머지 카드 ≤25토큰. 툴 호출 없음."""
    if not cases:
        return ""
    out = ["## 판단 일기 — 유사 사례 (참고용, 현재 데이터가 우선)", ""]
    rest = cases
    head = cases[0]
    if head.cosine >= _MID_SUMMARY_COSINE:
        out += [
            f"[{head.month} · {head.verdict} {head.score:+d} · 유사도 {head.cosine:.2f}]",
            clip_tokens(head.text, 120),
            "",
        ]
        rest = cases[1:]
    for c in rest:
        head_bits = f"[{c.month} {c.verdict}{c.score:+d} | {_short_tags(c.tags)}]"
        out.append(f"· {head_bits} {clip_tokens(c.text, 25)}")
    out += ["", "⚠️ 참고용. 현재 데이터가 우선. 상황이 다를 수 있으니 맹신 금지."]
    return "\n".join(out)


def main() -> None:
    logging.basicConfig(
        level=get_settings().log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    _log.info("일기 RAG 백필: %s", backfill())


if __name__ == "__main__":
    main()
