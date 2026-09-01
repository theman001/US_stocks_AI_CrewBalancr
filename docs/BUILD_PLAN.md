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
- [x] **3a-7 PaperBroker** — `broker/paper.py`(체결·평가·환전 스프레드) / `broker/metrics.py`(TWR → CAGR·MDD·변동성·샤프·소르티노) / `broker/benchmarks.py`(SPY·60/40·ACWI 동일 현금흐름) / `broker/shadow.py`(결정론 vs 조직 A/B) + 스키마 9종. 21 tests. 검토: [reviews/3a-7.md](reviews/3a-7.md) (3 rounds, 7 findings). ⚠️ 3a-8/3a-10: NAV 평가 시 보유 티커 전부의 체결가 공급 필수 (누락 시 avg_cost 폴백만).
- [x] **3a-8 pipeline.py** — `pipeline.py`(`run_pipeline`: macro+breadth→regime→배분→스크린×3→스코어×3→`cash_flow_rebalance`→`size_positions`→`check_constraints`→`_build_orders`) + `tools/portfolio_math.py`(`size_positions`: 저/중 균등·고위험 ATR 역가중·밴드 클램프·스필·섹터캡) + config `sizing:` 블록. 11 tests. 검토: [reviews/3a-8.md](reviews/3a-8.md) (3 rounds, 5 findings). 라이브: BULL, 결정성 확인, constraints PASS. ⚠️ 초기 배분은 `max_change_per_rebal` 로 수 주 램프업. 3a-10 main.py 가 regime_history/crisis_state 주입.
- [x] **3a-9 에이전트 3 + 일기 훅** — `llm.py`(DeepSeek 팩토리) + `agents/crew.py`(① Macro Strategist → ②③④ 통합 Analyst → ⑧ CIO, Process.sequential) + `agents/guardrails.py`(`no_fabricated_numbers`) + `diary/{schema,logger}.py` + `config/{agents,tasks}.yaml`. CIO 는 HOLD 권한(주문 불변, 실행만 스킵). 16 tests(mock LLM). 검토: [reviews/3a-9.md](reviews/3a-9.md) (3 rounds, 6 findings). ⚠️ 실 DeepSeek 은 계정 잔액 부족으로 미검증 — `pytest -m llm`. crewai 1.15 설치됨.
- [x] **3a-10 리포트 + main** — `main.py`(`run`: 적금 납입→run_pipeline→run_crew→CIO APPROVED 면 체결·HOLD 면 스킵→mark-to-market→리포트+알림) + `report.py`(주간 markdown / `performance` CLI) + `tools/fx.py`(USD/KRW) + 감시견 일일 NAV 평가·위기→main 트리거. 15 tests. 검토: [reviews/3a-10.md](reviews/3a-10.md) (3 rounds, 6 findings — 쿨다운 매수 제거, crisis_flag 소유권, 쿨다운 유지 등). 라이브: BULL, 10종목 체결, 크루 실패 흡수, report.md 저장.
- [~] **3a-11 backtest.py** — **보류** (사용자 결정 2026-09-01). yfinance 는 point-in-time 펀더멘털 미지원 → 프로토타입 백테스트는 "대략적 감"만 가능. 진짜 Gate A 검증은 Sharadar 구독 시 일회성 수행 (phase-2 §8.2). 그때 `run_pipeline` 의 결정론 툴(`macro_data`/`market_data`/`fundamentals`/`screen`/`score_category`)에 as-of 파라미터 스레딩 + 주간 루프 구축.

## Phase 3b — 조직 완편

- [x] **3b-1 애널리스트 분할** — 통합 Analyst → ② Fundamental / ③ Thematic / ④ News 분리 + ⑤ Research Director. `agents/tools.py`(crewai 툴 래퍼 3종), `crew.py` 재작성 (① + ②③④ async → ⑤ → ⑧), `guardrails.hedge_only`(툴 쓰는 에이전트용). schemas: FundamentalNotes/ThematicNotes/MarketNarrative/ResearchView. diary claim_type +catalyst/event_risk/sleeve_stance. 22 tests. 검토: [reviews/3b-1.md](reviews/3b-1.md) (3 rounds, 2 findings). 실 DeepSeek 미검증 (잔액).
- [x] **3b-2 의사결정 계층** — `agents/organization.py`(`run_organization`: 애널리스트 크루 → `_OrgFlow` crewai.Flow @router 반려 1회 → CIO) + `agents/pm.py`(`clamp_pm_draft` 하드 클램프: ±3%p·풀·제외·밴드·캡). PM 이 draft 직접 제안(사용자 결정), 파이썬 클램프. `pipeline.build_orders`/`category_usd` 공개. main 이 org_orders 체결. 12 tests. 검토: [reviews/3b-2.md](reviews/3b-2.md) (2 rounds, 4 findings — 틸트 기준·예산 초과·카테고리 제거·빈 주문). 실 DeepSeek 미검증.
- [x] **3b-3 섀도 틸트 측정** — `main.py` 가 `ShadowState`(deterministic + organization) 이중 포트 병행 시뮬 (동일 현금흐름, 조직 = 실제). `_execute_and_mark` 양쪽 체결·마크, 조직 있으면 결정론 `run_pipeline` 2차 실행. `watchdog._mark_nav` 양쪽 마크. `report` 섀도 A/B 상세(총수익·MDD·샤프 대비). `paper_portfolio.json` → `shadow.json` (1회 이관). 검토: [reviews/3b-3.md](reviews/3b-3.md) (2 rounds, 1 finding). 라이브: 이중 포트 정상.

## Phase 4 — 판단 일기 RAG (가동은 모의투자 ~3개월 데이터 후, 빌드는 지금)

- [x] **4-0 태깅 하네스** — `config/diary_taxonomy.yaml`(CLOSED/SEMI-OPEN + signal_rules) +
  `diary/schema.py`(통제어휘 검증·`eval_signal_rules`·`magnitude_of`) + `PipelineResult.macro`
  + crew/organization 콜백이 action·magnitude·rates_dir·원자료 스냅샷 채움. 3a-9 자리표시자
  완성. 검토: [reviews/4-0.md](reviews/4-0.md) (1 round, 0 findings).
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
