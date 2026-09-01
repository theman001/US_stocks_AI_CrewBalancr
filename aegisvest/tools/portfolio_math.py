"""PositionSizer — 카테고리 예산 → 종목별 목표 비중. docs/TOOLS.md §10.

근거: report/phase-1 §B-3.1 (2026-09-01 확정).
- 저·중위험: 균등가중. 스코어는 편입 커트라인(상위 N)만 결정.
- 고위험: ATR14 역가중 (변동성 큰 종목 -> 작은 포지션, 손절 시 달러손실 균등).
- 둘 다 티어 밴드로 클램프 후 잔여 재분배. 편입 수 N = min(예산/하한, max_positions, 후보수).
- 고위험 예산 미달분은 중위험에 스필 (config: underfill_spill_to). 나머지 미달·섹터캡 초과분은 현금.

숫자만 산출 — LLM 관여 0. 예외 raise 안 함 (ToolError 반환).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from statistics import median

from aegisvest.rules import allocation_rules
from aegisvest.schemas import ScoredTicker, SizedPosition, SizingResult, ToolError
from aegisvest.tools.fundamentals import fundamentals
from aegisvest.tools.market_data import market_data

_CATS = ("low", "mid", "high")
_EPS = 1e-9


def _clamp_redistribute(weights: list[float], lo: float, hi: float, budget: float) -> list[float]:
    """각 비중을 [lo, hi] 로 클램프하고 잔여(budget - 합)를 여유 있는 종목에 균등 분배."""
    w = [min(hi, max(lo, x)) for x in weights]
    for _ in range(5):  # ponytail: 고정 5회면 실무 규모(<=20종목)에서 수렴
        diff = budget - sum(w)
        if abs(diff) < _EPS:
            break
        idx = [
            i
            for i in range(len(w))
            if (diff > 0 and w[i] < hi - _EPS) or (diff < 0 and w[i] > lo + _EPS)
        ]
        if not idx:
            break
        share = diff / len(idx)
        for i in idx:
            w[i] = min(hi, max(lo, w[i] + share))
    return w


def _atr_pct(tickers: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for t in tickers:
        md = market_data(t)
        if isinstance(md, ToolError) or md.atr_14 is None or md.last_price <= 0:
            continue
        out[t] = md.atr_14 / md.last_price
    return out


def _sectors(tickers: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for t in tickers:
        f = fundamentals(t)
        out[t] = None if isinstance(f, ToolError) else f.sector
    return out


def _high_raw_weights(
    picks: list[ScoredTicker], budget: float, atr_pct: dict[str, float]
) -> list[float]:
    """ATR% 역비례. 누락 종목은 중앙값 대체. 전부 누락이면 균등."""
    if not atr_pct:
        return [budget / len(picks)] * len(picks)
    med = median(atr_pct.values())
    inv = [1.0 / max(atr_pct.get(p.ticker, med), 1e-4) for p in picks]
    s = sum(inv)
    return [budget * x / s for x in inv]


def _size_category(
    cat: str,
    budget: float,
    pool: list[ScoredTicker],
    max_n: int,
    band: list[float],
    *,
    atr_inverse: bool,
) -> tuple[list[SizedPosition], float, str | None]:
    """한 카테고리를 사이징. 반환: (포지션[가중치만], 미달분, note)."""
    lo, hi = band
    if max_n < 1 or not pool:
        return [], budget, None
    n = max(1, min(int(budget / lo + _EPS), max_n, len(pool)))
    picks = pool[:n]

    atr_pct: dict[str, float] = {}
    note: str | None = None
    if cat == "high" and atr_inverse:
        atr_pct = _atr_pct([p.ticker for p in picks])
        raw = _high_raw_weights(picks, budget, atr_pct)
        if not atr_pct:
            note = "high: ATR 조회 실패 전종목 -> 균등가중 폴백"
    else:
        raw = [budget / n] * n

    weights = _clamp_redistribute(raw, lo, hi, budget)
    sized = [
        SizedPosition(
            ticker=p.ticker,
            category=cat,
            weight=round(w, 6),
            target_usd=0.0,
            score=p.score,
            atr_pct=round(atr_pct[p.ticker], 4) if p.ticker in atr_pct else None,
        )
        for p, w in zip(picks, weights, strict=True)
    ]
    return sized, budget - sum(weights), note


def size_positions(
    category_targets: dict[str, float],
    scored: dict[str, list[ScoredTicker]],
    max_positions: dict[str, int],
    nav_usd: float = 0.0,
    *,
    sector: dict[str, str | None] | None = None,
    as_of: str | None = None,
) -> SizingResult | ToolError:
    """`category_targets`: low/mid/high 전체 포트 목표 비중 (소수).
    `scored`: 카테고리별 스코어 내림차순. `max_positions`: allocation_targets 산출값.
    `sector`: ticker -> 섹터 오버라이드 (미지정 시 fundamentals 조회 — 섹터캡 검증용).
    """
    if not all(c in category_targets for c in _CATS):
        return ToolError(error="category_targets 에 low/mid/high 필요", field="category_targets")

    rules = allocation_rules()
    bands = {k: list(v) for k, v in rules.sizing.bands.items()}
    spill_to = rules.sizing.underfill_spill_to
    atr_inverse = rules.sizing.high_atr_inverse
    sec = dict(sector or {})

    positions: list[SizedPosition] = []
    notes: list[str] = []
    shortfall: dict[str, float] = {}
    spill = 0.0

    # 고위험 먼저 (미달분을 spill_to 예산에 가산). 이후 low, mid.
    for cat in ("high", "low", "mid"):
        band = bands[cat]
        budget = category_targets.get(cat, 0.0) + (spill if cat == spill_to else 0.0)
        pool = scored.get(cat, [])

        if budget < band[0] - _EPS or not pool:
            if budget > _EPS:
                shortfall[cat] = round(shortfall.get(cat, 0.0) + budget, 6)
                notes.append(f"{cat}: 예산 {budget:.4f} < 하한 {band[0]} 또는 후보 없음 -> 현금")
            continue

        sized, gap, note = _size_category(
            cat, budget, pool, max_positions.get(cat, len(pool)), band, atr_inverse=atr_inverse
        )
        positions.extend(sized)
        if note:
            notes.append(note)
        if gap > 1e-6:
            if cat == "high":
                spill += gap
                notes.append(f"high: {gap:.4f} 미달 -> {spill_to} 로 스필")
            else:
                shortfall[cat] = round(shortfall.get(cat, 0.0) + gap, 6)
                notes.append(f"{cat}: {gap:.4f} 미달 (상한/후보 부족) -> 현금")

    _fill_sectors(positions, sec)
    _apply_sector_cap(positions, rules.guardrails.sector_cap, notes)
    positions = [p for p in positions if p.weight > 1e-5]  # 섹터 축소로 0 된 종목 제거
    for p in positions:
        p.target_usd = round(p.weight * nav_usd, 2)

    cw = {c: round(sum(p.weight for p in positions if p.category == c), 6) for c in _CATS}
    cw["cash"] = round(max(0.0, 1.0 - sum(cw.values())), 6)

    return SizingResult(
        positions=positions,
        category_weights=cw,
        budget_shortfall=shortfall,
        notes=notes,
        as_of=as_of or dt.date.today().isoformat(),
    )


def _fill_sectors(positions: list[SizedPosition], override: dict[str, str | None]) -> None:
    for p in positions:
        p.sector = override.get(p.ticker, p.sector)
    missing = [p.ticker for p in positions if p.sector is None]
    if missing:
        looked_up = _sectors(missing)
        for p in positions:
            if p.sector is None:
                p.sector = looked_up.get(p.ticker)


def _apply_sector_cap(positions: list[SizedPosition], cap: float, notes: list[str]) -> None:
    """섹터 합이 캡 초과면 그 섹터 비중을 비례 축소 (잔여 현금). ponytail: 타 종목 재분배 안 함."""
    by_sector: dict[str, float] = defaultdict(float)
    for p in positions:
        if p.sector:
            by_sector[p.sector] += p.weight
    for name, sw in by_sector.items():
        if sw > cap + _EPS:
            scale = cap / sw
            for p in positions:
                if p.sector == name:
                    p.weight = round(p.weight * scale, 6)
            notes.append(f"sector {name} {sw:.1%} > {cap:.0%} -> {scale:.2f}x 축소, 잔여 현금")
