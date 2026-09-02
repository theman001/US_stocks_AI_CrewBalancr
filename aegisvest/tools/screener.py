"""ScreenerTool — 카테고리별 하드 필터로 유니버스를 거른다. docs/TOOLS.md §6.

fundamentals() + market_data() 를 티커별로 병합해 config/filters/{cat}.yaml 을 적용한다.
HIGH 는 통과 후보군 내에서 RS 상위 30% 를 추가 컷.
"""

from __future__ import annotations

import datetime as dt
import logging

from aegisvest.rules import category_filters
from aegisvest.schemas import Category, FilterCheck, ScreenedTicker, ScreenResult, ToolError
from aegisvest.tools._screen import check_filter, merged_values
from aegisvest.tools.universe import get_universe

_log = logging.getLogger("aegisvest.screener")
_RS_TOP_FRAC = 0.30  # HIGH: RS 상위 30%
_RS_MIN_COVERAGE = 0.5  # RS 데이터가 통과 후보의 이 비율 미만이면 RS 컷 스킵 (일관성)


def screen(
    category: str, universe: str = "combined", limit: int | None = None
) -> ScreenResult | ToolError:
    """`category`: LOW|MID|HIGH. `limit`: 평가할 티커 수 상한 (레이트리밋 대응)."""
    cat = category.strip().upper()
    if cat not in {c.value for c in Category}:
        return ToolError(error=f"알 수 없는 카테고리: {category}", field="category")

    specs = category_filters(cat).hard_filters
    tickers = get_universe(universe)
    if not tickers:
        return ToolError(error=f"빈 유니버스: {universe}", field="universe")
    if limit is not None:
        tickers = tickers[:limit]

    passed: list[ScreenedTicker] = []
    errored: list[str] = []
    rs_by_ticker: dict[str, float] = {}
    as_of = dt.date.today().isoformat()

    for t in tickers:
        values = merged_values(t)
        if values is None:
            errored.append(t)
            continue
        as_of = values.get("as_of", as_of)
        checks = {s.field: check_filter(s, values) for s in specs}
        ok = all(c.result != "fail" for c in checks.values())
        passed.append(ScreenedTicker(ticker=t, passed=ok, checks=checks))
        if ok and values.get("rs_vs_spx_6m") is not None:
            rs_by_ticker[t] = float(values["rs_vs_spx_6m"])

    # HIGH: 통과 후보군 내 RS 상위 30% 만 유지.
    # RS 데이터 커버리지가 낮으면(SPX 조회 실패 등) 컷을 스킵 — "일부만 RS 있으면 RS 없는
    # 종목은 탈락, 아무도 없으면 전부 통과" 같은 데이터 의존 불일치 제거.
    if cat == "HIGH":
        n_passers = sum(1 for st in passed if st.passed)
        coverage = len(rs_by_ticker) / n_passers if n_passers else 0.0
        if coverage >= _RS_MIN_COVERAGE:
            ranked = sorted(rs_by_ticker.items(), key=lambda kv: kv[1], reverse=True)
            keep = {t for t, _ in ranked[: max(1, round(len(ranked) * _RS_TOP_FRAC))]}
            for st in passed:
                if st.passed and st.ticker not in keep:
                    st.passed = False
                    st.checks["rs_top30"] = FilterCheck(
                        result="fail", value=rs_by_ticker.get(st.ticker)
                    )
        elif n_passers:
            _log.warning("HIGH RS 커버리지 %.0f%% < 50%% — RS 상위 컷 스킵", coverage * 100)

    winners = [st for st in passed if st.passed]
    return ScreenResult(
        category=cat,
        passed=winners,
        failed_count=len(passed) - len(winners),
        evaluated_count=len(passed),
        errored=errored,
        as_of=as_of,
    )
