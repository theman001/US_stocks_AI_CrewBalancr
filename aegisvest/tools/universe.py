"""투자 유니버스 조회. FMP 구성종목 엔드포인트 → 없으면 config/universe/*.txt 폴백.

정확한 시점별 명단이 필요한 백테스트는 Sharadar (report/phase-2 §8).
"""

from __future__ import annotations

from aegisvest.config import CONFIG_DIR, get_settings
from aegisvest.tools._io import cached_json

# FMP stable 구성종목 엔드포인트는 프리미엄(402) — 무료 티어는 항상 파일 폴백.
_FMP = "https://financialmodelingprep.com/stable"
_ENDPOINT = {"SP500": "sp500-constituent", "NASDAQ100": "nasdaq-constituent"}
_FILE = {"SP500": "sp500.txt", "NASDAQ100": "nasdaq100.txt"}


def _from_file(name: str) -> list[str]:
    path = CONFIG_DIR / "universe" / _FILE[name]
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.split("#", 1)[0].strip().upper()
        if t:
            out.append(t)
    return out


def _from_fmp(name: str, key: str) -> list[str]:
    data = cached_json(
        f"{_FMP}/{_ENDPOINT[name]}",
        {"apikey": key},
        ttl_hours=168.0,  # 주간
    )
    return [row["symbol"].upper() for row in data or [] if row.get("symbol")]


def get_universe(name: str = "combined") -> list[str]:
    """`name`: SP500 | NASDAQ100 | combined. 중복 제거, 정렬된 티커 리스트."""
    name = name.strip().upper()
    parts = ["SP500", "NASDAQ100"] if name == "COMBINED" else [name]
    if any(p not in _FILE for p in parts):
        return []

    key = get_settings().fmp_api_key
    tickers: set[str] = set()
    for p in parts:
        got: list[str] = []
        if key:
            try:
                got = _from_fmp(p, key)
            except Exception:
                got = []
        tickers.update(got or _from_file(p))
    return sorted(tickers)
