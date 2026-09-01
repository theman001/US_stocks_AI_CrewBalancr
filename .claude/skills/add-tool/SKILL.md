---
name: add-tool
description: Scaffold a new Layer 0 deterministic Python tool for AegisVest. Use when adding/implementing any tool in aegisvest/tools/ (market data, fundamentals, macro, screener, scoring, allocation, rebalance, constraints, portfolio math, news). Triggers - "새 툴", "add tool", "X 툴 구현", "implement the ... tool".
---

# add-tool — AegisVest Layer 0 툴 규격

Layer 0 툴은 **숫자를 만드는 유일한 곳**이다. 에이전트는 이 반환값만 쓴다.
먼저 `docs/TOOLS.md` 의 해당 툴 I/O 계약과 `report/phase-1-conception.md` D-5,
관련 Phase 절을 읽어라.

## 규칙 (전부 준수)

1. 툴은 **순수 파이썬 함수** `def <name>(...) -> <Model> | ToolError`.
   CrewAI `BaseTool` 래퍼는 3a-9에서 별도로 추가 (`.model_dump()` 호출). 결정론
   코어·백테스트는 함수를 직접 호출한다 (CrewAI 미포함).
2. 인자는 명시적 타입힌트. 출력은 `aegisvest/schemas.py` 의 Pydantic 모델.
3. **예외를 raise 하지 않는다.** 실패 시 `ToolError(error="설명", field="필드명")` 반환.
   반환 타입은 `<Model> | ToolError`.
4. 성공 모델은 `docs/TOOLS.md` 스키마의 **모든 필드** 포함. 없는 값은 `None`.
5. **계산을 툴 안에서 완료한다.** 파생 지표(F-score, PEG, Z-score, 가중합, 보간 등)를
   툴이 산출. 에이전트/파이프라인에 raw 만 주고 계산 떠넘기지 말 것.
6. 네트워크 호출은 `aegisvest/tools/_io.py` 의 캐시 헬퍼 경유
   (`cached_json` / `cached`). 캐시 히트 시 네트워크 미호출. TTL `CACHE_TTL_HOURS`.
7. `as_of` (YYYY-MM-DD) 필드 포함. 발표 지연 있는 데이터는 `stale_fields: list[str]`.
8. 결정론적. 같은 입력 → 같은 출력. 난수·시각 의존 금지 (as_of 제외).
9. 소스 폴백 순서는 상수/config 로 (예: yfinance → FMP). API 키 없으면 `ToolError`.

## 스캐폴딩 순서

1. `aegisvest/schemas.py` 에 출력 Pydantic 모델 추가 (`docs/TOOLS.md` 기준).
2. `aegisvest/tools/<name>.py` 작성 (순수 함수). **`__init__.py` 에 재export 하지 말 것**
   (모듈명 = 함수명이면 서브모듈 shadowing). 호출: `from aegisvest.tools.<name> import <name>`.
3. 네트워크 호출은 `aegisvest/tools/_io.py` (`cached_json`/`cached_text`/`cached`) 경유.
   yfinance 이력은 `aegisvest/tools/_prices.py` 의 `history()`.
4. `tests/test_tools/test_<name>.py` — TEST_GUIDE 시나리오 1
   (테스트는 `from aegisvest.tools import <name> as mod` 로 모듈을 얻어 monkeypatch):
   - 정상 입력 → 모든 키·타입 확인
   - 잘못된 ticker (`"ZZZZ"`) → error dict, 예외 없음
   - 네트워크 차단(monkeypatch) → error dict, 프로세스 생존
   - 캐시: 2회 호출 시 2번째 네트워크 미호출 (호출 카운터 mock)
5. `uv run ruff check` + `uv run mypy aegisvest/tools/<name>.py` + `uv run pytest tests/test_tools/test_<name>.py`

## 흔한 실수
- 계산을 반환하지 않고 raw 만 반환 → 에이전트가 암산하게 됨 (절대 규칙 위반)
- 예외 raise → 파이프라인 중단
- 캐시 키에 시각 포함 → 매번 미스
- 단위 혼동 (bp vs %, KRW vs USD, 비율 vs 퍼센트)
