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
- [x] **4-1 evaluator** — `diary/evaluate.py`(`run`/`needs_reflection`/CLI): 섀도델타(4종)·초과수익 vs SPY(exclusion/catalyst)·regime_call 궤적·event_risk 근사. `logger.save_entries`. 11 tests(합성). 검토: [reviews/4-1.md](reviews/4-1.md) (2 rounds, 1 finding). 임계 상수·정밀 카테고리 중앙값은 실데이터 후(4-6)/Sharadar.
- [x] **4-2 Performance Reviewer** — ⑨ 에이전트 (`config/{agents,tasks}.yaml` +
  `agents/crew.run_reviewer` 단일 태스크 크루) + `diary/reviewer.py`(`run`/CLI): 채점완료
  항목 중 `needs_reflection` → post_mortem·lesson_card·event/theme/mistake 태그 append,
  나머지는 `gated`. 하인드사이트 방지(§4.2): 입력은 기록시점 필드+채점수치만, 뉴스툴 없음.
  `no_fabricated_numbers`(hedge_only) + 모호 반성 → pending_review 강등 + lesson_card 토큰절삭
  + SEMI-OPEN 신규태그 → `state/diary/pending_tags.json`. RAG 게이트(§4.3)로 rag_status 확정.
  `ReviewerOutput` 스키마, `DiaryEntry.post_mortem` dict 화. 10 tests(mock LLM). 검토:
  [reviews/4-2.md](reviews/4-2.md). cron: `evaluate && reviewer` 체이닝. 실 DeepSeek 미검증(잔액).
- [x] **4-3 RAG 저장** — `diary/rag.py`: `DiaryRAG.index`/`backfill`/`collections`/`lesson_text`
  + `python -m aegisvest.diary.rag` CLI. bge-m3(지연 로드) 이중 벡터 (situation/lesson),
  ChromaDB `PersistentClient(state/chroma)` cosine, 자격 `rag_status∈{auto,approved}` &
  `status∈{reflected,gated}`, `retired`→삭제, 배치 임베딩, id 필드로 재계산 방지. 7 tests
  (`_embed` mock). 검토: [reviews/4-3.md](reviews/4-3.md) (2 rounds, 1 finding). cron:
  `evaluate && reviewer && rag`. situation 벡터는 기록시 아닌 백필시 생성 (§5.1 결정 노트).
- [x] **4-4 recall + 주입** — `DiaryRAG.recall` (Q-D top-40×2 → O-A `0.65·코사인+0.20·구조+
  0.15·최근성` → dedupe → floor 0.55·attribution 게이트 → crisis 다양성), `build_query`
  (§6.2 결정론, LLM 없음), `format_recall` (§6.4 top-1 중간요약 + 카드). `organization`
  이 회상 1회 계산 → ①②③⑤⑥⑦ 태스크에 주입 (④⑧ 제외), guardrail `extra_allowed` 로
  회상 수치 통과. `schema.clip_tokens` 공용화. 8 tests. 검토: [reviews/4-4.md](reviews/4-4.md)
  (2 rounds, 4 findings). 단일 회상(2단계는 4-6), 콜드스타트 시 임베딩 스킵.
- [x] **4-5 거버넌스 CLI** — `aegisvest/diary/governance.py` + `__main__.py`:
  `python -m aegisvest.diary review` → pending_review 큐 + 신규 SEMI-OPEN 태그 + top-20
  회상 교훈(+base rate) 리포트. `--approve/--retire/--edit --lesson/--ack-tags` 액션 (재색인은
  다음 rag 배치). `rag._log_recall` → `state/diary/recall_log.jsonl`. 6 tests. 검토:
  [reviews/4-5.md](reviews/4-5.md) (2 rounds, 0 findings). 교훈 충돌 탐지는 4-6.
