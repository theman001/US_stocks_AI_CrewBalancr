"""리포트 조립 — 주간 매매 리포트(markdown) + 성과 조회 CLI. 근거: report/phase-2 §7, phase-3 §7.3.

`python -m aegisvest.report performance` — CAGR/MDD/변동성/샤프/소르티노 + 벤치 3종 + 섀도 A/B.
전체 리포트는 outputs/runs/<run_id>/ 에 저장, Mattermost 엔 요약만.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from aegisvest.broker.benchmarks import BENCHMARKS
from aegisvest.broker.metrics import performance_stats
from aegisvest.broker.shadow import delta_report
from aegisvest.config import get_settings
from aegisvest.schemas import (
    BenchmarkState,
    CrewOutcome,
    ExecutionResult,
    PaperPortfolio,
    PipelineResult,
    ShadowState,
)
from aegisvest.state import load_model


def _run_dir(run_id: str) -> Path:
    d = get_settings().output_dir / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def weekly_report_md(
    pr: PipelineResult,
    crew: CrewOutcome | None,
    execution: ExecutionResult | None,
    *,
    held: bool,
    contribution_usd: float,
    nav_usd: float,
    nav_krw: float,
) -> str:
    rg = pr.regime
    lines = [
        f"# 주간 리포트 — {pr.as_of}",
        "",
        f"- **레짐**: {rg.regime.value} (score {rg.total_score}, smooth {rg.score_smooth:.1f})"
        + (" · 🆘 CRISIS" if rg.crisis_active else ""),
        f"- **NAV**: ${nav_usd:,.2f} / ₩{nav_krw:,.0f}"
        + (f"  (이번 납입 ${contribution_usd:,.2f})" if contribution_usd else ""),
        f"- **제약 검증**: {pr.constraints.verdict}",
        f"- **의사결정**: {'⛔ HOLD (매매 보류)' if held else '✅ 실행'}"
        + (f" — CIO: {crew.cio.verdict}" if crew else " — 크루 미실행"),
        "",
        "## 목표 배분 (전체 포트 %)",
    ]
    for c in ("low", "mid", "high"):
        t = pr.allocation.category_targets_total.get(c, 0.0)
        w = pr.draft.category_weights.get(c, 0.0)
        lines.append(f"- {c}: 목표 {_pct(t)} / 초안 {_pct(w)}")
    lines.append(f"- cash: {_pct(pr.draft.category_weights.get('cash', 0.0))}")

    lines += ["", "## 주문", ""]
    if held:
        lines.append("_HOLD — 이번 주 주문 없음._")
    elif execution and execution.fills:
        lines.append("| 티커 | 방향 | 수량 | 체결가 | 금액 | 수수료 |")
        lines.append("|---|---|---|---|---|---|")
        for f in execution.fills:
            lines.append(
                f"| {f.ticker} | {f.side} | {f.shares:.4f} | ${f.price_usd:.2f} "
                f"| ${f.notional_usd:.2f} | ${f.commission_usd:.3f} |"
            )
        if execution.skipped:
            lines.append("")
            lines.append(f"_체결 스킵: {', '.join(execution.skipped)}_")
    else:
        lines.append("_체결 없음._")

    if crew:
        lines += ["", "## 조직 노트", "", *_crew_notes(pr, crew)]

    if pr.notes:
        lines += ["", "## 파이프라인 노트", *[f"- {n}" for n in pr.notes]]
    return "\n".join(lines) + "\n"


def _crew_notes(pr: PipelineResult, crew: CrewOutcome) -> list[str]:
    mb, rv = crew.macro_brief, crew.research_view
    out = [
        f"**Macro Strategist** ({mb.confidence}): " + "; ".join(mb.risk_scenarios[:3]),
        f"**News & Sentiment**: {crew.market_narrative.weekly_summary}",
        *[
            f"- 이벤트: {e.event} ({e.affected_sleeve}, {e.severity})"
            for e in crew.market_narrative.event_risks
        ],
        "**Research Director**: 슬리브 스탠스 ["
        + ", ".join(f"{k} {v.stance}" for k, v in rv.sleeve_stance.items())
        + "]",
        *(
            [f"- 제외 권고(비강제): {', '.join(rv.excluded_tickers)}"]
            if rv.excluded_tickers
            else []
        ),
        *[f"- 교차 리스크: {r}" for r in rv.cross_risks],
    ]
    if crew.pm_draft is not None:
        det = pr.draft.category_weights
        tilt = ", ".join(
            f"{c} {(crew.pm_draft.category_weights.get(c, 0.0) - det.get(c, 0.0)) * 100:+.1f}%p"
            for c in ("low", "mid", "high")
        )
        out.append(f"**Portfolio Manager**: 틸트 [{tilt}] (클램프 후)")
    if crew.risk_review is not None:
        rr = crew.risk_review
        out.append(
            f"**Risk Officer** ({rr.verdict}, {crew.risk_rounds}R): " + "; ".join(rr.concerns)
        )
    out.append(f"**CIO** ({crew.cio.verdict}): {crew.cio.ic_memo}")
    if crew.rebalance_held:
        out.append("- ⛔ 이번 주 리밸런싱 보류")
    if crew.cio.hold_reason:
        out.append(f"- HOLD 사유: {crew.cio.hold_reason}")
    return out


def mattermost_summary(
    pr: PipelineResult, crew: CrewOutcome | None, *, held: bool, nav_usd: float, n_fills: int
) -> str:
    rg = pr.regime
    head = "🆘 " if rg.crisis_active else "📊 "
    verdict = crew.cio.verdict if crew else "크루없음"
    return (
        f"{head}**주간 리포트 {pr.as_of}** · 레짐 {rg.regime.value} "
        f"(smooth {rg.score_smooth:.1f}) · NAV ${nav_usd:,.0f} · "
        f"{'HOLD' if held else f'{n_fills} 체결'} · CIO {verdict} · 제약 {pr.constraints.verdict}"
    )


def write_run(
    run_id: str,
    pr: PipelineResult,
    crew: CrewOutcome | None,
    execution: ExecutionResult | None,
    report_md: str,
) -> Path:
    d = _run_dir(run_id)
    (d / "report.md").write_text(report_md, encoding="utf-8")
    (d / "pipeline.json").write_text(pr.model_dump_json(indent=2), encoding="utf-8")
    if crew is not None:
        (d / "crew.json").write_text(crew.model_dump_json(indent=2), encoding="utf-8")
    if execution is not None:
        (d / "execution.json").write_text(execution.model_dump_json(indent=2), encoding="utf-8")
    return d / "report.md"


# ─────────────────────── 성과 조회 ───────────────────────


def performance_report_md() -> str:
    pf = load_model("paper_portfolio.json", PaperPortfolio)
    if pf is None or not pf.history:
        return "성과 데이터 없음 (모의투자 미시작)."
    strat = performance_stats(pf.history, pf.contributions)
    lines = [
        "# 성과 리포트",
        "",
        f"- 관측일수 {strat['n_days']} · 총수익률 {_fmt_pct(strat['total_return'])}",
        f"- CAGR {_fmt_pct(strat['cagr'])} · MDD {_fmt_pct(strat['mdd'])}"
        f" · 변동성 {_fmt_pct(strat['vol'])}",
        f"- 샤프 {_fmt(strat['sharpe'])} · 소르티노 {_fmt(strat['sortino'])}",
        "",
        "## 벤치마크",
    ]
    bench = load_model("benchmarks.json", BenchmarkState)
    for name in BENCHMARKS:
        hist = (bench.history.get(name) if bench else None) or []
        if hist:
            b = performance_stats(hist)
            lines.append(
                f"- {name}: 총수익 {_fmt_pct(b['total_return'])} · MDD {_fmt_pct(b['mdd'])}"
            )
        else:
            lines.append(f"- {name}: 데이터 없음")

    shadow = load_model("shadow.json", ShadowState)
    if shadow is not None:
        d = delta_report(shadow)
        lines += ["", "## 섀도 A/B (결정론 vs 조직)", f"- 판정: {d['verdict']}"]
        if d.get("org_minus_det_pct") is not None:
            lines.append(f"- 조직 vs 결정론: {_fmt_pct(d['org_minus_det_pct'])}")
    return "\n".join(lines) + "\n"


def _fmt(x: Any) -> str:
    return "—" if x is None else f"{x:.3f}"


def _fmt_pct(x: Any) -> str:
    return "—" if x is None else f"{x * 100:.2f}%"


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "performance"
    if arg == "performance":
        print(performance_report_md())
    elif arg == "last":
        runs = sorted((get_settings().output_dir / "runs").glob("*/report.md"))
        print(runs[-1].read_text(encoding="utf-8") if runs else "리포트 없음")
    else:
        print(json.dumps({"error": f"알 수 없는 명령: {arg}", "usage": "performance | last"}))
        sys.exit(2)


if __name__ == "__main__":
    main()
