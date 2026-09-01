"""스크리너·스코어러 공용 — 티커별 지표 병합 + 필터 평가."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aegisvest.rules import FilterSpec
from aegisvest.schemas import FilterCheck, ToolError
from aegisvest.tools.fundamentals import fundamentals
from aegisvest.tools.market_data import market_data

_OPS: dict[str, Callable[[Any, Any], Any]] = {
    ">=": lambda v, t: v >= t,
    "<=": lambda v, t: v <= t,
    ">": lambda v, t: v > t,
    "<": lambda v, t: v < t,
    "ne": lambda v, t: v != t,
    "in": lambda v, t: v in t,
    "between": lambda v, t: t[0] <= v <= t[1],
}


def apply_op(op: str, v: Any, target: Any) -> bool:
    fn = _OPS.get(op)
    if fn is None:
        msg = f"알 수 없는 op: {op}"
        raise ValueError(msg)
    return bool(fn(v, target))


def check_filter(spec: FilterSpec, values: dict[str, Any]) -> FilterCheck:
    v = values.get(spec.field)
    if v is None:
        return FilterCheck(result="skip" if spec.optional else "fail", value=None)
    target: Any = values.get(spec.ref) if spec.ref else spec.value
    if target is None:
        return FilterCheck(result="skip" if spec.optional else "fail", value=v)
    try:
        ok = apply_op(spec.op, v, target)
    except TypeError:  # config 타입 불일치 — 크래시 대신 skip
        return FilterCheck(result="skip", value=None)
    return FilterCheck(result="pass" if ok else "fail", value=v if isinstance(v, str) else float(v))


def merged_values(ticker: str) -> dict[str, Any] | None:
    """fundamentals + market_data 를 하나의 dict 로. 펀더멘털 실패 시 None."""
    f = fundamentals(ticker)
    if isinstance(f, ToolError):
        return None
    values = f.model_dump()
    m = market_data(ticker)
    if not isinstance(m, ToolError):
        values.update(m.model_dump())
    return values
