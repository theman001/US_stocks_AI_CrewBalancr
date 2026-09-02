# AegisVest — Phase 3 구상 보고서: 에이전트 조직 & 모의투자 하네스

> **작성일**: 2026-09-01
> **상태**: 확정 (세제 항목 잠정, 판단 일기 RAG는 Phase 4)
> **선행 문서**: [phase-1-conception.md](phase-1-conception.md) · [phase-2-macro-and-rebalancing.md](phase-2-macro-and-rebalancing.md)
> **대체 대상**: Phase 1 과제 C (CrewAI 조직 구조)

---

## 0. 결정 요약

| # | 결정 사항 | 선택 |
|---|---|---|
| A | 조직 규모 | **9-에이전트 4계층 펀드 운용 조직** (얇은 3-에이전트안 폐기) |
| B | 에이전트 재량 한계 | 카테고리 목표 대비 **±3%p** / 종목은 **스코어 상위 풀(max_positions×1.5) 내에서만** 선택 / **veto 가능, 편입 강제 불가** / 하드 가드레일 불가침 / 주문 수량은 PortfolioMathTool이 계산 |
| C | 백테스트 ↔ 조직 분리 | **백테스트 = 결정론 코어만** 검증. **조직(에이전트) = 라이브/모의 전용**, 도움 여부는 섀도 A/B로 측정. 조직은 백테스트로 검증된 코어를 뒤엎지 못함 |
| D | 역할 분담 | **파이썬 = 사실(scrape·계산), AI = 판단(정리·해석·분석·결정)** |
| E | 상호작용 모니터링 | CrewAI `task_callback` → Mattermost 3채널 실시간 게시 + `outputs/runs/<date>/` 파일 로그 |
| F | 소액 포트 구성 | 모의 = 소수점 30종목 (전략 원형), 실제 = 집중 + NAV 티어 확대 |
| G | 페이퍼 체결가 | 신호 다음 미국장 **개장가** |
| H | 판단 일기 RAG | 스키마·로깅은 Phase 3a부터, 채점·회상 서브시스템은 **Phase 4** |

---

## 1. 설계 원칙

| 원칙 | 의미 |
|---|---|
| **숫자 ≠ 에이전트** | 모든 수치(가격·지표·점수·비중·수량)는 Layer 0 파이썬 툴 출력. 에이전트는 해석·판단·종합만. `no_fabricated_numbers` 가드레일이 위반 시 반려 |
| **재량은 경계 안에서** (B) | 에이전트 틸트는 카테고리 ±3%p, 종목은 스코어 상위 풀 내, veto만 가능. 백테스트로 검증된 코어를 못 뒤엎음 |
| **에이전트는 라이브 전용** (C) | 백테스트엔 미포함 (25년×52주×다중콜 비현실 + LLM 룩어헤드). 조직 효용은 섀도 A/B로 별도 입증 |
| **독립 검증 + 거부권** | Risk Officer는 PM 산출물을 독립 재계산·검증, **REJECT 가능**. CIO만 최종 서명 |
| **관찰 가능성** (E) | 조직의 사고 과정을 Mattermost로 실시간 관전 |

> **B/C 상세 해설** (결정자 이해용):
> - **B 비유**: 검증된 레시피(정량 코어)에 요리사(에이전트)가 간을 맞출 순 있지만 주재료를 바꾸거나 소금을 3배 넣을 순 없다. 재량을 풀면 성과가 "그 주 LLM 컨디션"에 좌우되고 백테스트가 무의미해진다.
> - **C 비유**: 뼈대는 과거로 증명(백테스트), 조직은 실전 A/B로 증명. 매주 포트폴리오 2개 기록 — (a) 순수 결정론, (b) 조직 반영. 3~6개월 뒤 (b)>(a)면 조직 유지, (b)≤(a)면 재량 축소/컷.

---

## 2. 조직도 (4계층 · 9 에이전트)

