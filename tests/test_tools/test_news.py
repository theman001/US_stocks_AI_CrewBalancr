"""news.py — TEST_GUIDE 시나리오 1 (mock RSS/FMP)."""

from __future__ import annotations

from typing import Any

import pytest

from aegisvest.schemas import NewsResult, ToolError
from aegisvest.tools import news as nw

_RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Fed holds rates steady</title><link>https://x.test/1</link>
<pubDate>Mon, 01 Sep 2026 12:00:00 GMT</pubDate><description>desc</description></item>
<item><title>Old news</title><link>https://x.test/2</link>
<pubDate>Mon, 01 Jan 2020 12:00:00 GMT</pubDate><description>old</description></item>
</channel></rss>"""


def test_macro_parses_and_filters_old(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nw, "cached_text", lambda url, **k: _RSS)
    r = nw.news_scraper("macro", days=7)
    assert isinstance(r, NewsResult)
    titles = [h.title for h in r.headlines]
    assert "Fed holds rates steady" in titles
    assert "Old news" not in titles  # 컷오프 밖


def test_macro_all_feeds_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> str:
        raise ConnectionError("down")

    monkeypatch.setattr(nw, "cached_text", boom)
    r = nw.news_scraper("macro")
    assert isinstance(r, ToolError)
    assert r.field == "network"


def test_bad_scope() -> None:
    r = nw.news_scraper("weird")
    assert isinstance(r, ToolError)
    assert r.field == "scope"


def test_ticker_no_key() -> None:
    r = nw.news_scraper("ticker", ticker="AAPL")
    assert isinstance(r, ToolError)
    assert r.field == "FMP_API_KEY"


def test_ticker_without_ticker_arg() -> None:
    r = nw.news_scraper("ticker")
    assert isinstance(r, ToolError)
    assert r.field == "ticker"


def test_ticker_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "k")
    nw.get_settings.cache_clear()
    rows: list[dict[str, Any]] = [
        {
            "title": "AAPL beats",
            "site": "Reuters",
            "publishedDate": "2026-09-01 09:00:00",
            "url": "https://x.test/a",
            "text": "body",
        }
    ]
    monkeypatch.setattr(nw, "cached_json", lambda *a, **k: rows)
    r = nw.news_scraper("ticker", ticker="aapl", days=30)
    assert isinstance(r, NewsResult)
    assert r.ticker == "AAPL"
    assert r.headlines[0].source == "Reuters"
