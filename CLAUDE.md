# AegisVest — CrewAI 미국주식 다중 에이전트 투자 시스템

## 개요
CrewAI + DeepSeek API로 미국 주식(S&P500/NASDAQ)을 운용하는 자율형 다중 에이전트
펀드 조직. 파이프라인: 매크로 레짐 판별 → 카테고리 배분 → 리스크별 종목 스크리닝
→ 조직(9 에이전트) 검토·의사결정 → 모의투자 리포트.

## 명세가 곧 근거 — `report/`
모든 설계는 `report/phase-{1,2,3,4}-*.md` 에 확정돼 있다.
**모듈을 구현하기 전에 해당 Phase 문서의 관련 절을 먼저 읽어라.**
- Phase 1: 리스크 3티어(A), 동적 배분(B), Claude Code 설정(D)
- Phase 2: 레짐 판별·슬라이드 배분·리밸런싱·OMV8 배포·성공 게이트·백테스트 데이터
- Phase 3: 9-에이전트 조직, 재량 한계, 백테스트↔조직 분리, PaperBroker, **빌드 순서(§9)**
- Phase 4: 판단 일기 RAG

## 현재 빌드 단계
Phase 3 완료 (3a 코어, 3a-11 보류, 3b 조직 완편). **Phase 4 빌드 완료** (4-0~4-5:
태깅·evaluate·⑨ Reviewer·RAG 저장·recall+주입·거버넌스 CLI — 합성데이터로 테스트).
4-6 튜닝·4-7 O-D 는 실데이터(~3개월) 후. 가동도 모의투자 데이터 축적 후. `docs/BUILD_PLAN.md` 참조.
독립 `/code-review` 완료 — 9패스 (pre-Phase-4 7 + 4-post + post-e2e + whole-integration),
전 `aegisvest/` 커버 (~58 수정: TWR 기여일·섀도 레짐 이중계산·guardrail 우회·state atomic·
배당 rate 정규화·regime_history 절삭 등). E2E 통합 테스트 + ponytail 정리(죽은 config·의존성).
**DRY_RUN 엄격 계약** — 드라이런은 `state/` 무접촉 (shadow/regime/일기/RAG/chroma), 회상·미체결·알림 스킵.
`docs/reviews/*.md` (인덱스 `docs/reviews/README.md`). 284 tests. `main` 에 병합됨.
포트 상태는 `state/shadow.json` (organization = 실제, deterministic = 병행 시뮬).
파이썬 3.12 (`.python-version`). 인디케이터는 pandas-ta 없이 직접 계산.
`crewai` 1.15, `chromadb`+`FlagEmbedding`(bge-m3) 설치됨 (`uv sync --extra agents --extra diary`).
`docker` 는 이 개발환경에 없음.
DeepSeek 키는 `.env` 에 있으나 **계정 잔액 부족** — 실 크루 미검증, mock(ScriptedLLM) 로 테스트.
펀더멘털·뉴스·유니버스는 yfinance/RSS/정적파일 (FMP 무료 티어 제한). FRED 키 검증됨.
개발 API 키: FRED/FMP/DeepSeek 없음, Mattermost 웹훅만 있음. FRED/FMP 경로는 mock 테스트.
툴 호출: `from aegisvest.tools.<name> import <name>` (패키지 재export 안 함).

## 빌드 / 테스트
```bash
uv sync
uv run pytest -q
uv run pytest tests/test_tools/
uv run ruff check . && uv run ruff format .
uv run mypy aegisvest
docker compose build
python -m aegisvest.main        # 주간 크루
python -m aegisvest.watchdog    # 일일 감시견
python -m aegisvest.report performance   # 성과 조회
```

## 절대 규칙 (위반 시 코드 반려)
1. **숫자는 Layer 0 파이썬 툴 반환값만.** LLM 암산·추정 금지. 에이전트는 해석·판단만.
2. 툴은 **예외를 raise 하지 않고** `{"error": ..., "field": ...}` 반환.
3. 에이전트 재량은 하드 제한: 카테고리 목표 대비 **±3%p**, 종목은 스코어 상위 풀 내
   선택, veto 가능·편입 강제 불가, 하드 가드레일(고위험 20% 등) 불가침.
4. 최종 주문 수량·비중은 `PortfolioMathTool`(파이썬)이 계산. 에이전트는 승인·선택만.
5. 상세: `docs/PROMPTS.md`

## 아키텍처 규칙
- CrewAI `Process.sequential` + 명시적 `context`. **Hierarchical 금지.**
- 결정론 코어(`pipeline.py`)와 에이전트 레이어 분리. **백테스트엔 에이전트 미포함.**
- 새 추상화(단일 구현 인터페이스·팩토리) 만들지 말 것. 새 의존성 추가 전 확인.
- 3개 스크리닝 태스크는 `async_execution=True`.

## 3티어 전략 (요약)
| 티어 | 정의 | 핵심 필터 | 포지션 |
|---|---|---|---|
| 🟢 저위험 | 배당성장·우량가치 | β 0.6~1.05, 연속증배≥10y, 배당성향 30~65%, ROE≥12%, F≥6 | 3~6%/종목, 손절 없음 |
| 🟡 중위험 | GARP·빅테크 | PEG 0.8~2.0, 매출CAGR 10~30%, ROE≥15%, GPM≥40%, Rule of 40 | 3~5%/종목, 소프트손절 -20% |
| 🔴 고위험 | 혁신테마·모멘텀 | 종가>200SMA, 50>200, RS 상위30%, RSI 45~78, 거래량 확인 | 1~2.5%/종목, 하드손절 -15~25% |

## 레짐 → 배분 (슬라이드 보간, score_smooth -12~+12)
| score | 저 | 중 | 고 | 슬리브 | 현금 |
|---|---|---|---|---|---|
| -12 | 85 | 15 | 0 | 50% | 50% |
| 0 | 55 | 32 | 13 | 85% | 15% |
| +12 | 40 | 40 | 20 | 95% | 5% |
기준점 사이 선형 보간. 고위험 절대 상한 20%. 리밸런싱 밴드 ±4%p/±25%. 쿨다운 10거래일.

## 디렉토리
- `aegisvest/tools/` Layer 0 결정론 툴 (숫자 생성)
- `aegisvest/agents/` CrewAI 에이전트 ①~⑨
- `aegisvest/pipeline.py` 결정론 코어 (백테스트 재사용)
- `aegisvest/broker/` PaperBroker, benchmarks, shadow A/B
- `aegisvest/diary/` 판단 일기 (Phase 4)
- `config/*.yaml` 임계값·가중치·에이전트 정의
- `state/` `outputs/` `data/cache/` 런타임 (git-ignored, 볼륨)

## 커밋 규율
- 빌드 단계별 브랜치. 검증(ruff/mypy/pytest) 통과 후 커밋.
- `push`는 확인받고. 커밋 메시지 끝에:
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