```
LAYER 0 — 정보 수집 (파이썬, 에이전트 아님)
  MarketData · Fundamentals · MacroData · NewsScraper · Screener
  · ScoringCalculator · RegimeScoreCalculator · AllocationTable(보간)
  · CashFlowRebalancer · ConstraintChecker · PortfolioMathTool
        │
        ▼
LAYER 1 — 애널리스트 (async 병렬 4)          "영역 데이터 + 뉴스 → 리서치 노트"
  ① Macro Strategist          (매크로 전략가)
  ② Fundamental Analyst       (펀더멘털 분석가 — 저·중위험)
  ③ Thematic/Momentum Analyst (테마·모멘텀 분석가 — 고위험)
  ④ News & Sentiment Analyst  (뉴스·센티먼트 분석가)
        │
        ▼
LAYER 2 — 종합·검토 (1)
  ⑤ Research Director         (리서치 총괄) — 노트 4종 상충 조정 → 하우스뷰
        │
        ▼
LAYER 3 — 의사결정 (3)
  ⑥ Portfolio Manager        (포트폴리오 매니저) — 결정론 배분 + 하우스뷰 틸트 → 초안
  ⑦ Risk Officer             (리스크 담당) — 독립 검증, 거부권
  ⑧ Chief Investment Officer  (CIO) — 최종 승인 + IC 메모 서명
        │
        ▼
LAYER 4 — 사후 학습 (1, Phase 4 가동)
  ⑨ Performance Reviewer     (성과 리뷰어) — 과거 판단 채점·반성 → 판단 일기 RAG
        │
        ▼
  리포트 조립 → Mattermost + outputs/
```

---

## 3. 에이전트 상세

모든 계산 에이전트 backstory에 Phase 1 C-3의 "절대 규칙" 블록 삽입. 페르소나 3~4문장.

### ① Macro Strategist — 매크로 전략가
- **Goal**: `RegimeScoreCalculator` 출력(6축 점수 + raw 값 + 히스토리)을 해석해 레짐을 평이하게 설명하고, 축 간 상충·향후 2~4주 리스크 시나리오·관찰 포인트를 제시
- **입력**: RegimeScore JSON, 매크로 히스토리, 매크로 헤드라인(NewsScraper)
- **출력** `MacroBrief`: `{regime, confidence, axis_conflicts[], risk_scenarios[], watch_items[]}`
- **툴**: MacroDataTool (추가 조회용, 선택)
- **재량**: 없음 (해설·판단만). 배분 숫자 언급 금지
- **temperature**: 0.3

### ② Fundamental Analyst — 펀더멘털 분석가 (저·중위험)
- **Goal**: LOW/MID 스크린 통과 상위 후보의 재무 건전성을 코멘트하고, 스코어가 못 잡는 정성 리스크(이익 피크아웃, 일회성 이익, 소송, 회계 이슈, 경영진 교체)를 플래그
- **입력**: LOW/MID 스크린 결과 + 재무 지표 + 스코어, 종목별 최근 뉴스
- **출력** `FundamentalNotes`: `[{ticker, thesis_1line, quality_flags[], valuation_trap: bool}]`
- **툴**: NewsScraperTool, FundamentalsTool
- **재량**: 후보에 `exclude` 권고 가능 (스코어 무관 정성 거부). 편입 강제 불가
- **temperature**: 0.2

### ③ Thematic / Momentum Analyst — 테마·모멘텀 분석가 (고위험)
- **Goal**: HIGH 후보를 테마 분류하고 다음 촉매 이벤트·날짜, 크라우딩/과열 경고, 모멘텀 지속성을 판단. 결과는 스코어의 "테마 강도" 항목에 피드백
- **입력**: HIGH 스크린 결과 + 기술 지표 + 테마/뉴스
- **출력** `ThematicNotes`: `[{ticker, themes[], catalyst, catalyst_date, crowding_flag, momentum_durability: high|med|low}]`
- **툴**: NewsScraperTool, TechnicalIndicatorTool
- **재량**: 테마 강도 점수 조정(제한 범위), `exclude` 권고
- **temperature**: 0.3

### ④ News & Sentiment Analyst — 뉴스·센티먼트 분석가
- **Goal**: 이번 주 시장 내러티브를 요약하고, 매크로 점수에 안 잡히는 이벤트 리스크(선거·지정학·규제·Fed 발언 뉘앙스)를 플래그
- **입력**: 매크로/시장 전반 헤드라인 스크랩
- **출력** `MarketNarrative`: `{weekly_summary, event_risks: [{event, date, affected_sleeve, severity}]}`
- **툴**: NewsScraperTool
- **재량**: 없음. 이벤트 리스크 반영 여부는 Layer 2가 판단
- **temperature**: 0.3

