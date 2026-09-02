"""MacroDataTool — 레짐 6축 raw 데이터. 소스: FRED + yfinance. docs/TOOLS.md §3.

시장 폭(pct_above_200dma)은 구성종목 가격이 필요하므로 3a-5에서 채운다 (현재 None).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from aegisvest.config import get_settings
from aegisvest.schemas import MacroData
from aegisvest.tools import indicators as ind
from aegisvest.tools._io import cached_json
from aegisvest.tools._prices import history

_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

# FRED series id. 지역 연준은 일부 없어도 나머지 평균.
_FRED_SERIES = {
    "t10y3m": "T10Y3M",  # 퍼센트
    "t10y2y": "T10Y2Y",  # 퍼센트
    "hy_oas": "BAMLH0A0HYM2",  # 퍼센트
    "dff": "DFF",  # 퍼센트
    "wei": "WEI",  # 퍼센트(연율 근사)
    "claims": "IC4WSA",  # 건수 (주간)
}
# 라이브 검증됨 (2026-09). KC/Richmond 는 FRED series id 확인 안 돼 제외 — 3개로 충분.
_REGIONAL_FED = {
    "empire": "GACDISA066MSFRBNY",  # NY Fed 일반활동
    "philly": "GACDFSA066MSFRBPHI",  # Philadelphia Fed 일반활동
    "dallas": "BACTSAMFRBDAL",  # Dallas Fed 일반활동
}


def _fred_series(series_id: str, key: str, limit: int = 300) -> pd.Series:
    """FRED 관측치 → 날짜 인덱스 float Series (오름차순). '.' 은 결측."""
    data: dict[str, Any] = cached_json(
        _FRED_URL,
        {
            "series_id": series_id,
            "api_key": key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        },
        ttl_hours=float(get_settings().cache_ttl_hours),
    )
    pairs = [
        (o["date"], o["value"])
        for o in data.get("observations", [])
        if o.get("value") not in (".", "", None)
    ]
    if not pairs:
        return pd.Series(dtype=float)
    return pd.Series(
        [float(v) for _, v in pairs], index=pd.to_datetime([d for d, _ in pairs])
    ).sort_index()


def _at(ser: pd.Series | None, n_back: int = 0) -> float | None:
    """뒤에서 n_back 번째 값 (0 = 최신)."""
    if ser is None or len(ser) <= n_back:
        return None
    return float(ser.iloc[-1 - n_back])


def _pct_change(ser: pd.Series | None, n_back: int) -> float | None:
    now, past = _at(ser, 0), _at(ser, n_back)
    if now is None or past is None or past == 0.0:
        return None
    return now / past - 1.0


@dataclass
class _Fred:
    series: dict[str, pd.Series] = field(default_factory=dict)
    stale: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)

    def load(self, key: str) -> None:
        for name, sid in {**_FRED_SERIES, **_REGIONAL_FED}.items():
            try:
                ser = _fred_series(sid, key)
            except Exception:
                self.stale.append(f"fred:{name}")
                continue
            if ser.empty:
                self.stale.append(f"fred:{name}")
            else:
                self.series[name] = ser
                self.dates.append(str(ser.index[-1].date()))

    def pp_to_bp(self, name: str, n_back: int = 0) -> float | None:
        """퍼센트포인트 → 베이시스포인트."""
        val = _at(self.series.get(name), n_back)
        return None if val is None else val * 100.0

    def fed_trend(self) -> str | None:
        dff = self.series.get("dff")
        # DFF 는 7일 일간(주말 포함) → ~6개월 = 180 관측치
        now, past = _at(dff, 0), _at(dff, 180)
        if now is None or past is None:
            return None
        diff = now - past  # 퍼센트포인트
        return "hiking" if diff > 0.10 else "cutting" if diff < -0.10 else "hold"

    def regional_avg(self) -> float | None:
        vals = [_at(self.series.get(n)) for n in _REGIONAL_FED]
        present = [v for v in vals if v is not None]
        return sum(present) / len(present) if present else None


@dataclass
class _Yf:
    vix: float | None = None
    vix3m: float | None = None
    vix_1d_change_pct: float | None = None
    spx_last: float | None = None
    spx_sma_50: float | None = None
    spx_sma_200: float | None = None
    spx_50_slope_20d: float | None = None
    stale: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)

    def load(self, ttl_hours: float) -> None:
        self._vix(ttl_hours)
        self._vix3m(ttl_hours)
        self._spx(ttl_hours)

    def _vix(self, ttl: float) -> None:
        try:
            h = history("^VIX", ttl)
        except Exception:
            self.stale.append("yf:vix")
            return
        if len(h) < 2:  # 빈/1행 프레임도 데이터 문제 — stale 로 표시
            self.stale.append("yf:vix")
            return
        self.vix = float(h["Close"].iloc[-1])
        prev = float(h["Close"].iloc[-2])
        self.vix_1d_change_pct = (self.vix / prev - 1.0) if prev else None
        self.dates.append(str(h.index[-1].date()))

    def _vix3m(self, ttl: float) -> None:
        try:
            h = history("^VIX3M", ttl)
        except Exception:
            self.stale.append("yf:vix3m")
            return
        if h.empty:
            self.stale.append("yf:vix3m")
            return
        self.vix3m = float(h["Close"].iloc[-1])

    def _spx(self, ttl: float) -> None:
        try:
            h = history("^GSPC", ttl)
        except Exception:
            self.stale.append("yf:spx")
            return
        if h.empty:
            self.stale.append("yf:spx")
            return
        c = h["Close"]
        self.spx_last = float(c.iloc[-1])
        self.spx_sma_50 = ind.sma(c, 50)
        self.spx_sma_200 = ind.sma(c, 200)
        sma50_20ago = ind.sma_prev(c, 50, back=20)
        if self.spx_sma_50 is not None and sma50_20ago:
            self.spx_50_slope_20d = self.spx_sma_50 / sma50_20ago - 1.0
        self.dates.append(str(c.index[-1].date()))


def macro_data() -> MacroData:
    """레짐 판별용 매크로 raw 데이터. 부분 실패 시 해당 필드 None + stale_fields."""
    s = get_settings()
    fred = _Fred()
    if s.fred_api_key:
        fred.load(s.fred_api_key)
    else:
        fred.stale.append("fred:no_api_key")

    yf = _Yf()
    yf.load(float(s.cache_ttl_hours))

    yc_now = fred.pp_to_bp("t10y3m")
    yc_20 = fred.pp_to_bp("t10y3m", 20)
    hy_now = fred.pp_to_bp("hy_oas")
    hy_20 = fred.pp_to_bp("hy_oas", 20)
    dates = fred.dates + yf.dates

    return MacroData(
        vix=yf.vix,
        vix3m=yf.vix3m,
        vix_1d_change_pct=yf.vix_1d_change_pct,
        spx_last=yf.spx_last,
        spx_sma_200=yf.spx_sma_200,
        spx_sma_50=yf.spx_sma_50,
        spx_50_slope_20d=yf.spx_50_slope_20d,
        pct_above_200dma=None,  # 3a-5
        pct_above_200dma_4w_change=None,  # 3a-5
        yc_10y_3m_bp=yc_now,
        yc_10y_3m_4w_change_bp=(
            yc_now - yc_20 if yc_now is not None and yc_20 is not None else None
        ),
        yc_10y_3m_prev_bp=fred.pp_to_bp("t10y3m", 1),
        yc_10y_2y_bp=fred.pp_to_bp("t10y2y"),
        fed_funds_trend=fred.fed_trend(),
        hy_oas_bp=hy_now,
        hy_oas_4w_change_bp=(hy_now - hy_20 if hy_now is not None and hy_20 is not None else None),
        wei=_at(fred.series.get("wei")),
        regional_fed_mfg_avg=fred.regional_avg(),
        claims_4w_trend_pct=_pct_change(fred.series.get("claims"), 13),  # ~3개월 (주간)
        ism_pmi=s.manual_ism_pmi,
        as_of=max(dates) if dates else dt.date.today().isoformat(),
        stale_fields=fred.stale + yf.stale,
    )