- [x] **4-post 독립 code-review** — 빌트인 `/code-review` high 로 4-1~4-5 재검토, 7건 중 6건 수정
  (동시성 `diary_lock` fcntl · `_merge_tags` signal 우선 폐기 · 회상 guardrail hedge_only ·
  `_normalize_regime` · reviewer 건별 save · governance JSON 가드), 1건(회상 시 모델 로드)
  문서화 + `_MIN_CORPUS` 게이트. 검토: [reviews/4-post-codereview.md](reviews/4-post-codereview.md).
- [ ] **4-6 튜닝** — 유사도 하한·반감기·k, RAG on/off 섀도 A/B 측정
- [ ] **4-7 (추후) O-D** — 학습형 랭킹 가중 (채점 항목 ≥ ~150)

## Pre-Phase-4 감사 (독립 `/code-review`)

- [x] **money-path** — `broker/` · `portfolio_math` · `pipeline` · `main` · `state`. 7건 수정:
  TWR 기여일=NavPoint일 정렬 · 섀도 레짐 이중계산 방지(`_persist_regime` 이동) · `state`
  atomic write · 벤치 결측 leg `pending_usd` 이월 · n_orders/docstring/중복호출.
  검토: [reviews/money-path-codereview.md](reviews/money-path-codereview.md). 251 tests.
- [x] **guardrails/pm** — `agents/guardrails.py` · `agents/pm.py`. 5건 수정: `~` 범위표기
  헤지 오탐 · `clamp_pm_draft` 섹터캡 미적용(+constraints FAIL→결정론 폴백) · 카테고리
  대소문자로 PM 틸트 소실 · 티커 중복 이중계상 · 손절 상수 반려.
  검토: [reviews/guardrails-pm-codereview.md](reviews/guardrails-pm-codereview.md). 257 tests.
- [x] **regime/screen/score** — `tools/regime.py` · `screener.py` · `allocation.py`. 6건 수정:
  low_confidence 시 score_smooth 외삽 억제 · RS 컷 데이터운 의존 제거 · EMA 같은날 이중계산 ·
  CRISIS 해제 공휴일 반영 · 백워데이션 `>=` 명세 일치 · 고위험캡 스필 mid.
  검토: [reviews/regime-screen-codereview.md](reviews/regime-screen-codereview.md). 261 tests.
- [x] **runtime** — `watchdog.py` · `report.py` · `constraints.py` · `state.py`. 6건 수정:
  벤치마크 기여 미보정(Gate B 왜곡) · read/write 인코딩 미지정(C 로케일 상태유실) ·
  `_mark_nav` guard 가 빈 포트 봄 · `max_change_per_rebal` 게이트가 메인 경로서 미작동 ·
  FX 폴백 1400 점프 · 가격 중복조회. 검토: [reviews/runtime-codereview.md](reviews/runtime-codereview.md). 263 tests.
- [x] **data-tools** — `macro_data` · `market_data` · `fundamentals` · `news` · `_io` · `_prices`.
  5건 수정: dropna 가 최신봉 버려 가격 stale · 캐시 손상 미복구+비원자적 · `_cagr` 결측
  압축으로 기준연도 어긋남 · 뉴스 미상날짜 컷오프 우회 · 빈약 VIX 프레임 stale 미표시.
  검토: [reviews/data-tools-codereview.md](reviews/data-tools-codereview.md). 268 tests.
- [x] **scoring-derived** — `scoring` · `_derived` · `breadth` · `universe` · `config`. 8건 수정:
  폭 4w 분모 편향 · `roic` 결측 debt 0 대체 · `piotroski_f` 부분점수 · scoring 비숫자 raise ·
  `_bool_env` 빈값 · 음수 PE 밸류 최고점 · FMP 점표기 미정규화 · 배당 연속성 미확인.
  검토: [reviews/scoring-derived-codereview.md](reviews/scoring-derived-codereview.md). 274 tests.

