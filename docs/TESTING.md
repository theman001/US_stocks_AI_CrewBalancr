# TESTING.md — 자율 코드 검증 시나리오

Claude Code 는 코드 작성 후 아래를 자율 실행하고, 실패 시 수정한다.
프레임워크는 **pytest 만**. fixture 남발 금지. 툴별 1개 스모크 테스트 원칙.

## 실행 순서
```bash
uv run ruff check . --fix && uv run ruff format .
uv run mypy aegisvest
uv run pytest -x -q
```

## 시나리오 1 — 툴 계약 준수 (`tests/test_tools/`)
각 툴:
- 정상 입력 → 반환 dict 에 `docs/TOOLS.md` 스키마의 모든 키 존재, 타입 일치
- 잘못된 ticker (`"ZZZZ"`) → 예외 raise 하지 않고 `{"error": ...}` 반환
- 네트워크 차단(monkeypatch) → error dict, 프로세스 생존
- 캐시: 2회 연속 호출 시 2번째는 네트워크 미호출 (호출 카운터 mock)

## 시나리오 2 — RegimeScoreCalculator 결정성 (**필수**)
`config/regime_rules.yaml` 임계값 대비 경계값:
- VIX=14.9 → vix 축 +2 / VIX=15.0 → 0 / VIX=28.1 → -2
- 인위적 6축 raw → `total_score` 가 phase-2 §1 표와 정확히 일치
- `total_score` +5 → BULL / +4 → NEUTRAL / -5 → BEAR
- VIX=36 → `total_score` 무관 CRISIS (`crisis_override=true`)
- 같은 입력 3회 → 완전히 동일한 출력 (LLM 미개입 확인)
- 5일 EMA: 알려진 시퀀스 → 손계산 값과 일치
- 보간: `score_smooth=+2` → phase-2 §2.2 표 기준 저 51.5 / 중 34 / 고 14.5

## 시나리오 3 — 스크리닝 필터 정확성
합성 유니버스(`tests/fixtures/synthetic_universe.json`, ~30종목):
- β=1.2 종목 → LOW 하드필터 탈락
- PEG=2.5 종목 → MID 탈락
- 종가 < 200SMA 종목 → HIGH 탈락
- 통과 0건이면 빈 리스트 반환 (크래시 아님)

## 시나리오 4 — 배분 가드레일 (ConstraintChecker) (**필수**)
- 고위험 합계 22% → 위반 감지, `violations` 에 `high_abs_cap`
- 단일 종목 9% → 위반
- 리밸런싱 밴드: 목표 40% vs 현재 42% → 거래 불필요 / 47% → 거래 필요
- 경계값: 목표 40% vs 현재 44.0% → **밴드 정확히 4.0%p, 거래 필요** (`>=`)
- 쿨다운: 10거래일 내 조정한 카테고리는 `cooldown_blocked`

## 시나리오 5 — 현금흐름 리밸런싱 + 결정론 파이프라인
### 5a CashFlowRebalancer
- 신규 현금이 부족 카테고리를 모두 채우면 → `sell_needed=false`
- 신규 현금 부족 + 밴드 밖 → `sell_needed=true`, `sell_orders` 존재
- `post_action_weights` 합 + 현금 = 1.0 (±0.001)
### 5b run_pipeline (데이터 소스만 mock, 로직은 실제)
- 빈 포트 + 신규 현금 → 전부 매수 주문, 주문 합 ≤ 신규 현금
- `sizing.category_weights` 합 + 현금 = 1.0, `high` ≤ 20%
- draft 에서 빠진 보유 종목 → 전량 매도 주문
- CRISIS 매크로 → `allocation.category_targets_total["high"] == 0`, 슬리브 50%
- PositionSizer: 편입 수 = 예산÷하한, 저/중 균등, 고위험 ATR 역가중, 섹터캡 30% 축소

## 시나리오 6 — 크루 통합 (mock LLM) — `tests/test_agents/test_crew.py`
- `ScriptedLLM(BaseLLM)` 로 DeepSeek 대체 (response_model / 태스크 마커로 canned JSON)
- ① → ② → ⑧ 순차 → `CrewOutcome` (MacroBrief / AnalystView / CIODecision) 스키마 통과
- CIO `HOLD` (CRISIS) → 일기에 `cio_override` 기록, 주문은 불변
- 애널리스트 `excluded_tickers` → 일기 `exclusion` (`enforced: False`)
- 3b: ⑦ Risk Officer REJECTED → Flow 재시도 1회, ⑥ 틸트 ±3%p 클램프 (여기선 미구현)

## 시나리오 7 — 할루시네이션 가드 (**필수**) — `tests/test_agents/test_guardrails.py`
- "약 15%" (헤지어+숫자) → `no_fabricated_numbers` reject
- 페이로드에 없는 "55%" → reject / 페이로드 유래 "40%"·"6"·"90" → pass
- 정성 서술("변동성 안정, 폭 약함")·연도("2026")·참조상수("200일선") → pass

## 시나리오 8 — (Phase 4) 판단 일기
- 일기 항목 스키마 라운드트립 (직렬화/역직렬화)
- `signal_rules` 조건식: `hy_oas_4w_change_bp=10` → `signal:credit_spread_widening` 태그
- evaluator 채점 루브릭: 합성 shadow 데이터 → 예상 score/verdict
- `recall()`: 유사도 < 0.55 → 무반환

## 통과 기준
- 모든 테스트 green, ruff/mypy 클린
- **시나리오 2·4·7 은 반드시 통과** (시스템 신뢰성 핵심). 실패 시 배포 불가.
- 커버리지 목표는 두지 않음. 위 시나리오가 실제 리스크를 커버.
