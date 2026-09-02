"""CrewAI 툴 래퍼 — Layer 0 순수 함수를 에이전트가 호출 가능하게. 근거: add-tool 스킬.

툴은 ①Macro ②Fund ③Thematic ⑨Reviewer 만 사용 (docs/PROMPTS.md 규칙 5).
숫자 생성은 여전히 순수 함수 몫 — 래퍼는 JSON 직렬화만. 예외 삼켜서 문자열 반환.
"""

from __future__ import annotations

from crewai.tools import tool

from aegisvest.schemas import ToolError
from aegisvest.tools.fundamentals import fundamentals
from aegisvest.tools.market_data import market_data
from aegisvest.tools.news import news_scraper


def _dump(result: object) -> str:
    if isinstance(result, ToolError):
        return f'{{"error": "{result.error}", "field": "{result.field}"}}'
    return result.model_dump_json() if hasattr(result, "model_dump_json") else str(result)


@tool("news_scraper")
def news_scraper_tool(scope: str = "macro", ticker: str = "", days: int = 7) -> str:
    """시장/종목 뉴스 헤드라인. scope='macro' 또는 'ticker'(+심볼). 스크랩만 (해석은 에이전트)."""
    return _dump(news_scraper(scope=scope, ticker=ticker or None, days=days))


@tool("fundamentals")
def fundamentals_tool(ticker: str) -> str:
    """종목 재무 지표 + 파생 스코어(F-score, Z-score, PEG, ROIC 등). 전부 계산된 값."""
    return _dump(fundamentals(ticker))


@tool("technical_indicators")
def technical_tool(ticker: str) -> str:
    """종목 가격·기술지표 (SMA50/200, RSI14, ATR14, 12-1 모멘텀, RS vs SPX, 52주 고점 대비)."""
    return _dump(market_data(ticker))
