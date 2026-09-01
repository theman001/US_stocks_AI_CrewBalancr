"""섀도 A/B — 순수 결정론 vs 에이전트 틸트 포트폴리오 병행 추적.

근거: report/phase-3 §1 (C), §7.3. 조직 틸트가 실제로 도움이 되는지 3~6개월 측정.
실행(execute/mark_to_market)은 파이프라인이 `paper` 로 각각 수행하고, 여기선 비교만.
3a 단계에선 organization 이 비어있고 deterministic = 실제 모의 포트폴리오.
"""

from __future__ import annotations

from aegisvest.broker.metrics import performance_stats
from aegisvest.schemas import ShadowState


def delta_report(shadow: ShadowState) -> dict[str, object]:
    """두 포트폴리오의 최신 NAV·성과 차이. organization - deterministic."""
    det, org = shadow.deterministic, shadow.organization
    det_nav = det.history[-1].nav_usd if det.history else None
    org_nav = org.history[-1].nav_usd if org.history else None

    det_stats = performance_stats(det.history, det.contributions)
    org_stats = performance_stats(org.history, org.contributions)

    nav_delta_pct = None
    if det_nav and org_nav and det_nav > 0:
        nav_delta_pct = round(org_nav / det_nav - 1.0, 4)

    return {
        "deterministic_nav_usd": det_nav,
        "organization_nav_usd": org_nav,
        "org_minus_det_pct": nav_delta_pct,
        "deterministic": det_stats,
        "organization": org_stats,
        "verdict": (
            "insufficient_data"
            if nav_delta_pct is None or abs(nav_delta_pct) < 1e-4  # 동일(크루 미실행) 포함
            else "org_helps"
            if nav_delta_pct > 0
            else "org_neutral_or_harmful"
        ),
    }
