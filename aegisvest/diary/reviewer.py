"""판단 일기 반성 배치 — ⑨ Performance Reviewer (LLM 서술). report/phase-4 §4.

`evaluate.py` 채점 후 (`status == "evaluated"`) 항목 중 `needs_reflection` 인 것을 골라
Reviewer 크루로 `post_mortem`·`lesson_card`·event/theme/mistake 태그를 붙인다. **점수·verdict 는
안 건드림** (evaluate.py 소관). RAG 진입 게이트(§4.3)로 `rag_status` 를 auto / pending_review 확정.

status 전이: evaluated → reflected (needs_reflection 시) / gated (아니면). 둘 다 종결·RAG 진입.
rag_status(§4.3): 레짐콜·CIO override·위기전환·대형 틸트 → pending_review, 그 외 auto.

분리 원칙: 채점(evaluate.py, 결정론) 과 별도 실행. cron 에서 체이닝:
    python -m aegisvest.diary.evaluate && python -m aegisvest.diary.reviewer

하인드사이트 방지(§4.2): Reviewer 입력은 **기록 시점** 필드(claim/reasoning/refs/snapshot)+
채점 수치뿐. 라이브 뉴스 툴은 주지 않는다 (오늘 헤드라인 = 사후정보). point-in-time 뉴스
인용은 Sharadar 도입 시 (3a-11 백테스트 보류와 같은 근거).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from aegisvest.config import get_settings
from aegisvest.diary.evaluate import needs_reflection
from aegisvest.diary.logger import load_entries, save_entries
from aegisvest.diary.schema import clip_tokens, diary_taxonomy
from aegisvest.schemas import DiaryEntry, ReviewerOutput

_log = logging.getLogger("aegisvest.diary.reviewer")

# "더 신중했어야", "주의 필요" 등 구체 신호 없는 반성 (§4.2 — 폐기 대상)
_VAGUE = re.compile(
    r"신중|조심|주의(?:가|를|해|$| )|잘\s*봤어야|더\s*봤어야|careful|cautious|vigilan",
    re.IGNORECASE,
)
_LESSON_CARD_TOKENS = 25
_PENDING_REVIEW_TYPES = frozenset({"regime_call", "cio_override"})


def _cap_lesson_card(card: str) -> str:
    """25 토큰 이내 강제 (§4.2). 근사 절삭은 diary.schema.clip_tokens 공용."""
    return clip_tokens(card, _LESSON_CARD_TOKENS)


def rag_status_for(entry: DiaryEntry) -> str:
    """report/phase-4 §4.3 (K). 대형 틸트·위기·레짐·CIO override → 인간 확인. 나머지 auto."""
    if entry.claim_type in _PENDING_REVIEW_TYPES:
        return "pending_review"
    if "action:crisis_shift" in entry.tags:
        return "pending_review"
    if entry.claim_type == "allocation_tilt" and (
        "magnitude:large" in entry.tags or "magnitude:structural" in entry.tags
    ):
        return "pending_review"
    return "auto"


def _validate(out: ReviewerOutput) -> list[str]:
    """§4.2 — 구체 신호 없는 모호한 반성 플래그 (폐기 대신 pending_review 로 강등)."""
    problems: list[str] = []
    ms = out.missed_signal.strip()
    if len(ms) < 8 or (_VAGUE.search(ms) and not ms.lower().startswith("none")):
        problems.append("missed_signal: 구체적 신호 인용 없음")
    if len(out.what_would_change.strip()) < 8 or _VAGUE.search(out.what_would_change):
        problems.append("what_would_change: 모호 (수정 휴리스틱 아님)")
    return problems


def _record_pending_tags(unknown: dict[str, list[str]]) -> None:
    """SEMI-OPEN 신규값 기록 (§7.4 — 작동하되 분기 검토 전까지 플래그)."""
    path = get_settings().state_dir / "diary" / "pending_tags.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        existing: dict[str, list[str]] = loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError):
        existing = {}
    changed = False
    for dim, vals in unknown.items():
        known = set(existing.get(dim, []))
        for v in vals:
            if v and v not in known:
                existing.setdefault(dim, []).append(v)
                known.add(v)
                changed = True
    if not changed:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        _log.warning("pending_tags 기록 실패: %s", e)


def _merge_tags(entry: DiaryEntry, out: ReviewerOutput) -> list[str]:
    tax = diary_taxonomy()
    known_event = set(tax.semi_open.get("event", []))
    known_theme = set(tax.semi_open.get("theme", []))
    known_mistake = set(tax.closed.get("mistake", []))
    _record_pending_tags(
        {
            "event": [t for t in out.event_tags if t not in known_event],
            "theme": [t for t in out.theme_tags if t not in known_theme],
        }
    )
    tags = [*entry.tags]
    tags += [f"event:{t}" for t in out.event_tags]
    tags += [f"theme:{t}" for t in out.theme_tags]
    mistake = out.mistake_tag.strip()
    if mistake and mistake != "none" and mistake in known_mistake:  # CLOSED: 미지값 드롭
        tags.append(f"mistake:{mistake}")
    # ponytail: max_tags_per_entry 상한 유지 — 반성 태그가 넘치면 잘림 (드묾, 4-6 재검토)
    return list(dict.fromkeys(tags))[: tax.max_tags_per_entry]


def _reviewer_inputs(entry: DiaryEntry) -> dict[str, str]:
    tax = diary_taxonomy()
    return {
        "claim_type": entry.claim_type,
        "claim": entry.claim,
        "reasoning": entry.reasoning,
        "supporting_refs": json.dumps(entry.supporting_refs, ensure_ascii=False),
        "data_snapshot": json.dumps(entry.data_snapshot, ensure_ascii=False),
        "decision": json.dumps(entry.decision, ensure_ascii=False, default=str),
        "situation_text": entry.situation_text,
        "outcome": json.dumps(entry.outcome or {}, ensure_ascii=False, default=str),
        "semi_open_events": ", ".join(tax.semi_open.get("event", [])),
        "semi_open_themes": ", ".join(tax.semi_open.get("theme", [])),
        "closed_mistakes": ", ".join(tax.closed.get("mistake", [])),
    }


def _reflect(entry: DiaryEntry, llm: Any) -> ReviewerOutput | None:
    from aegisvest.agents.crew import run_reviewer  # noqa: PLC0415  # crewai 지연 로드

    try:
        return run_reviewer(_reviewer_inputs(entry), llm=llm)
    except Exception as e:  # 크루 1건 실패로 배치 전체를 멈추지 않는다
        _log.warning("reviewer 실패 (%s): %s", entry.id, e)
        return None


def _apply(entry: DiaryEntry, out: ReviewerOutput) -> bool:
    """반성 결과를 항목에 append. 모호 플래그 시 rag_status→pending_review. 반환=플래그 여부."""
    problems = _validate(out)
    entry.outcome = {**(entry.outcome or {}), "what_happened": out.what_happened}
    entry.post_mortem = {
        "missed_signal": out.missed_signal,
        "underestimated_because": out.underestimated_because,
        "root_cause": out.root_cause,
        "lesson": out.lesson,
        "base_rate_note": out.base_rate_note,
        "what_would_change": out.what_would_change,
    }
    entry.lesson_card = _cap_lesson_card(out.lesson_card)
    entry.tags = _merge_tags(entry, out)
    entry.status = "reflected"
    if problems:
        entry.post_mortem["flags"] = problems
        entry.rag_status = "pending_review"
    return bool(problems)


def _llm_available() -> bool:
    return bool(get_settings().deepseek_api_key)


def run(*, llm: Any = None) -> dict[str, int]:
    """채점 완료(`evaluated`) 미반성 항목 처리. 반환은 카운트 요약 (호출자·CLI 공용)."""
    entries = load_entries()
    have_llm = llm is not None or _llm_available()
    counts = {"gated": 0, "reflected": 0, "flagged": 0, "skipped_no_llm": 0, "errored": 0}

    for entry in entries:
        if entry.status != "evaluated" or entry.post_mortem is not None:
            continue
        entry.rag_status = rag_status_for(entry)
        counts["gated"] += 1
        if not needs_reflection(entry):
            entry.status = "gated"  # 종결 — 상황벡터만 RAG 진입, 반성 불필요 (§3.3)
            continue
        if not have_llm:
            counts["skipped_no_llm"] += 1  # evaluated 유지 — 키 생기면 다음 배치가 재시도
            continue
        out = _reflect(entry, llm)
        if out is None:
            counts["errored"] += 1
            continue
        counts["flagged"] += int(_apply(entry, out))
        counts["reflected"] += 1

    save_entries(entries)
    return counts


def main() -> None:
    logging.basicConfig(
        level=get_settings().log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    _log.info("일기 반성 완료: %s", run())


if __name__ == "__main__":
    main()