### ⑤ Research Director — 리서치 총괄
- **Goal**: 노트 4종을 종합해 상충을 조정하고(예: 매크로는 방어인데 테마 애널이 공격적 → 사이즈 억제 권고), 슬리브별 통합 스탠스와 교차 리스크를 담은 하우스뷰 생산
- **입력**: MacroBrief + FundamentalNotes + ThematicNotes + MarketNarrative
- **출력** `ResearchView`: `{sleeve_stance: {low|mid|high: {stance: overweight|neutral|underweight, reason}}, cross_risks[], excluded_tickers[], notes}`
- **툴**: 없음 (순수 종합)
- **재량**: 슬리브 스탠스 권고 (PM 참고). 직접 비중 결정 불가
- **temperature**: 0.2

### ⑥ Portfolio Manager — 포트폴리오 매니저
- **Goal**: `AllocationTable`(보간, 파이썬)의 목표 배분을 받아 `ResearchView` 스탠스로 가드레일 범위 내 틸트하고, `CashFlowRebalancer`(파이썬) 결과에 맞춰 종목을 최종 선택, 주문 초안 생성
- **입력**: AllocationTable 목표, ResearchView, 현재 포트폴리오, CashFlowRebalancer 결과, 스코어 랭킹
- **출력** `DraftPortfolio`: `{target_weights, holdings[], orders[], tilt_rationale}`
- **툴**: PortfolioMathTool (모든 수량·비중 계산), PositionSizer
- **재량 한계 (하드, B)**:
  - 카테고리 목표 대비 **±3%p**
  - 종목은 각 카테고리 **스코어 상위 N (= max_positions × 1.5)** 안에서만 선택
  - `ResearchView.excluded_tickers` 반드시 제외
  - 신규 종목 추가·하드 가드레일(고위험 20% 등) 위반 불가
  - 주문 수량 임의 조정 불가 (PortfolioMathTool 계산 고정)
- **temperature**: 0.2

### ⑦ Risk Officer — 리스크 담당 (독립 검증)
- **Goal**: `ConstraintChecker`(파이썬) 결과를 검토하고 정성 리스크(집중도, 상관관계 클러스터, 유동성, 이벤트 겹침)를 평가. PM 틸트가 하우스뷰로 정당화되는지 확인
- **입력**: DraftPortfolio, ConstraintChecker 결과, ResearchView, MarketNarrative.event_risks
- **출력** `RiskReview`: `{verdict: APPROVED|CONDITIONAL|REJECTED, conditions[], concerns[]}`
- **툴**: ConstraintChecker, PortfolioMathTool (독립 재계산)
- **권한**: REJECTED → PM에게 **1회 반려** (사유 첨부). 2회차도 REJECTED면 "이번 주 리밸런싱 보류, 현 포트 유지"로 CIO에 상신
- **temperature**: 0.1

### ⑧ Chief Investment Officer — CIO (최종 결정)
- **Goal**: DraftPortfolio + RiskReview + ResearchView를 놓고 최종 승인. CONDITIONAL이면 조건 수용 여부 결정. 배분 대변화(>10%p)나 CRISIS면 추가 코멘트. IC 메모 서명
- **입력**: 위 3종
- **출력** `FinalPortfolio`: `{approved_orders[], ic_memo, regime_label, allocation_summary}`
- **툴**: 없음 (승인·서명)
- **재량**: RiskReview 조건 override 가능하나 사유를 IC 메모에 **명시 필수**. 주문 숫자는 못 바꿈 — "승인/보류"만
- **temperature**: 0.2

