"""NewsScraperTool — 헤드라인 스크랩. 전부 무료 RSS (Google News / Yahoo). docs/TOOLS.md §11.

FMP 뉴스 엔드포인트는 무료 티어에서 제한(402/404) → 종목 뉴스도 Google News RSS.
스크랩만 한다. 요약·해석·이벤트 판단은 에이전트의 몫.
"""

from __future__ import annotations

import datetime as dt
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from xml.etree import ElementTree as ET

from aegisvest.config import get_settings
from aegisvest.schemas import NewsItem, NewsResult, ToolError
from aegisvest.tools._io import cached_text

_MACRO_FEEDS = [
    "https://news.google.com/rss/search?q=%22federal%20reserve%22%20OR%20FOMC%20OR%20"
    "inflation%20OR%20%22jobs%20report%22%20OR%20%22S%26P%20500%22&hl=en-US&gl=US&ceid=US:en",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US",
]
_UA = {"User-Agent": "Mozilla/5.0 (AegisVest news scraper)"}


def _google_news_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"


def _parse_date(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError):
        try:
            return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return ""


def _parse_rss(xml_text: str, source: str, cutoff: dt.date) -> list[NewsItem]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items: list[NewsItem] = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        published = _parse_date(it.findtext("pubDate"))
        if published and dt.date.fromisoformat(published) < cutoff:
            continue
        items.append(
            NewsItem(
                title=title,
                source=source,
                published=published,
                url=(it.findtext("link") or "").strip(),
                summary=(it.findtext("description") or "").strip()[:500],
            )
        )
    return items


def _macro_headlines(days: int, ttl: float) -> tuple[list[NewsItem], int]:
    cutoff = dt.date.today() - dt.timedelta(days=days)
    out: list[NewsItem] = []
    failures = 0
    for url in _MACRO_FEEDS:
        try:
            xml_text = cached_text(url, ttl_hours=ttl, headers=_UA)
        except Exception:
            failures += 1
            continue
        source = "Google News" if "google" in url else "Yahoo Finance"
        out.extend(_parse_rss(xml_text, source, cutoff))
    return out, failures


def _scrape_ticker(ticker: str | None, days: int, ttl: float, today: str) -> NewsResult | ToolError:
    if not ticker:
        return ToolError(error="scope='ticker' 인데 ticker 없음", field="ticker")
    sym = ticker.strip().upper()
    cutoff = dt.date.today() - dt.timedelta(days=days)
    try:
        xml_text = cached_text(_google_news_url(f"{sym} stock"), ttl_hours=ttl, headers=_UA)
    except Exception as exc:
        return ToolError(error=f"종목 뉴스 조회 실패: {exc}", field="network")
    items = _dedup(_parse_rss(xml_text, "Google News", cutoff))
    items.sort(key=lambda x: x.published, reverse=True)
    return NewsResult(scope="ticker", ticker=sym, headlines=items, as_of=today)


def _dedup(items: list[NewsItem]) -> list[NewsItem]:
    """제목 앞 60자 기준 중복 제거 (피드 간 겹침)."""
    seen: set[str] = set()
    out: list[NewsItem] = []
    for it in items:
        norm = it.title.lower().strip()[:60]
        if norm and norm not in seen:
            seen.add(norm)
            out.append(it)
    return out


def _scrape_macro(days: int, ttl: float, today: str) -> NewsResult | ToolError:
    items, failures = _macro_headlines(days, ttl)
    if failures == len(_MACRO_FEEDS):
        return ToolError(error="모든 매크로 피드 조회 실패", field="network")
    items.sort(key=lambda x: x.published, reverse=True)
    return NewsResult(scope="macro", ticker=None, headlines=_dedup(items), as_of=today)


def news_scraper(
    scope: str = "macro", ticker: str | None = None, days: int = 7
) -> NewsResult | ToolError:
    """`scope`='macro' -> RSS 헤드라인, 'ticker' -> FMP 종목 뉴스."""
    ttl = min(float(get_settings().cache_ttl_hours), 6.0)  # 뉴스는 더 자주 갱신
    today = dt.date.today().isoformat()
    if scope == "ticker":
        return _scrape_ticker(ticker, days, ttl, today)
    if scope == "macro":
        return _scrape_macro(days, ttl, today)
    return ToolError(error=f"알 수 없는 scope: {scope}", field="scope")
