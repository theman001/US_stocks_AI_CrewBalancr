"""CashFlowRebalancer — 신규 현금 우선 매수, 밴드 밖일 때만 매도. docs/TOOLS.md §8.

근거: report/phase-2 §3.3 ①. 적금형 최적화 — 매도(양도세·수수료) 최소화.
순서: (1) 가용 현금으로 부족 카테고리 매수 → (2) 그래도 밴드 밖이면 과대 카테고리 매도.
쿨다운(동일 카테고리 10거래일)은 **매도만** 막는다. 1회 변동 상한 적용. CRISIS 는 쿨다운 예외.
"""

from __future__ import annotations

from aegisvest.rules import Guardrails, allocation_rules
from aegisvest.schemas import RebalanceOrder, RebalancePlan, ToolError

_CATS = ("low", "mid", "high")


def _outside_band(current: float, target: float, g: Guardrails) -> bool:
    drift_pp = abs(current - target) * 100.0
    if target > 1e-9:
        drift_rel = abs(current - target) / target
    else:
        drift_rel = 0.0 if current < 1e-9 else 1.0
    return drift_pp >= g.rebal_band_abs_pp or drift_rel >= g.rebal_band_rel


def cash_flow_rebalance(
    targets_total: dict[str, float],
    current_category_usd: dict[str, float],
    cash_usd: float,
    pending_contribution_usd: float = 0.0,
    cooldown_state: dict[str, int] | None = None,
    *,
    crisis: bool = False,
) -> RebalancePlan | ToolError:
    """targets_total: low/mid/high 전체 포트 목표 비중(소수)."""
    if not all(c in targets_total for c in _CATS):
        return ToolError(error="targets_total 에 low/mid/high 필요", field="targets_total")
    g = allocation_rules().guardrails
    cd = cooldown_state or {}
    holding: dict[str, float] = {c: current_category_usd.get(c, 0.0) for c in _CATS}
    nav = sum(holding.values()) + cash_usd + pending_contribution_usd
    if nav <= 0:
        return ToolError(error="NAV <= 0", field="current_category_usd")

    target_usd = {c: targets_total[c] * nav for c in _CATS}
    cash_floor_usd = nav * g.cash_floor
    max_move_usd = nav * g.max_change_per_rebal_pp / 100.0
    deployable = pending_contribution_usd + max(0.0, cash_usd - cash_floor_usd)

    def _cooldown_hit(c: str, blocked: list[str]) -> bool:
        if crisis:
            return False
        if cd.get(c, 10_000) < g.cooldown_trading_days:
            blocked.append(c)
            return True
        return False

    cooldown_blocked: list[str] = []

    # ── 1) 부족 카테고리 매수 (상대 부족률 큰 순, deployable 소진까지) ──
    buys: list[RebalanceOrder] = []
    remaining = deployable
    underweight = sorted(
        (c for c in _CATS if target_usd[c] - holding[c] > 0),
        key=lambda c: (target_usd[c] - holding[c]) / max(target_usd[c], 1.0),
        reverse=True,
    )
    for c in underweight:
        if remaining <= 0:
            break
        # 쿨다운은 매도(단계 6)만 막는다 — 신규 현금 매수는 세금 0이라 제한 없음 (phase-2 §3.3 ⑦)
        amt = min(target_usd[c] - holding[c], remaining, max_move_usd)
        if amt <= 0:
            continue
        buys.append(RebalanceOrder(category=c, amount_usd=round(amt, 2)))
        holding[c] += amt
        remaining -= amt

    # ── 2) 매수 후에도 밴드 밖인 과대 카테고리 매도 ──
    sells: list[RebalanceOrder] = []
    for c in _CATS:
        w = holding[c] / nav
        if (
            holding[c] > target_usd[c]
            and _outside_band(w, targets_total[c], g)
            and not _cooldown_hit(c, cooldown_blocked)
        ):
            amt = min(holding[c] - target_usd[c], max_move_usd)
            sells.append(RebalanceOrder(category=c, amount_usd=round(amt, 2)))
            holding[c] -= amt

    post = {c: round(holding[c] / nav, 6) for c in _CATS}
    post["cash"] = round(max(0.0, nav - sum(holding.values())) / nav, 6)

    return RebalancePlan(
        new_cash_deployable_usd=round(deployable, 2),
        buys_from_new_cash=buys,
        sell_needed=bool(sells),
        sell_orders=sells,
        cooldown_blocked=sorted(set(cooldown_blocked)),
        post_action_weights=post,
    )