### ⑨ Performance Reviewer — 성과 리뷰어 (Phase 4 가동)
- **Goal**: `horizon`이 경과한 과거 판단을 실제 가격·수익 데이터로 채점하고, miss에 대해 **판단 시점 가용 신호 기준**으로 근본 원인을 서술 + 태깅
- **입력**: 채점 대상 일기 항목 배치 + 해당 기간 실제 가격/수익 + 해당 기간 뉴스
- **출력** `PostMortem`: `{diary_id, verdict, score, what_happened, post_mortem, tags[]}`
- **툴**: MarketDataTool, NewsScraperTool
- **재량**: 없음 (사후 분석)
- **temperature**: 0.2
- **금지**: 사후확신 편향("더 신중했어야"). 판단 시점에 이용 가능했던 구체적 신호를 놓쳤/오독했는지만 서술

---

## 4. 데이터 흐름 & 반려 루프

```
Layer 0 파이썬  ──→  ① ② ③ ④  (async 병렬)  ──→  ⑤ Research Director
                                                        │ ResearchView
                                                        ▼
                                              ⑥ PM ──→ DraftPortfolio
                                                 ▲          │
                                        1회 반려 │          ▼
                                                 └──── ⑦ Risk Officer
                                                            │ APPROVED / CONDITIONAL
                                                            ▼
                                                        ⑧ CIO ──→ FinalPortfolio
                                                            │
                                        (Phase 4) ⑨ Reviewer ← 주간 별도 배치
```

- CrewAI `Process.sequential` + 각 Task `context` 명시. ①~④는 `async_execution=True`.
- ⑥↔⑦ 반려 루프: `crewai.Flow` `@router` 또는 파이썬 재시도 래퍼 (최대 1회).
- **Hierarchical 프로세스 미사용** — 조직 위계는 개념(역할), 실행은 고정 파이프라인 (Phase 1 결정 유지, DeepSeek 비결정성 회피).
- 선택: PM이 Research Director에게 1회 질의 허용 (제한적 위임).

---

## 5. 숫자 무결성 메커니즘

| 장치 | 역할 |
|---|---|
| Layer 0 툴만 숫자 생성 | 에이전트 입력은 전부 구조화 JSON |
| `no_fabricated_numbers()` 가드레일 | 각 에이전트 출력의 모든 숫자를 입력 페이로드와 대조, 불일치 시 재요청 |
| `ConstraintChecker` (파이썬) | ⑦ 단계 강제 실행 하드 게이트 — 에이전트 판단 무관 |
| `PortfolioMathTool` (파이썬) | 최종 주문 수량·비중 100% 여기서 계산. ⑥⑧은 선택·승인만 |
| Layer 2~3 에이전트 툴 없음 | 툴콜 불안정성 노출 최소화 (툴은 ①②③⑨만) |
| `deepseek-chat`, temp 0.0~0.3, `top_p` 낮게 | 재현성 |

> **⚠️ 3b-2 변경 (사용자 결정 2026-09-01)**: ⑥ PM 은 "선택·승인만" 대신 **DraftPortfolio
> (카테고리·종목 비중)를 직접 제안**한다. LLM 이 비중 숫자를 내지만 파이썬
> `agents/pm.clamp_pm_draft` 가 하드 한계로 강제 클램프한다: 카테고리 목표 ±3%p / 종목은
> 스코어 상위 풀(max_positions×1.5) 내(신규 편입 불가) / `excluded_tickers` 강제 제외 /
> 티어 밴드·단일종목 8%·고위험 20%·**섹터 30%**·현금 3% 불가침. LLM 이 카테고리를 대문자로
> 내거나 티커를 중복해도 정규화·dedup. 그래도 `check_constraints` 가 FAIL 이면 조직 주문을
> 버리고 **결정론 주문으로 폴백** (guardrails-pm 감사, 2026-09-02). 최종 주문 수량은 여전히
> 파이썬 (`pipeline.build_orders`). ⑥ 는 hedge_only 가드레일.
>
> **반려 루프**: `crewai.Flow` `@router` (⑥ PM → ⑦ Risk → REJECTED 면 PM 1회 재시도,
> 2회차도 REJECTED 면 `rebalance_held` → 이번 주 매매 스킵). `agents/organization.py`.

---

## 6. 상호작용 모니터링 (E)

CrewAI `task_callback` 훅 → 각 에이전트 노트 완성 시 Mattermost 게시 (실시간 관전).