> **감사 완료** — 독립 `/code-review` 8 패스 (4-post-review + post-e2e 포함), 전 `aegisvest/`
> 커버, ~50 findings / ~48 수정. `docs/reviews/*-codereview.md` + `docs/reviews/README.md`.

- [x] **E2E 통합 테스트** — `tests/test_e2e.py`: 실 `run_pipeline`(데이터 소스만 mock) +
  실 `run_organization`(ScriptedLLM) + 실 일기 체인(로깅→evaluate→reviewer→rag.backfill→
  2차 실행 회상 주입). 모듈 단위 테스트가 못 잡는 크로스모듈 배선(감사 버그 부류) 검증.
  Layer 0 규율(일기 태그 = 결정론 레짐, LLM 주장 아님) + 크루 실패 흡수 + DRY_RUN 무저장.
  3 tests. 검토: [reviews/e2e.md](reviews/e2e.md). 279 passed.
- [x] **감사 이후 추가분 독립 `/code-review`** — ponytail·DRY_RUN·E2E·배당 rate 커밋 재검토.
  4건 수정: E2E 시간의존(→run_id 상대날짜) · docker hf-cache bind mount 가 bge-m3 베이크 섀도
  (→명명 볼륨) · recall_log 절삭 비원자적 · 배당 docstring. 이어 노트도 사용자 판단으로 수정:
  **DRY_RUN 엄격 계약** (`run_organization(dry_run=)` 스레딩 — 드라이런은 일기·RAG·회상·Slack
  노트 전부 스킵, `state/` 무접촉) + **골든/데스크로스 상태 기반** (`spx_sma_50 < spx_sma_200`,
  `spx_sma_*_prev` 제거) + crisis 픽스처 현실화 (`death_cross` 발동).
  검토: [reviews/post-e2e-codereview.md](reviews/post-e2e-codereview.md). 282 passed.

## 배포 (병행)

- [x] docker-compose.yml — OMV8 단일 스택. **Phase 4 대응 (2026-09-02)**: crontab 이 일기
  배치를 `evaluate && reviewer && rag` 체이닝, `mem_limit 4g`(bge-m3 상주), `HF_HOME` 볼륨.
  Dockerfile 이 빌드 시 bge-m3 가중치 베이크 (명명 볼륨 `hf-cache` 로 첫 up 시 채움 — bind
  mount 면 베이크본이 가려짐). `DRY_RUN` **엄격 계약** (`state/` 무접촉: shadow/benchmarks/regime/
  일기/RAG/chroma 미생성, 회상·Slack 노트·미체결·알림 스킵. 크루·리포트·`outputs/` 는 실행.
  기본 true — `.env` 에서 false 로 가동).
- [ ] Mattermost 웹훅 3채널 (research/decisions/alerts) — `.env`
- [ ] Radxa Rock 5 ITX 배포 검증 (ARM64) — **docker build 는 이 개발환경에 docker 없어 미검증**

## 명세 미해결 (개발 중 확정)

