"""AllocationTableTool — score_smooth → 카테고리 배분 (슬라이드 보간). docs/TOOLS.md §5.

근거: report/phase-2 §2. 임계값·앵커는 config/allocation.yaml. LLM 관여 0.
CRISIS 는 -12 앵커로 스냅.
"""

from __future__ import annotations

from aegisvest.rules import allocation_rules
from aegisvest.schemas import AllocationTargets, ToolError

_LOW, _MID, _HIGH, _SLEEVE, _CASH = range(5)


def _interp(score: float, anchors: dict[int, list[float]]) -> tuple[list[float], list[int]]:
    keys = sorted(anchors)
    s = max(keys[0], min(keys[-1], score))
    lo = max(k for k in keys if k <= s)
    hi = min(k for k in keys if k >= s)
    if lo == hi:
        return anchors[lo], [lo, hi]
    frac = (s - lo) / (hi - lo)
    blended = [a + frac * (b - a) for a, b in zip(anchors[lo], anchors[hi], strict=True)]
    return blended, [lo, hi]


def _max_positions(nav_usd: float, mode: str) -> dict[str, int]:
    rules = allocation_rules()
    if mode == "paper":
        return dict(rules.paper_max_positions)
    tiers = sorted(rules.nav_tiers, key=lambda t: t.below_usd)
    for tier in tiers:
        if nav_usd < tier.below_usd:
            return dict(tier.max_positions)
    return dict(tiers[-1].max_positions)


def allocation_targets(
    score_smooth: float, nav_usd: float = 0.0, *, crisis: bool = False, mode: str = "paper"
) -> AllocationTargets | ToolError:
    """`score_smooth`: 레짐 5일 EMA. `mode`: paper|live. `crisis`: -12 앵커 스냅."""
    if mode not in {"paper", "live"}:
        return ToolError(error=f"알 수 없는 mode: {mode}", field="mode")
    rules = allocation_rules()
    eff_score = -12.0 if crisis else score_smooth
    vals, used = _interp(eff_score, rules.anchors)

    sleeve = vals[_SLEEVE] / 100.0
    cash = vals[_CASH] / 100.0
    cat_sleeve = {
        "low": vals[_LOW] / 100.0,
        "mid": vals[_MID] / 100.0,
        "high": vals[_HIGH] / 100.0,
    }
    cat_total = {k: round(v * sleeve, 6) for k, v in cat_sleeve.items()}
    # 고위험 절대 상한 강제
    cap = rules.guardrails.high_abs_cap
    if cat_total["high"] > cap:
        overflow = cat_total["high"] - cap
        cat_total["high"] = cap
        cat_total["low"] += overflow  # 초과분은 저위험으로

    return AllocationTargets(
        score_smooth=score_smooth,
        crisis=crisis,
        equity_sleeve_pct=round(sleeve, 6),
        cash_pct=round(cash, 6),
        category_targets_sleeve={k: round(v, 6) for k, v in cat_sleeve.items()},
        category_targets_total=cat_total,
        max_positions=_max_positions(nav_usd, mode),
        interp_anchors=used,
        guardrails=rules.guardrails.model_dump(),
    )
