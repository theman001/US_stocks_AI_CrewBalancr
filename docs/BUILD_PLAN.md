# BUILD_PLAN — 빌드 진행 체크리스트

> 근거: `report/phase-3-organization-and-paper-trading.md` §9 + `report/phase-4-judgment-diary-rag.md` §10
> 단계 완료 시: `review-stage` 스킬로 검토 → 0건 도달 → ✅ 체크 + `docs/reviews/<stage>.md` 링크 → 커밋 → `CLAUDE.md` "현재 빌드 단계" 갱신.
> 1~8 (3a 코어)는 **LLM 없이** 완성·테스트 가능.

## Phase 3a — 결정론 코어 + 최소 조직

- [x] **3a-1 스캐폴딩** — pyproject.toml, config.py, schemas.py(primitives), .env.example, Dockerfile, docker-compose.yml, .python-version(3.12), 디렉토리, tests/test_scaffolding.py — `uv sync`/ruff/mypy/pytest 통과 (docker build 는 ARM/OMV 측에서 검증). 커밋 `build/3a-1-scaffolding`
- [x] **3a-2 데이터 툴** — market_data, fundamentals, macro_data, news + `_io`(캐시)/`_prices`/`indicators`. 순수 함수 + Pydantic 반환 (BaseTool 래퍼는 3a-9). 36 tests, 라이브 스모크 OK. 검토: [reviews/3a-2.md](reviews/3a-2.md) (3 rounds, 8 findings). ⚠️ **후속**: FMP 레이트리밋(3a-5), `_REGIONAL_FED` series id 라이브 검증, `pct_above_200dma`/`pe_5y_median`/F-score/Z-score/배당 연속증배 등 파생지표는 3a-5.
- [x] **3a-3 레짐 엔진** — `tools/regime.py` (`regime_score`) + `config/regime_rules.yaml` + `rules.py`(Pydantic 로더). 6축 채점·정규화·5일 EMA·CRISIS 래치·`low_confidence` 강등. 26 regime tests (경계값·결정성·CRISIS·EMA). 검토: [reviews/3a-3.md](reviews/3a-3.md) (3 rounds, 3 findings). ⚠️ 3a-4: 감시견이 `low_confidence` 아닌 날만 history append + `crisis_state` persist.
- [x] **3a-4 감시견** — `watchdog.py` (`run`/`main`) + `state.py`(JSON persistence) + `notify.py`(Mattermost). 매일 macro_data→regime_score, low_confidence 아닌 날만 history append, crisis_state persist, CRISIS→flag+알림. VIX 1일 +50% 위기조건 regime._crisis 로 통합. 14 tests. 검토: [reviews/3a-4.md](reviews/3a-4.md) (2 rounds, 2 findings). ⚠️ 3a-10: main.py 가 crisis_flag.json 읽어 크루 즉시 실행.
- [x] **3a-5 스크리너 + 스코어링** — `screener.py` / `scoring.py` / `_screen.py` / `_derived.py` / `universe.py` / `breadth.py` + config/{filters,scoring,universe}/*. **FMP→yfinance 전면 전환** (무료 티어 종목 제한). 101 tests. 검토: [reviews/3a-5.md](reviews/3a-5.md) (2 rounds). ✅ phase-1 필터 재보정 승인됨 (2026-09).
- [x] **3a-6 배분 + 리밸런싱** — `allocation.py`(슬라이드 보간·CRISIS 스냅·nav_tier) / `rebalance.py`(현금흐름·밴드·쿨다운·CRISIS 예외) / `constraints.py`(하드 가드레일) + `config/allocation.yaml`. 25 tests. 검토: [reviews/3a-6.md](reviews/3a-6.md) (2 rounds). 라이브: score 0 → phase-2 §2.2 예시와 정확 일치.
- [ ] **3a-7 PaperBroker** — broker/paper, broker/benchmarks, broker/shadow — equity curve 생성
- [ ] **3a-8 pipeline.py** — run_pipeline() 결정론 전체 조립 — 시나리오 6 일부
- [ ] **3a-9 에이전트 3 + 일기 훅** — llm.py, agents/(Macro Strategist / 통합 Analyst / CIO), no_fabricated_numbers, task_callback Mattermost, diary/schema.py + diary/logger.py — 시나리오 7 (필수)
- [ ] **3a-10 리포트 + main** — report.py, notify.py, main.py (주간 크루 전체) — 통합
- [ ] **3a-11 backtest.py** — 3a-2~8을 과거 데이터로 루프 — Gate A

## Phase 3b — 조직 완편

- [ ] **3b-1 애널리스트 분할** — ② Fundamental / ③ Thematic 분리 + ④ News + ⑤ Research Director
- [ ] **3b-2 의사결정 계층** — ⑥ Portfolio Manager + ⑦ Risk Officer + 반려 루프 (crewai.Flow)
- [ ] **3b-3 섀도 틸트 측정** — 조직 on/off NAV 병행 리포트

## Phase 4 — 판단 일기 RAG (모의투자 ~3개월 데이터 후)

- [ ] **4-1 evaluator** — diary/evaluate.py (claim_type별 결정론 채점 루브릭) — 시나리오 8
- [ ] **4-2 Performance Reviewer** — ⑨ 에이전트 (post_mortem + 태깅 + lesson_card)
- [ ] **4-3 RAG 저장** — diary/rag.py (bge-m3 이중벡터 + ChromaDB, 기존 항목 백필)
- [ ] **4-4 recall + 주입** — DiaryRAG.recall() (Q-D 검색, O-A 랭킹, P-D 포맷) + 에이전트 연결
- [ ] **4-5 거버넌스 CLI** — `python -m aegisvest.diary review`
- [ ] **4-6 튜닝** — 유사도 하한·반감기·k, RAG on/off 섀도 A/B 측정
- [ ] **4-7 (추후) O-D** — 학습형 랭킹 가중 (채점 항목 ≥ ~150)

## 배포 (병행)

- [ ] docker-compose.yml — OMV8 단일 스택 (build.context git URL + configs 인라인 crontab + supercronic)
- [ ] cron: 감시견 매일 06:30 / 크루 일요일 22:00 / 일기 채점 월요일 23:00 (KST)
- [ ] Mattermost 웹훅 3채널 (research/decisions/alerts) — `.env`
- [ ] Radxa Rock 5 ITX 배포 검증 (ARM64)

## 명세 미해결 (개발 중 확정)

- [x] **phase-1 필터 임계값 재보정 승인됨** (2026-09) — config/filters/*.yaml, report/phase-1 §A 노트, reviews/3a-5.md
- [ ] 나무증권 해외주식 세제 확정 → phase-2 §5 / phase-3 §9 잠정 규칙 대체
- [ ] 성공 판정 합격선 최종 수치 (샤프 임계, 관찰 기간)
- [x] NewsScraper 소스: Google News + Yahoo RSS (FMP 뉴스 무료 제한)
- [ ] 백테스트 Sharadar 구독 시점 (Gate A 최종 검증 직전)
