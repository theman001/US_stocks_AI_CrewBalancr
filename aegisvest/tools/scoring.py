"""ScoringCalculator — 후보군을 percentile rank 정규화 + 가중합으로 스코어링. docs/TOOLS.md §7.

metric 을 후보군 내에서 순위화(0~1) → direction 적용 → component 평균 → weight*component 합 *100.
결측 metric 은 중립 0.5. `theme_strength` 는 Thematic Analyst(3b) 가 overrides 로 주입.
"""

from __future__ import annotations

import datetime as dt
from bisect import bisect_right
from typing import Any

from aegisvest.rules import ScoringComponent, category_scoring
from aegisvest.schemas import Category, ScoredTicker, ScoringResult, ToolError
from aegisvest.tools._screen import check_filter, merged_values

_NEUTRAL = 0.5


def _add_derived(v: dict[str, Any], theme: float) -> None:
    pe, pe5 = v.get("pe_ttm"), v.get("pe_5y_median")
    v["pe_vs_5y_median"] = pe / pe5 if pe and pe5 and pe5 > 0 else None
    dy, dy5 = v.get("div_yield"), v.get("div_yield_5y_median")
    v["div_yield_vs_5y"] = dy / dy5 if dy and dy5 and dy5 > 0 else None
    s50, s200 = v.get("sma_50"), v.get("sma_200")
    v["sma_50_200_ratio"] = s50 / s200 if s50 and s200 and s200 > 0 else None
    v["theme_strength"] = theme


def _percentile(sorted_vals: list[float], x: float) -> float:
    return bisect_right(sorted_vals, x) / len(sorted_vals)


def _component_score(
    comp: ScoringComponent, ticker_vals: dict[str, Any], ranks: dict[str, list[float]]
) -> float:
    parts: list[float] = []
    for metric, direction in zip(comp.metrics, comp.directions, strict=True):
        x = ticker_vals.get(metric)
        if x is None:
            parts.append(_NEUTRAL)
            continue
        if comp.llm_fed:  # 이미 0~1 스코어 (Thematic Analyst) — percentile 안 씀
            parts.append(max(0.0, min(1.0, float(x))))
            continue
        pool = ranks.get(metric, [])
        if not pool:
            parts.append(_NEUTRAL)
            continue
        pct = _percentile(pool, float(x))
        parts.append(pct if direction >= 0 else 1.0 - pct)
    return sum(parts) / len(parts) if parts else _NEUTRAL


def _subtier(cat: str, values: dict[str, Any]) -> str | None:
    for rule in category_scoring(cat).subtiers:
        if all(check_filter(f, values).result == "pass" for f in rule.filters):
            return rule.name
    return None


def score_category(
    category: str,
    tickers: list[str],
    theme_strength_overrides: dict[str, float] | None = None,
) -> ScoringResult | ToolError:
    """`tickers` (스크리너 통과 티커) 를 스코어링. HIGH 는 theme_strength_overrides 참고."""
    cat = category.strip().upper()
    if cat not in {c.value for c in Category}:
        return ToolError(error=f"알 수 없는 카테고리: {category}", field="category")
    if not tickers:
        return ToolError(error="빈 티커 리스트", field="tickers")

    cfg = category_scoring(cat)
    overrides = theme_strength_overrides or {}
    rows: dict[str, dict[str, Any]] = {}
    errored: list[str] = []
    as_of = dt.date.today().isoformat()

    for t in tickers:
        v = merged_values(t)
        if v is None:
            errored.append(t)
            continue
        _add_derived(v, overrides.get(t, _NEUTRAL))
        rows[t] = v
        as_of = v.get("as_of", as_of)

    if not rows:
        return ToolError(error="스코어링 가능한 티커 없음", field="tickers")

    all_metrics = {m for c in cfg.components for m in c.metrics}
    ranks: dict[str, list[float]] = {
        m: sorted(float(v[m]) for v in rows.values() if v.get(m) is not None) for m in all_metrics
    }

    scored: list[ScoredTicker] = []
    for t, v in rows.items():
        comps = {c.name: _component_score(c, v, ranks) for c in cfg.components}
        total = 100.0 * sum(c.weight * comps[c.name] for c in cfg.components)
        scored.append(
            ScoredTicker(
                ticker=t,
                score=round(total, 2),
                rank=0,
                subtier=_subtier(cat, v),
                component_scores={k: round(x, 3) for k, x in comps.items()},
            )
        )

    scored.sort(key=lambda s: s.score, reverse=True)
    for i, s in enumerate(scored, 1):
        s.rank = i
    return ScoringResult(category=cat, scores=scored, errored=errored, as_of=as_of)
