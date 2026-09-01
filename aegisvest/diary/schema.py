"""판단 일기 — 결정론 파생 필드 (claim_type 분류, horizon 일정, 태그). report/phase-4 §2.

기록 시점에 파이썬이 확정하는 부분. LLM 은 claim/reasoning 텍스트만 채운다.
DiaryEntry 모델 자체는 aegisvest/schemas.py.
"""

from __future__ import annotations

import datetime as dt
import re

# report/phase-4 §7.2 통제 어휘
CLAIM_TYPES: frozenset[str] = frozenset(
    {
        "regime_call",
        "sleeve_stance",
        "allocation_tilt",
        "exclusion",
        "event_risk",
        "catalyst",
        "risk_veto",
        "cio_override",
    }
)

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


def derive_tags(
    *,
    regime: str,
    claim_type: str,
    sleeve: str | None = None,
    action: str | None = None,
    magnitude: str | None = None,
    rates_dir: str | None = None,
    signals: tuple[str, ...] = (),
) -> list[str]:
    tags = [f"regime:{regime.lower()}", f"claim_type:{claim_type}"]
    for prefix, val in (
        ("sleeve", sleeve),
        ("action", action),
        ("magnitude", magnitude),
        ("rates_dir", rates_dir),
    ):
        if val:
            tags.append(f"{prefix}:{val}")
    tags.extend(f"signal:{s}" for s in signals)
    return tags
