# E2E 통합 테스트 (2026-09-02)

감사 7패스 + ponytail 정리 후. 모듈 단위 테스트는 크로스모듈 배선을 못 잡는다
(감사에서 나온 버그 부류: `_persist_regime` 이중계산, TWR 기여일 불일치,
`clamp_pm_draft` 대소문자 소실 — 전부 모듈 경계에서 발생). `tests/test_e2e.py`
가 실 파이프라인 + 실 조직(ScriptedLLM) + 실 일기 체인을 한 번에 태운다.

## mock 경계 — 데이터 소스만

- `pl.{macro_data, market_breadth, get_universe, screen, score_category, market_data}`
- `portfolio_math.{market_data, _sectors}`, `main.{usd_krw, market_data, latest_close_date, post}`
- `crew.get_llm` → `ScriptedLLM` (canned JSON 9종), `rag._embed` → 균일 벡터 (랭킹은 test_diary_rag 소관)

`run_pipeline` · `run_organization` · `clamp_pm_draft` · `evaluate` · `reviewer` ·
`rag.backfill` · `recall` · `format_recall` 은 전부 **실제 코드**.

## 커버 (test_full_weekly_lifecycle, 5 페이즈)

1. 주간 실행 → 크루 APPROVED, 적금 납입, 주문 체결, shadow.json 저장,
   일기 5종(regime_call/exclusion/catalyst/event_risk/sleeve_stance) 로깅.
   **regime_call 태그가 결정론 레짐(`regime:neutral`)** — LLM 의 "BULL" 주장이 아님 (Layer 0 규율 검증).
   `hy_oas_bp 400` 이 스냅샷에 원자료 그대로.
2. 섀도/레짐 이력 시드 (org +15% > det +5%) → `evaluate` → regime_call 채점,
   `sleeve_stance` verdict=hit (조직 아웃퍼폼이 채점에 반영).
3. `reviewer` (⑨, ScriptedLLM) → post_mortem·lesson 생성, status=reflected.
4. `rag.backfill` → situation/lesson 벡터 색인, `*_vector_id` 필드 채워짐.
5. 2차 주간 실행 → 회상이 `macro_brief`·`research_view`·`pm_draft` 에 주입,
   `cio_decision` 에는 미주입 (⑧ 제외 규칙).

추가 2건:
- `test_crew_failure_absorbed_by_deterministic` — 크루가 raise 해도 결정론 주문·모의투자 계속.
- `test_dry_run_full_chain_no_persistence` — `DRY_RUN=true` → 상태 미저장, 일기는 기록.

## 검증
ruff / format / mypy(50) / pytest **279 passed, 2 deselected**.
커밋: `test(e2e): 주간 전체 생애주기 통합 테스트`
