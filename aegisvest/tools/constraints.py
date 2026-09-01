"""ConstraintChecker — 하드 가드레일 검증. docs/TOOLS.md §9.

근거: report/phase-2 §2.3. ⑦ Risk Officer 단계에서 강제 실행되는 하드 게이트 —
에이전트 판단과 무관하게 파이썬이 pass/fail 을 낸다.
"""

from __future__ import annotations

from collections import defaultdict

from aegisvest.rules import allocation_rules
from aegisvest.schemas import ConstraintResult, ConstraintViolation, DraftPortfolio

_CATS = ("low", "mid", "high")


def check_constraints(draft: DraftPortfolio) -> ConstraintResult:
    g = allocation_rules().guardrails
    w = draft.category_weights
    v: list[ConstraintViolation] = []

    high = w.get("high", 0.0)
    if high > g.high_abs_cap + 1e-9:
        v.append(
            ConstraintViolation(
                rule="high_abs_cap", detail=f"고위험 {high:.1%} > {g.high_abs_cap:.0%}", value=high
            )
        )

    cash = w.get("cash", 0.0)
    if cash < g.cash_floor - 1e-9:
        v.append(
            ConstraintViolation(
                rule="cash_floor", detail=f"현금 {cash:.1%} < {g.cash_floor:.0%}", value=cash
            )
        )

    total = sum(w.get(k, 0.0) for k in (*_CATS, "cash"))
    if abs(total - 1.0) > 0.005:
        v.append(
            ConstraintViolation(
                rule="weights_sum", detail=f"비중 합 {total:.4f} ≠ 1.0", value=total
            )
        )

    for p in draft.positions:
        if p.weight > g.single_name_cap + 1e-9:
            v.append(
                ConstraintViolation(
                    rule="single_name_cap",
                    detail=f"{p.ticker} {p.weight:.1%} > {g.single_name_cap:.0%}",
                    value=p.weight,
                )
            )

    by_sector: dict[str, float] = defaultdict(float)
    for p in draft.positions:
        if p.sector:
            by_sector[p.sector] += p.weight
    for sector, sw in by_sector.items():
        if sw > g.sector_cap + 1e-9:
            v.append(
                ConstraintViolation(
                    rule="sector_cap", detail=f"{sector} {sw:.1%} > {g.sector_cap:.0%}", value=sw
                )
            )

    if draft.prior_category_weights:
        for c in _CATS:
            change_pp = abs(w.get(c, 0.0) - draft.prior_category_weights.get(c, 0.0)) * 100.0
            if change_pp > g.max_change_per_rebal_pp + 1e-6:
                v.append(
                    ConstraintViolation(
                        rule="max_change_per_rebal",
                        detail=f"{c} 변동 {change_pp:.1f}%p > {g.max_change_per_rebal_pp:.0f}%p",
                        value=change_pp,
                    )
                )

    return ConstraintResult(verdict="PASS" if not v else "FAIL", violations=v)
