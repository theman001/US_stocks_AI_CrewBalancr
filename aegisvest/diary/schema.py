"""판단 일기 — 결정론 파생 필드 (claim_type 분류, horizon 일정, 태그). report/phase-4 §2·§7.

기록 시점에 파이썬이 확정하는 부분. LLM 은 claim/reasoning 텍스트와 반성 시 event/theme/mistake
태그(§7.2 — 통제 어휘 안에서만 선택)만 채운다. DiaryEntry 모델 자체는 aegisvest/schemas.py.
"""

from __future__ import annotations

import datetime as dt
import re
from functools import lru_cache
from typing import Any

import yaml
from pydantic import BaseModel

from aegisvest.config import CONFIG_DIR

# ─────────────────────── 통제 어휘 (config/diary_taxonomy.yaml) ───────────────────────


class Taxonomy(BaseModel):
    closed: dict[str, list[str]]
    semi_open: dict[str, list[str]]
    signal_rules: dict[str, str]
    max_tags_per_entry: int
    similarity_floor: float
    recency_halflife_months: int


@lru_cache(maxsize=1)
def diary_taxonomy() -> Taxonomy:
    data = yaml.safe_load((CONFIG_DIR / "diary_taxonomy.yaml").read_text(encoding="utf-8"))
    return Taxonomy.model_validate(data)


# report/phase-4 §7.1 CLOSED.claim_type — diary/logger.py 검증에 사용
CLAIM_TYPES: frozenset[str] = frozenset(diary_taxonomy().closed["claim_type"])

# claim_type → evaluate_after 오프셋(주). report/phase-4 §2.1 표.
_HORIZON_SCHEDULE: dict[str, tuple[int, ...]] = {
    "regime_call": (4, 12),  # 4주 예비 + 12주 최종
    "sleeve_stance": (12,),
    "allocation_tilt": (12,),
    "exclusion": (12,),
    "event_risk": (2,),  # 이벤트일 + 2주 (이벤트일 미상 시 기록일 기준)
    "catalyst": (2,),
    "risk_veto": (8,),
    "cio_override": (12,),
}


def default_horizon_weeks(claim_type: str) -> int:
    return _HORIZON_SCHEDULE.get(claim_type, (12,))[-1]


def evaluate_dates(run_date: dt.date, claim_type: str, horizon_weeks: int) -> list[str]:
    offsets = _HORIZON_SCHEDULE.get(claim_type, (horizon_weeks,))
    return [(run_date + dt.timedelta(weeks=w)).isoformat() for w in offsets]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "x"


def entry_id(run_id: str, agent: str, claim_type: str) -> str:
    return f"{run_id}_{_slug(agent)}_{claim_type}"


def magnitude_of(delta_pp: float, *, structural_threshold_pp: float = 20.0) -> str:
    """카테고리 비중 변화(%p, 소수 아님) → magnitude 태그. report/phase-4 §7.1."""
    d = abs(delta_pp)
    if d >= structural_threshold_pp:  # 슬리브 사실상 on/off
        return "structural"
    if d > 2:
        return "large"
    if d >= 1:
        return "moderate"
    return "minor"


# ── signal_rules 평가 — data_snapshot(dict) 조건식 → signal 태그 ──
# ponytail: eval() 은 우리가 직접 관리하는 config/diary_taxonomy.yaml 만 평가 (외부입력 아님).
# 실패(필드 없음·오류)는 조용히 미발동 처리 — 일기 기록을 막지 않는다.
def eval_signal_rules(snapshot: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for tag, expr in diary_taxonomy().signal_rules.items():
        try:
            if eval(expr, {"__builtins__": {}}, snapshot):
                out.append(tag)
        except Exception:  # 필드 결측(NameError)·타입 불일치 → 미발동
            continue
    return out


def _valid_closed(dimension: str, value: str) -> bool:
    allowed = diary_taxonomy().closed.get(dimension)
    return allowed is None or value in allowed


def derive_tags(
    *,
    regime: str,
    claim_type: str,
    sleeve: str | None = None,
    action: str | None = None,
    magnitude: str | None = None,
    rates_dir: str | None = None,
    signals: tuple[str, ...] = (),
    data_snapshot: dict[str, Any] | None = None,
) -> list[str]:
    """report/phase-4 §7.2 — 기록 시점 결정론 태그. `data_snapshot` 주면 signal 자동 평가."""
    tags = [f"regime:{regime.lower()}", f"claim_type:{claim_type}"]
    for dim, val in (
        ("sleeve", sleeve),
        ("action", action),
        ("magnitude", magnitude),
        ("rates_dir", rates_dir),
    ):
        if val and _valid_closed(dim, val):
            tags.append(f"{dim}:{val}")

    auto_signals = eval_signal_rules(data_snapshot) if data_snapshot else []
    all_signals = dict.fromkeys((*signals, *auto_signals))  # 순서 유지 dedup
    known_signals = set(diary_taxonomy().semi_open.get("signal", []))
    tags.extend(f"signal:{s}" for s in all_signals if s in known_signals)

    return tags[: diary_taxonomy().max_tags_per_entry]