| 채널 | 게시 내용 |
|---|---|
| `#aegis-research` | 애널리스트 4종 노트 + Research Director 종합 |
| `#aegis-decisions` | PM 초안 → Risk 검토(반려 시 양 라운드) → CIO 메모 |
| `#aegis-alerts` | 위기 알림 + 주간 최종 요약 |

- 구현: 인커밍 웹훅 1개 + payload `channel` 오버라이드, 또는 채널별 웹훅 3개 (`.env`: `MM_WEBHOOK_RESEARCH` 등)
- ⚠️ **2026-09 확인**: 현 웹훅(`chat.taeuk.site`)은 **채널 고정** — payload `channel` 넣으면 404.
  → `notify.post` 는 채널별 웹훅 있으면 라우팅, 없으면 기본 URL + 텍스트 `[채널]` 태그.
- 각 게시 = `에이전트명 · 역할 이모지 · 핵심 요약` + 상세 접기
- 전체 원문 I/O → `outputs/runs/<날짜>/<순번>_<에이전트>.json`
- `step_callback`(사고·행동 단계)은 파일 로그만 (Mattermost엔 시끄러움)

---

## 7. 모의투자 하네스 (PaperBroker)

### 7.1 데이터 모델

`state/paper_portfolio.json`
```json
{
  "cash_usd": 68.5,
  "positions": {"MSFT": {"shares": 0.152, "avg_cost_usd": 420.1}},
  "contributions": [{"date": "2026-09-01", "krw": 100000, "usd": 70.0, "fx_rate": 1428.5}],
  "history": [{"date": "2026-09-01", "nav_usd": 70.0, "nav_krw": 100000}]
}
```

### 7.2 체결 규칙
- 체결가 = **신호 다음 미국장 개장가** (일요일 밤 KST 실행 → 월요일 개장가). 룩어헤드 없음
- 소수점 주식 허용 (나무증권 소수점 매매와 일치, 시뮬은 무제한 정밀도)
- 비용 (config 노브 — 실측 후 조정): `PAPER_COMMISSION_PCT=0.001`, `PAPER_FX_SPREAD_PCT=0.005`

### 7.3 평가 & 벤치마크
- 일일 평가: 감시견이 가격 수집 시 `history`에 NAV 추가 (KRW·USD 둘 다)
- 벤치마크 병행: 동일 현금흐름으로 `SPY` / `60·40`(SPY+AGG) / `ACWI` 시뮬 → `state/benchmarks.json`
- **섀도 A/B** (C): 매주 (a) 순수 결정론 포트 (b) 조직 반영 포트 둘 다 추적 → `state/shadow.json`
- 성과 조회: `python -m aegisvest.report performance` → CAGR·MDD·변동성·샤프·소르티노 + 벤치 3종 + (a)vs(b) 대비. Gate B 판정 사용

---

## 8. 소액 구간 포트폴리오 구성 (F)

| 구간 | 방식 | 종목 수 |
|---|---|---|
| **모의투자** | 소수점 30종목 (전략 원형, 백테스트와 동일 로직 검증) | 저 20 / 중 15 / 고 15 |
| **실제 자금** | 집중 + NAV 티어 확대 | 아래 표 |

```yaml
# config/allocation.yaml
nav_tiers:
  - {below_usd: 10000,  max_positions: {low: 5,  mid: 4,  high: 3}}
  - {below_usd: 25000,  max_positions: {low: 8,  mid: 6,  high: 5}}
  - {below_usd: 999999, max_positions: {low: 20, mid: 15, high: 15}}
```

- ETF 프록시(저=SCHD, 중=QQQ, 고=테마 ETF)는 **Gate A 실패 시 폴백**으로만
- 집중 시 사이징: 카테고리 예산 내 스코어 가중, 단일 종목 `min(포트 8%, 균등비중 × 1.5)` 상한

---

## 9. 빌드 단계

각 단계 독립 테스트 가능. 1~8단계(3a 코어)는 **LLM 없이** 완성·검증 가능.

