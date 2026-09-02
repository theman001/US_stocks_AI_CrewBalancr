"""_derived.py — 파생 재무 지표 순수 함수."""

from __future__ import annotations

from aegisvest.tools import _derived as dv
from aegisvest.tools._derived import AnnualFinancials as AF


def _year(**kw: float) -> AF:
    base = dict(
        total_assets=1000.0,
        total_liabilities=400.0,
        current_assets=300.0,
        current_liabilities=200.0,
        long_term_debt=250.0,
        retained_earnings=500.0,
        stockholders_equity=600.0,
        shares_outstanding=100.0,
        revenue=800.0,
        gross_profit=400.0,
        ebit=150.0,
        net_income=100.0,
        operating_cash_flow=130.0,
    )
    base.update(kw)
    return AF(**base)  # type: ignore[arg-type]


def test_piotroski_perfect_improvement() -> None:
    y0 = _year(
        net_income=120,
        operating_cash_flow=160,
        current_assets=340,
        long_term_debt=200,
        gross_profit=440,
        revenue=820,
        shares_outstanding=98,
    )
    y1 = _year()
    f = dv.piotroski_f([y0, y1])
    assert f is not None and f >= 7


def test_piotroski_needs_two_years() -> None:
    assert dv.piotroski_f([_year()]) is None


def test_altman_z_healthy_company() -> None:
    z = dv.altman_z([_year()], market_cap=2000.0)
    assert z is not None and z > 3.0


def test_altman_z_fills_missing_from_prior_year() -> None:
    y0 = _year(retained_earnings=None)
    y1 = _year(retained_earnings=480.0)
    assert dv.altman_z([y0, y1], market_cap=2000.0) is not None


def test_altman_z_none_without_market_cap() -> None:
    assert dv.altman_z([_year()], market_cap=None) is None


def test_dividend_streak() -> None:
    divs = [(2019, 1.0), (2020, 1.1), (2021, 1.2), (2022, 1.3), (2023, 1.4)]
    assert dv.dividend_streak_years(divs) == 4
    reset = [(2019, 1.0), (2020, 1.1), (2021, 1.05), (2022, 1.2)]
    assert dv.dividend_streak_years(reset) == 1  # 2021 감소 → 리셋, 2022 증가


def test_dgr() -> None:
    divs = [(y, 1.0 * 1.05 ** (y - 2018)) for y in range(2018, 2025)]
    r = dv.dgr(divs, 5)
    assert r is not None and abs(r - 0.05) < 1e-6


def test_roic() -> None:
    r = dv.roic(_year(ebit=200.0, stockholders_equity=600.0, long_term_debt=200.0))
    assert r is not None and abs(r - 200.0 * 0.79 / 800.0) < 1e-6


def test_roic_approximates_ltd_from_liabilities_when_missing() -> None:
    # long_term_debt None → (total_liab 400 - current_liab 200) = 200 로 근사
    r = dv.roic(
        _year(ebit=200.0, stockholders_equity=600.0, long_term_debt=None)  # type: ignore[arg-type]
    )
    assert r is not None and abs(r - 200.0 * 0.79 / 800.0) < 1e-6
    # 부채 정보 자체가 없으면 부풀림 방지 위해 None (0 으로 대체 안 함)
    y = _year(ebit=200.0, stockholders_equity=600.0)
    y.long_term_debt = y.total_liabilities = y.current_liabilities = None
    assert dv.roic(y) is None


def test_piotroski_normalizes_partial_score() -> None:
    y0, y1 = _year(), _year()
    y0.gross_profit = y1.gross_profit = None  # 2개 항목 결측 → 7/9 resolvable
    y0.shares_outstanding = y1.shares_outstanding = None
    f = dv.piotroski_f([y0, y1])
    assert f is not None and 0 <= f <= 9  # partial(≤7) 아니라 정규화된 9점 척도


def test_dividend_streak_resets_on_year_gap() -> None:
    gapped = [(2018, 1.0), (2019, 1.1), (2021, 1.2), (2022, 1.3)]  # 2020 결측
    assert dv.dividend_streak_years(gapped) == 1  # 2019→2021 갭 → 리셋, 2021→2022 만 카운트


def test_mean_roe() -> None:
    years = [_year(net_income=n, stockholders_equity=1000.0) for n in (120, 100, 80)]
    assert dv.mean_roe(years) == (0.12 + 0.10 + 0.08) / 3
