---
name: add-tool
description: Scaffold a new Layer 0 deterministic Python tool for AegisVest. Use when adding/implementing any tool in aegisvest/tools/ (market data, fundamentals, macro, screener, scoring, allocation, rebalance, constraints, portfolio math, news). Triggers - "새 툴", "add tool", "X 툴 구현", "implement the ... tool".
---

# add-tool — AegisVest Layer 0 툴 규격

Layer 0 툴은 **숫자를 만드는 유일한 곳**이다. 에이전트는 이 반환값만 쓴다.
먼저 `docs/TOOLS.md` 의 해당 툴 I/O 계약과 `report/phase-1-conception.md` D-5,
관련 Phase 절을 읽어라.

## 규칙 (전부 준수)

1. `crewai.tools.BaseTool` 상속. `name`, `description`(단위 명시), `args_schema`.
2. `args_schema` 는 Pydantic. 모든 필드 `Field(description=..., 단위)`. 기본값 신중히.
3. **예외를 raise 하지 않는다.** 실패 시 `{"error": "설명", "field": "필드명"}` 반환.
   호출 에이전트가 `DATA_UNAVAILABLE` 로 처리한다.
4. 반환은 항상 JSON 직렬화 가능 dict. `docs/TOOLS.md` 스키마의 **모든 키** 포함,
   타입 일치. 없는 값은 `None` (키 누락 금지).
5. **계산을 툴 안에서 완료한다.** 파생 지표(F-score, PEG, Z-score, 가중합, 보간 등)를
   툴이 산출해서 반환. 에이전트에 raw 만 주고 계산 떠넘기지 말 것.
6. 네트워크 호출은 `data/cache/` 에 TTL 캐시 (`CACHE_TTL_HOURS`, 기본 24). 캐시
   히트 시 네트워크 미호출. `requests-cache` 또는 수동.
7. `as_of` (YYYY-MM-DD) 필드 포함. 발표 지연 있는 데이터는 `stale_fields: [...]`.
8. 결정론적. 같은 입력 → 같은 출력. 난수·시각 의존 금지 (as_of 제외).
9. 소스 폴백 순서는 config 또는 상수로 (예: yfinance → FMP).

## 스캐폴딩 순서

1. `aegisvest/schemas.py` 에 입력·출력 Pydantic 모델 추가 (출력은 `docs/TOOLS.md` 기준).
2. `aegisvest/tools/<name>.py` 작성.
3. `aegisvest/tools/__init__.py` 에 등록.
4. `tests/test_tools/test_<name>.py` — TEST_GUIDE 시나리오 1:
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