| 단계 | 산출물 | 검증 (TEST_GUIDE) |
|---|---|---|
| **3a-1** | 스캐폴딩 (pyproject, config, schemas, Docker, compose) | 빌드 성공 |
| **3a-2** | 데이터 툴 (market/fundamentals/macro/news + 캐시) | 시나리오 1 |
| **3a-3** | 레짐 엔진 (regime.py + regime_rules.yaml) | 시나리오 2 (경계값·결정성) |
| **3a-4** | 감시견 (watchdog.py — 위기 체크 + 매크로 점수 누적) | 독립 실행 |
| **3a-5** | 스크리너 + 스코어링 | 시나리오 3 |
| **3a-6** | 배분 보간 + 현금흐름 리밸런싱 + 제약 | 시나리오 4 |
| **3a-7** | PaperBroker + 벤치마크 + 섀도 A/B | equity curve 생성 |
| **3a-8** | pipeline.py (결정론 전체 조립) | 시나리오 5 일부 |
| **3a-9** | 에이전트 3 (Macro Strategist / 통합 Analyst / CIO) + `no_fabricated_numbers` + `task_callback` Mattermost + **판단 일기 스키마·로깅 훅** | 시나리오 6 |
| **3a-10** | report.py + notify.py + main.py (주간 크루 전체) | 통합 |
| **3a-11** | backtest.py (3a-2~8을 과거 데이터로 루프) | Gate A |
| **3b-1** | 애널리스트 3분할 (②③) + ④ News + ⑤ Research Director | — |
| **3b-2** | ⑥ PM + ⑦ Risk Officer + 반려 루프 | — |
| **3b-3** | 섀도 틸트 측정 리포트 (조직 on/off 효용) | — |
| **Phase 4** | ⑨ Performance Reviewer + 채점 job + 벡터 DB + `DiaryRAG.recall` | 별도 문서 |

> **세제**: 나무증권 확인 대기 중이나 코딩 차단 안 함 — `MODE=paper`가 먼저이고, 한국 양도세는 보유기간 무관 22% 단일이라 별도 로직 불필요 (연말 손실 하베스팅은 나중 정제).

---

## 10. repo 구조

```
US_stocks_AI_CrewBalancr/
├── docker-compose.yml  Dockerfile  pyproject.toml  uv.lock
├── .env.example  .gitignore  .claudeignore  .claude/settings.json
├── CLAUDE.md  SKILLS.md  PROMPTS.md  TEST_GUIDE.md
├── report/                       # 명세 (Phase 1~4)
├── aegisvest/
│   ├── main.py                   # 주간 크루 엔트리
│   ├── watchdog.py               # 일일 감시견 + 매크로 점수 누적
│   ├── pipeline.py               # run_pipeline() 결정론 코어
│   ├── config.py  llm.py  notify.py  report.py  schemas.py
│   ├── agents/                   # ①~⑨ Agent + Task 정의 (+ config/agents.yaml, tasks.yaml)
│   ├── tools/                    # market_data, fundamentals, macro_data, news,
│   │                             #   regime, screener, scoring, allocation,
│   │                             #   rebalance, constraints, portfolio_math
│   ├── broker/                   # paper.py, benchmarks.py, shadow.py
│   └── diary/                    # schema.py, logger.py  (Phase 4: evaluator.py, rag.py)
├── config/
│   ├── regime_rules.yaml         # 6축 임계값 + 보간 앵커
│   ├── allocation.yaml           # 가드레일, nav_tiers
│   ├── agents.yaml  tasks.yaml   # CrewAI 정의
│   ├── filters/{low,mid,high}.yaml
│   └── scoring/{low,mid,high}.yaml
├── state/  outputs/  data/cache/  # 런타임 (git-ignored, OMV 볼륨)
└── tests/  (fixtures/, test_tools/, test_pipeline.py)
```

---

## 11. 다음: Phase 4 (판단 일기 RAG)

- ⑨ Performance Reviewer 채점 파이프라인
- 벡터 DB (ChromaDB 임베디드 후보) + 로컬 임베딩 (bge-m3 후보)
- 일기 항목 스키마 확정 (judgment / data_snapshot / outcome / post_mortem / tags / embedding)
- `DiaryRAG.recall()` 회상 훅 — 각 에이전트 판단 전 유사 사례 주입
- 콜드 스타트·과적합 방지 전략
- 가동 시점: 모의투자 데이터 ~3개월 축적 후
