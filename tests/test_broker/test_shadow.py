"""broker/shadow.py — 섀도 A/B 비교."""

from __future__ import annotations

from aegisvest.broker.shadow import delta_report
from aegisvest.schemas import NavPoint, PaperPortfolio, ShadowState


def _pf(navs: list[float]) -> PaperPortfolio:
    return PaperPortfolio(
        history=[
            NavPoint(date=f"2026-01-{i + 1:02d}", nav_usd=v, nav_krw=v * 1400)
            for i, v in enumerate(navs)
        ]
    )


def test_insufficient_data() -> None:
    r = delta_report(ShadowState())
    assert r["verdict"] == "insufficient_data"


def test_org_helps() -> None:
    s = ShadowState(deterministic=_pf([100, 101, 102]), organization=_pf([100, 102, 105]))
    r = delta_report(s)
    assert r["verdict"] == "org_helps"
    assert isinstance(r["org_minus_det_pct"], float) and r["org_minus_det_pct"] > 0


def test_org_harmful() -> None:
    s = ShadowState(deterministic=_pf([100, 105, 110]), organization=_pf([100, 102, 103]))
    r = delta_report(s)
    assert r["verdict"] == "org_neutral_or_harmful"
