"""⑥ PM 틸트 클램프 — LLM 제안 draft 를 하드 한계로 강제. report/phase-3 §3 ⑥·§5.

사용자 결정 2026-09-01: PM 이 비중을 제안하되 파이썬이 클램프.
불가침: 카테고리 목표 ±3%p / 종목은 스코어 상위 풀(max_positions x1.5) 내 / excluded 강제 제외 /
신규 편입 불가 / 티어 밴드·단일종목캡·고위험 절대캡·현금 하한.
"""

from __future__ import annotations

from collections import defaultdict

from aegisvest.rules import allocation_rules
from aegisvest.schemas import PMDraft, Position, SizedPosition, SizingResult

_CATS = ("low", "mid", "high")
_TILT_LIMIT = 0.03  # 카테고리 목표 대비 ±3%p


def eligible_pool(scoring: dict[str, object], max_positions: dict[str, int]) -> dict[str, str]:
    """ticker -> category. 카테고리별 스코어 상위 (max_positions x 1.5) 만 PM 선택 가능."""
    out: dict[str, str] = {}
    for cat in _CATS:
        sc = scoring.get(cat)
        rows = getattr(sc, "scores", []) if sc is not None else []
        n = max(1, round(max_positions.get(cat, 15) * 1.5))
        for row in rows[:n]:
            out[row.ticker] = cat
    return out


def clamp_pm_draft(
    pm: PMDraft,
    *,
    det_targets: dict[str, float],
    scoring: dict[str, object],
    max_positions: dict[str, int],
    excluded: list[str],
    nav_usd: float,
) -> SizingResult:
    """PM 제안 → 하드 클램프된 SizingResult (결정론 사이저와 동일 형식)."""
    rules = allocation_rules()
    bands = rules.sizing.bands
    g = rules.guardrails
    pool = eligible_pool(scoring, max_positions)
    excl = {t.upper() for t in excluded}
    notes: list[str] = []

    # 1) 풀 밖·제외 종목 제거 + 티커 중복 제거 (LLM 이 같은 종목 2번 내면 첫 항목만).
    #    카테고리는 pool 값(소문자)으로 정규화 — LLM 이 'LOW' 로 내도 매칭 유지.
    kept: list[Position] = []
    seen: set[str] = set()
    for p in pm.positions:
        key = p.ticker.upper()
        if p.ticker in pool and key not in seen and key not in excl:
            kept.append(p.model_copy(update={"category": pool[p.ticker]}))
            seen.add(key)
    kept_tickers = {p.ticker for p in kept}
    dropped = [p.ticker for p in pm.positions if p.ticker not in kept_tickers]
    if dropped:
        notes.append(f"PM 제안 중 풀밖/제외/중복 {len(dropped)}종목 제거: {', '.join(dropped[:6])}")

    positions: list[SizedPosition] = []
    for cat in _CATS:
        lo, hi = bands[cat]
        cap = min(hi, g.single_name_cap)
        cat_pos = sorted(
            (p for p in kept if p.category == cat), key=lambda p: p.weight, reverse=True
        )
        if not cat_pos:
            continue
        det = det_targets.get(cat, 0.0)
        raw_sum = sum(max(p.weight, 0.0) for p in cat_pos)
        # 2) 카테고리 예산: PM 제안합을 결정론 배분 ±3%p 로 클램프
        budget = min(max(raw_sum, det - _TILT_LIMIT, 0.0), det + _TILT_LIMIT)
        # 3) 예산이 담을 수 있는 종목 수 (하한 lo 기준) — 초과분은 PM 확신 낮은 순으로 컷
        n = max(1, min(len(cat_pos), int(budget / lo + 1e-9)))
        picks = cat_pos[:n]
        pick_sum = sum(max(p.weight, 0.0) for p in picks) or 1e-9
        if n < len(cat_pos) or abs(budget - raw_sum) > 1e-6:
            notes.append(
                f"{cat}: PM {len(cat_pos)}종목 {raw_sum:.3f} → {n}종목 {budget:.3f} "
                f"(결정론 {det:.3f} ±3%p)"
            )
        # 4) 종목별: PM 상대비중 → 예산 배분 → 밴드·단일종목캡 클램프
        ws = [min(cap, max(lo, max(p.weight, 0.0) / pick_sum * budget)) for p in picks]
        over = sum(ws) - budget
        if over > 1e-9:  # 하한 상향으로 예산 초과 → 비례 축소 (±3%p 불가침)
            ws = [max(0.0, w - over * w / sum(ws)) for w in ws]
        for p, w in zip(picks, ws, strict=True):
            positions.append(
                SizedPosition(
                    ticker=p.ticker,
                    category=cat,
                    weight=round(w, 6),
                    target_usd=round(w * nav_usd, 2),
                    score=0.0,
                    sector=p.sector,
                )
            )

    _enforce_caps(positions, g, nav_usd, notes)
    _enforce_sector_cap(positions, g.sector_cap, nav_usd, notes)  # 결정론 사이저와 동일 (불가침)
    cw = {c: round(sum(p.weight for p in positions if p.category == c), 6) for c in _CATS}
    cw["cash"] = round(max(g.cash_floor, 1.0 - sum(cw.values())), 6)
    return SizingResult(
        positions=positions, category_weights=cw, budget_shortfall={}, notes=notes, as_of=""
    )


def _enforce_caps(
    positions: list[SizedPosition], g: object, nav_usd: float, notes: list[str]
) -> None:
    """고위험 절대캡 초과 → 비례 축소. (현금 하한은 category_weights 계산에서.)"""
    cap = g.high_abs_cap  # type: ignore[attr-defined]
    high_sum = sum(p.weight for p in positions if p.category == "high")
    if high_sum > cap + 1e-9:
        scale = cap / high_sum
        for p in positions:
            if p.category == "high":
                p.weight = round(p.weight * scale, 6)
                p.target_usd = round(p.weight * nav_usd, 2)
        notes.append(f"PM 고위험 {high_sum:.1%} > {cap:.0%} → {scale:.2f}x 축소")


def _enforce_sector_cap(
    positions: list[SizedPosition], cap: float, nav_usd: float, notes: list[str]
) -> None:
    """섹터 합계 > cap → 비례 축소 (잔여 현금). portfolio_math._apply_sector_cap 과 동형."""
    by_sector: dict[str, float] = defaultdict(float)
    for p in positions:
        if p.sector:
            by_sector[p.sector] += p.weight
    for name, sw in by_sector.items():
        if sw > cap + 1e-9:
            scale = cap / sw
            for p in positions:
                if p.sector == name:
                    p.weight = round(p.weight * scale, 6)
                    p.target_usd = round(p.weight * nav_usd, 2)
            notes.append(f"PM 섹터 {name} {sw:.1%} > {cap:.0%} → {scale:.2f}x 축소")
