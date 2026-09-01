"""report.py — 주간 리포트 markdown + 성과 조회."""

from __future__ import annotations

from aegisvest import report, state
from aegisvest.schemas import (
    Contribution,
    ExecutionResult,
    Fill,
    NavPoint,
    PaperPortfolio,
)
from tests.fixtures.pipeline import make_pipeline_result


def test_weekly_report_executed() -> None:
    pr = make_pipeline_result()
    ex = ExecutionResult(
        fills=[
            Fill(
                ticker="L0",
                side="buy",
                shares=0.5,
                price_usd=100.0,
                commission_usd=0.05,
                notional_usd=50.0,
            )
        ],
        total_commission_usd=0.05,
        cash_after_usd=20.0,
        skipped=[],
    )
    md = report.weekly_report_md(
        pr, None, ex, held=False, contribution_usd=70.0, nav_usd=1000.0, nav_krw=1_400_000.0
    )
    assert "# 주간 리포트 — 2026-09-01" in md
    assert "BULL" in md and "L0" in md
    assert "✅ 실행" in md


def test_weekly_report_hold() -> None:
    pr = make_pipeline_result(crisis=True)
    md = report.weekly_report_md(
        pr, None, None, held=True, contribution_usd=0.0, nav_usd=900.0, nav_krw=1_260_000.0
    )
    assert "HOLD" in md
    assert "이번 주 주문 없음" in md


def test_write_run_creates_artifacts() -> None:
    pr = make_pipeline_result()
    md = "# test\n"
    path = report.write_run("2026-09-01", pr, None, None, md)
    assert path.exists() and path.name == "report.md"
    assert (path.parent / "pipeline.json").exists()


def test_performance_report_empty() -> None:
    assert "성과 데이터 없음" in report.performance_report_md()


def test_performance_report_with_history() -> None:
    pf = PaperPortfolio(
        cash_usd=0.0,
        contributions=[Contribution(date="2026-01-01", krw=140000, usd=100.0, fx_rate=1400.0)],
        history=[
            NavPoint(date=f"2026-01-{d:02d}", nav_usd=v, nav_krw=v * 1400)
            for d, v in [(1, 100.0), (2, 101.0), (3, 99.0), (4, 103.0)]
        ],
    )
    state.save_model("paper_portfolio.json", pf)
    md = report.performance_report_md()
    assert "성과 리포트" in md
    assert "총수익률" in md
