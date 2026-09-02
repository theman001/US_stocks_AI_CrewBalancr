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


def test_undated_item_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    rss = (
        '<?xml version="1.0"?><rss><channel>'
        "<item><title>No date here</title><link>https://x.test/9</link></item>"
        "<item><title>Dated recent</title>"
        "<pubDate>Wed, 02 Sep 2026 09:00:00 GMT</pubDate></item>"
        "</channel></rss>"
    )
    monkeypatch.setattr(nw, "cached_text", lambda url, **k: rss)
    titles = [h.title for h in nw.news_scraper("macro", days=7).headlines]  # type: ignore[union-attr]
    assert "No date here" not in titles  # 날짜 못 읽음 → 창 밖일 수 있어 제외
    assert "Dated recent" in titles


def test_dc_date_namespace_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    rss = (
        '<?xml version="1.0"?><rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>'
        "<item><title>DC dated</title>"
        "<dc:date>2026-09-01T10:00:00Z</dc:date></item>"
        "</channel></rss>"
    )
    monkeypatch.setattr(nw, "cached_text", lambda url, **k: rss)
    titles = [h.title for h in nw.news_scraper("macro", days=7).headlines]  # type: ignore[union-attr]
    assert "DC dated" in titles  # dc:date 폴백 인식


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


def test_ticker_without_ticker_arg() -> None:
    r = nw.news_scraper("ticker")
    assert isinstance(r, ToolError)
    assert r.field == "ticker"


def test_ticker_uses_google_news_rss(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake_text(url: str, **_k: Any) -> str:
        seen["url"] = url
        return _RSS

    monkeypatch.setattr(nw, "cached_text", fake_text)
    r = nw.news_scraper("ticker", ticker="aapl", days=30)
    assert isinstance(r, NewsResult)
    assert r.ticker == "AAPL"
    assert "AAPL%20stock" in seen["url"]
    assert r.headlines[0].title == "Fed holds rates steady"


def test_ticker_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> str:
        raise ConnectionError("down")

    monkeypatch.setattr(nw, "cached_text", boom)
    r = nw.news_scraper("ticker", ticker="AAPL")
    assert isinstance(r, ToolError)
    assert r.field == "network"