- [x] **phase-1 필터 임계값 재보정 승인됨** (2026-09) — config/filters/*.yaml, report/phase-1 §A 노트, reviews/3a-5.md
- [x] NewsScraper 소스: Google News + Yahoo RSS (FMP 뉴스 무료 제한)

---

## 후속 일감 (외부 대기 / 소규모 개선)

> 지금 당장 못 하는 것 — 트리거 조건이 오면 처리. `docs/reviews/*-codereview.md` 에서 발췌.

### A. 실데이터 축적 후 (모의투자 ~3개월)
- [ ] **4-6 튜닝** — `similarity_floor`·`recency_halflife_months`·recall `k`, RAG on/off
  섀도 A/B 측정, `evaluate.py` 임계 상수(`_SHADOW_DELTA_UNIT` 0.5%p / `_EXCESS_RETURN_UNIT`
  10% / event severity), `rag._MIN_CORPUS` 튜닝
- [ ] **4-6 교훈 충돌 탐지** — 신규 lesson 벡터 vs 기존 고신뢰 lesson 코사인 유사도 →
  거버넌스 CLI 에 충돌 목록 (report/phase-4 §8)
- [ ] **4-6 2단계 회상** — ①②③ 는 매크로 쿼리, ⑤⑥⑦ 는 애널리스트 event/theme 태그 반영
  강화 쿼리 (현재는 단일 회상)
- [ ] **4-6 `format_recall` 4줄 템플릿** — top-1 을 상황/판단/결과/교훈 4줄로 (현재 원문 절삭).
  `RecalledCase` 에 `what_happened`·`lesson` 메타 추가 필요 (report/phase-4 §6.4)
- [ ] **4-6 실 토크나이저** — `diary.schema.clip_tokens` 의 문자/3 근사 → tiktoken 등
- [ ] **4-7 O-D** — 학습형 로지스틱 랭킹 가중 (`0.65/0.20/0.15` 대체). 채점 항목 ≥ ~150
- [ ] **성공 판정 합격선 최종 수치** — 샤프 임계, 관찰 기간 (실 트랙레코드 보고 확정)

### B. 구독 / 외부 서비스
- [ ] **Sharadar 백테스트** — 3a-11 보류 해제. point-in-time 펀더멘털 → Gate A 일회성 검증.
  `run_pipeline` 결정론 툴에 as-of 스레딩 + 주간 루프 (phase-2 §8.2)
- [ ] **point-in-time 뉴스** — Reviewer(4-2) 하인드사이트 입력·`evaluate` exclusion "카테고리
  중앙값" 정밀화 (현재 SPY 근사). Sharadar/유료 뉴스 아카이브
- [ ] **나무증권 해외주식 세제** — phase-2 §5 / phase-3 §9 잠정 규칙 대체
- [ ] **DeepSeek 잔액 충전** → `uv run pytest -m llm` (실 크루 검증), `-m net` (bge-m3)
- [ ] **Mattermost 웹훅 3채널** (research/decisions/alerts) — `.env` `MM_WEBHOOK_*`

### C. 환경 (이 개발환경에 docker 없음)
- [ ] **docker build 검증** (ARM64) + bge-m3 베이크 이미지 크기 확인
- [ ] **Radxa Rock 5 ITX 배포** — compose up, 볼륨·cron·supercronic 동작 확인

### D. 소규모 개선 (아무때나)
- [x] **watchdog `dry_run` 배선** (2026-09-02) — `get_settings().dry_run` 이면 crisis_state/
  regime_history/nav 미저장 + 위기 알림·주간 트리거 스킵 (계산·로그만). main 과 동일 패턴.
- [x] **배당 지급시기 왜곡** (2026-09-02) — `_annual_dividends` 를 rate 정규화로 교체:
  연도별 지급액 중앙값 * 전 기간 최빈 지급빈도. 2017 TCJA 선지급·특별배당에 불변.
  이미 받아오던 `.dividends` (payment 단위) 활용 — 신규 데이터 소스 불필요.
- [x] **`recall_log.jsonl` 로테이션** (2026-09-02) — `_RECALL_LOG_MAX=520` (~10년치) 초과 시
  앞부분 절삭. 주 ~1행이라 실질 영향 없지만 무한 증가 방지.
- [x] **`docs/reviews/` 인덱스** (2026-09-02) — [reviews/README.md](reviews/README.md) (단계 게이트 17 + 감사 8 + 기타 2)

> **ponytail 정리** (2026-09-02) — 감사 후 오버엔지니어링 스캔. 죽은 config(reasoner/
> llm_temperature/max_rpm/nasdaq/max_high_risk)·스키마(Verdict/Metric)·레거시 이관 코드
> + `requests-cache`·`crewai-tools` 의존성 제거. 동작 변화 0. [reviews/ponytail-cleanup.md](reviews/ponytail-cleanup.md)
