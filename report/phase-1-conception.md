# AegisVest — Phase 1 구상 보고서

> **작성일**: 2026-09-01
> **상태**: 확정
> **범위**: 리스크별 투자 전략 카테고리 세분화(A), 동적 자산 배분 규칙(B), CrewAI 조직 구조(C), Claude Code 설정 파일(D)

> ⚠️ 이 문서는 **시스템 설계 프레임워크**이며 투자 자문이 아니다. 모든 임계값은 백테스트·페이퍼트레이딩으로 재보정 전제.

---

## 프로젝트 정의

CrewAI 프레임워크 + DeepSeek LLM API 기반 미국 주식(S&P 500 / NASDAQ) 대상 **자율형 다중 에이전트 투자 조직 시스템**.

**핵심 파이프라인**: 투자 전략 수립 → 리스크별 전략 카테고리화·세분화 → 시장 상황·전략별 투자 비율(자산 배분) 차등 설정.

**기술 스택**: CrewAI (오케스트레이션), DeepSeek API (LLM, LiteLLM 경유), Python 3.11+.

---

## 과제 A. 리스크별 투자 전략 카테고리 세분화

각 카테고리는 **하드 필터(pass/fail)** → **스코어링(0~100)** → **서브티어 분류** 3단계.
에이전트는 하드 필터로 유니버스를 자르고, 스코어로 랭킹, 서브티어 태그를 부여한다.

### 🟢 저위험 — 배당 성장 & 우량 가치주

#### 하드 필터 (전부 통과해야 유니버스 편입)

| 지표 | 조건 | 근거 |
|---|---|---|
| 시가총액 | ≥ $10B | 라지캡 한정 |
| 60개월 베타 | 0.6 ≤ β ≤ 1.05 | 시장 대비 저변동 |
| 배당 이력 | 연속 증배 ≥ 10년 | Aristocrat/Achiever급 |
| 5년 배당성장률(DGR) | ≥ 5% | 인플레이션 방어 |
| 배당성향(EPS 기준) | 30% ~ 65% | 지속가능성 |
| FCF 배당성향 | ≤ 75% | 현금 기준 안전마진 |
| 순부채/EBITDA | ≤ 3.0 | 레버리지 통제 |
| 이자보상배율 | ≥ 5x | 채무 상환력 |
| ROE (5년 평균) | ≥ 12% | 자본 효율 |
| ROIC vs WACC | ROIC > WACC | 가치 창출 |
| EPS 흑자 연도 | 최근 10년 중 10년 | 이익 안정성 |
| Piotroski F-Score | ≥ 6 | 재무 건전성 |
| Altman Z-Score | ≥ 3.0 | 부도 위험 낮음 |
| 신용등급 | BBB+ 이상 (S&P) | 투자등급 |

#### 스코어링 가중치 (0~100)

- **밸류에이션 매력도 35%**: 현재 P/E vs 자체 5년 중앙값, EV/EBITDA vs 섹터, 배당수익률 vs 자체 5년 중앙값 (역사적 대비 저평가일수록 고점)
- **배당 품질 30%**: DGR 추세, 배당성향 여유, FCF 커버리지
- **수익성 안정성 25%**: ROE/ROIC 수준 및 표준편차(낮을수록 가점)
- **재무 안전성 10%**: F-Score, Z-Score, 부채비율

#### 서브티어

- `LOW-A 배당귀족 코어`: 연속 증배 ≥ 25년, β ≤ 0.9 → 포트폴리오 앵커
- `LOW-B 퀄리티 컴파운더`: ROIC ≥ 15%, DGR ≥ 8%, 다소 높은 밸류에이션 허용
- `LOW-C 디펜시브 밸류`: 배당수익률 상위, 경기방어 섹터(필수소비재·유틸리티·헬스케어), 저평가 깊음

#### 포지션 규칙

종목당 3~6%, 12~20 종목, 섹터당 ≤ 25%, 손절 없음(펀더멘털 훼손 시에만 청산 — F-Score < 4 또는 감배).

---

### 🟡 중위험 — GARP & 확고한 빅테크 성장주

#### 하드 필터

| 지표 | 조건 |
|---|---|
| 시가총액 | ≥ $20B |
| 매출 3년 CAGR | 10% ~ 30% |
| Forward EPS 성장률(컨센서스) | ≥ 12% |
| PEG (forward P/E ÷ 3~5년 EPS 성장률) | 0.8 ~ 2.0 (< 1.5 가점) |
| ROE | ≥ 15% |
| ROIC | ≥ 12% |
| 매출총이익률 | ≥ 40% |
| 영업이익률 추세 | 최근 3년 non-declining |
| FCF | 흑자 & 최근 3년 성장 |
| 순부채/EBITDA | ≤ 2.5 (순현금이면 최상) |
| 60개월 베타 | 0.9 ~ 1.4 |
| Rule of 40 (소프트웨어/플랫폼 한정) | 매출성장% + FCF마진% ≥ 40 |
| 컨센서스 EPS 리비전 (3개월) | 순상향 |

#### 스코어링 (0~100)

- **성장의 질 35%**: 매출·EPS 성장률, 성장 지속성(변동성 역가중), 리비전 모멘텀
- **밸류에이션 규율 30%**: PEG, EV/Sales vs 성장률, forward P/E vs 자체 5년 밴드
- **자본 효율 & 해자 25%**: ROIC 추세, 매출총이익률, 시장점유율 변화, 재투자율(R&D/매출)
- **재무 체력 10%**: 레버리지, 이자보상, FCF 전환율

#### 서브티어

- `MID-A GARP 코어`: PEG < 1.3, ROE > 18% — 성장·가치 균형점
- `MID-B 빅테크 GARP`: 메가캡 플랫폼, 예측가능 캐시플로우, 다소 높은 P/E 허용(PEG ≤ 2.0)
- `MID-C 사이클리컬 성장`: 산업재·반도체 장비 등, 사이클 위치 점검 필수(피크 마진 경계)

#### 포지션 규칙

종목당 3~5%, 10~15 종목, 밸류에이션 극단 이탈(forward P/E > 자체 밴드 +2σ) 시 트림, 소프트 손절 -20%(펀더멘털 재확인).

---

### 🔴 고위험 — 혁신 테마주 & 기술적 모멘텀

#### 하드 필터

| 지표 | 조건 |
|---|---|
| 시가총액 | ≥ $2B |
| 20일 평균 거래대금(ADV) | ≥ $30M (유동성) |
| 테마 태그 | AI/반도체·바이오테크·클린에너지·우주·양자·핀테크 중 1+ |
| 매출 성장률(YoY) | ≥ 30% *또는* 명확한 카탈리스트 있는 pre-revenue |
| 추세 | 종가 > 200일 SMA, 50일 SMA > 200일 SMA |
| 상대강도(RS) vs S&P 500 (6개월) | 상위 30% |
| 12-1 모멘텀 (최근 12개월 수익률 – 최근 1개월) | > 0 |
| RSI(14) | 45 ~ 78 (>80 과열 제외) |
| 최근 거래량 | 20일 평균 대비 상승 추세, 돌파 시 ≥ 1.5x |

#### 스코어링 (0~100)

- **추세·모멘텀 40%**: 이동평균 정렬, RS 순위, 12-1 모멘텀, 신고가 근접도(52주 고점 대비 -15% 이내 가점)
- **거래량 확인 20%**: OBV 추세, 돌파 거래량, 축적/분산 라인
- **테마 강도 25%**: 섹터 자금 흐름, 애널리스트 커버리지 증가, 뉴스/카탈리스트 밀도
- **펀더멘털 옵셔널리티 15%**: 매출 성장 가속, TAM, 현금 소진 런웨이(≥ 18개월)

#### 진입 타이밍 규칙 (에이전트가 명시)

- **눌림목 진입**: RSI 40~50로 조정 + 50일선 지지 유지
- **돌파 진입**: 저항 돌파 + 거래량 ≥ 1.5x
- **제외**: RSI > 80 + 200일선 대비 +40% 이상 확장

#### 서브티어

- `HIGH-A 세큘러 테마`: 구조적 성장 스토리(AI 인프라, GLP-1 등), 상대적으로 큰 캡 → 코어 테마 노출
- `HIGH-B 모멘텀 돌파`: 순수 기술적, 신고가 돌파, 짧은 보유
- `HIGH-C 스펙 옵셔널리티`: 소형 바이오/pre-revenue, 이벤트 드리븐(FDA·수주), 최소 사이즈

#### 포지션 규칙

종목당 1~2.5%, 8~15 종목, **하드 손절 -15~25% (ATR 기반)**, 트레일링 스톱(20일 저점), 개별 이벤트(실적·FDA) 전 사이즈 절반.

---

## 과제 B. 동적 자산 배분 규칙

### B-1. 매크로 레짐 판별 (복합 스코어)

6개 축, 각 -2 ~ +2 점. **양수 = risk-on**.

| 축 | +2 (강세) | 0 (중립) | -2 (약세/위기) |
|---|---|---|---|
| **VIX 레벨 + 기간구조** | VIX < 15 & 콘탱고(VIX < VIX3M) | 15~22 | VIX > 28 또는 백워데이션 |
| **S&P 500 추세** | 종가 > 200일 SMA & 50일 SMA 상승 | 200일선 ±2% 횡보 | 종가 < 200일 SMA & 50일선 하락 |
| **시장 폭(Breadth)** | 200일선 상회 종목 > 60% | 45~60% | < 35% |
| **일드커브 + 정책** | 10Y-3M 정상(+) & Fed 동결/인하 | 평탄 | 역전 심화 또는 역전 후 급격 재정상화(침체 임박 신호) |
| **신용 스프레드 (HY OAS)** | < 350bp & 축소 | 350~500bp | > 500bp 또는 급확대(주간 +75bp) |
| **경기 (ISM PMI + Sahm)** | PMI > 52 & 실업률 안정 | PMI 48~52 | PMI < 48 또는 Sahm Rule 발동 |

**총점 → 레짐**

- **+5 이상**: 🐂 강세장 (Risk-On)
- **-4 ~ +4**: ⚖️ 평시 / 횡보 (Neutral)
- **-5 이하**: 🐻 약세장 / 위기 (Risk-Off)
- 특례: VIX > 35 **또는** HY OAS > 700bp → 총점 무관 **위기 모드 강제**

**히스테리시스**: 레짐 전환은 **연속 3거래일** 임계 유지 시에만 확정(휩쏘 방지). 위기 모드 진입은 1일, 해제는 5일(비대칭).

### B-2. 카테고리별 배분 모델

**계층 1 — 리스크 자산 vs 안전 버퍼**

| 레짐 | 주식 슬리브 | 현금/T-Bill/단기채 |
|---|---|---|
| 🐂 강세 | 95% | 5% |
| ⚖️ 평시 | 85% | 15% |
| 🐻 약세 | 65% | 35% |
| 🆘 위기 강제 | 50% | 50% |

**계층 2 — 주식 슬리브 내 3카테고리 배분 (슬리브 100% 기준)**

| 레짐 | 🟢 저위험 | 🟡 중위험 | 🔴 고위험 |
|---|---|---|---|
| 🐂 강세 | 40% | 40% | 20% |
| ⚖️ 평시 | 55% | 32% | 13% |
| 🐻 약세 | 72% | 23% | 5% |
| 🆘 위기 | 85% | 15% | 0% |

**전체 포트 환산 예시 (평시)**: 저 55%×85% = 46.75%, 중 32%×85% = 27.2%, 고 13%×85% = 11.05%, 현금 15%.

### B-3. 가드레일 (에이전트 하드 제약)

- 리밸런싱 밴드: 목표 대비 **절대 ±4%p** 또는 **상대 ±25%** 이탈 시에만 거래 (거래비용·세금 절감)
- 1회 리밸런싱당 카테고리 배분 변경 ≤ 15%p (급격한 레짐 오판 방어)
- 고위험 카테고리 총 노출 상한: 전체 포트의 **20%** 절대 캡 (레짐 무관)
- 단일 종목 상한: 전체 포트의 8%
- 단일 섹터 상한: 전체 포트의 30%
- 현금 하한: 강세장에도 3%

### B-4. Phase 2로 이월된 논의

1. **매크로 데이터 소스 신뢰도 계층** — FRED(공식) vs 실시간 프록시(ETF 흐름), 발표 지연(PMI는 익월 1일, 고용은 익월 첫 금요일) 처리
2. **리밸런싱 주기 3안**: (a) 고정 월 1회, (b) 밴드 트리거 + 최소 2주 쿨다운, (c) 레짐 전환 이벤트 드리븐 + 분기 정기점검 — 각 안의 회전율·비용·추적오차 트레이드오프
3. 레짐 스코어의 **연속값(-12~+12) → 배분 연속 보간** vs 이산 3구간

---

## 과제 C. CrewAI 조직 구조

> ⚠️ **이 절은 Phase 3에서 대체됨** → [phase-3-organization-and-paper-trading.md](phase-3-organization-and-paper-trading.md)
> Phase 3 확정 사항: **9-에이전트 4계층 펀드 운용 조직** (얇은 3-에이전트안 폐기), 에이전트 **재량 한계**(카테고리 ±3%p / 스코어 상위 풀 내 선택 / veto 가능·편입 불가 / 가드레일 불가침), **백테스트=결정론 코어만 / 조직=라이브 섀도 A/B**, `task_callback` 기반 Mattermost 모니터링, 판단 일기 RAG(Phase 4).
> 아래 원안(4~8 에이전트 스케치)은 **이력 보존용**. C-3(할루시네이션 방지)의 원칙은 Phase 3에서도 유효.

### C-1. 에이전트 정의 (원안 — 대체됨)

> **1인 개발 MVP 권고**: 아래 8개 중 **★ 4개만 먼저 구현**하고 나머지는 파이프라인 검증 후 추가.

#### ★ 1. Macro Regime Analyst (매크로 레짐 분석가)

- **Role**: 미국 매크로 환경 레짐 판별관
- **Goal**: B-1의 6축 스코어를 **오직 툴이 반환한 수치로만** 계산해 레짐을 `BULL/NEUTRAL/BEAR/CRISIS` 중 하나로 확정하고, 각 축 점수와 근거 데이터를 JSON으로 출력한다
- **Backstory**: "당신은 15년간 글로벌 매크로 헤지펀드에서 레짐 신호를 운용했다. 당신은 예측하지 않는다 — 오직 규칙표에 데이터를 대입할 뿐이다. 데이터가 없으면 '판단 불가'라고 말한다. 당신은 직감을 경멸한다."
- **Tools**: `MacroDataTool`, `MarketDataTool`, `RegimeScoreCalculator`
- `allow_delegation=False`, `temperature=0.0`

#### ★ 2. Portfolio Allocation Officer (CIO / 배분 담당관)

- **Role**: 최고투자책임자 — 레짐 → 카테고리 배분 결정
- **Goal**: Macro Analyst의 레짐 산출물을 받아 B-2 배분표를 **툴로 조회**하고, 현재 포트폴리오 대비 리밸런싱 밴드(B-3)를 적용해 목표 배분과 필요 거래 방향을 산출한다
- **Backstory**: "당신은 100억 달러 자산배분 위원회를 이끌었다. 당신의 규칙은 성문화되어 있고, 당신은 규칙을 어기지 않는다. 시장 예측가가 회의에서 떠들면 당신은 배분표를 가리킨다."
- **Tools**: `AllocationTableTool`, `PortfolioStateTool`, `RebalanceBandChecker`
- `allow_delegation=False`, `temperature=0.0`

#### ★ 3. Equity Screening Analyst (통합 종목 스크리너)

> MVP에서는 저/중/고 3명을 **1명 + 파라미터**로 통합. 검증 후 3명으로 분리.

- **Role**: 리스크 카테고리별 종목 스크리너
- **Goal**: 주어진 카테고리(`LOW`/`MID`/`HIGH`)에 대해 과제 A의 하드 필터를 `ScreenerTool`로 실행하고, 통과 종목에 스코어링 공식을 적용해 상위 N개와 서브티어 태그, 각 지표 원본값을 반환한다
- **Backstory**: "당신은 정량 리서치 데스크의 스크리닝 엔진이다. 당신은 종목을 '좋아하지' 않는다. 필터를 통과하거나 못 하거나 둘 중 하나다. 모든 수치는 데이터 벤더에서 나오며, 당신은 그것을 만들어내지 않는다."
- **Tools**: `ScreenerTool`, `FundamentalsTool`, `TechnicalIndicatorTool`, `ScoringCalculator`
- `allow_delegation=False`, `temperature=0.1`

#### ★ 4. Quantitative Risk Validator (정량 검증관 / 리스크 매니저)

- **Role**: 최종 포트폴리오 수치 검증 및 리스크 제약 집행관
- **Goal**: Allocation Officer의 목표 배분과 Screener의 종목 리스트를 받아 (1) 모든 수치를 툴로 **독립 재계산**해 대조, (2) B-3 가드레일 전부 검증, (3) 포지션 사이징 계산, (4) 불일치·위반 시 `REJECTED` + 사유 반환
- **Backstory**: "당신은 리스크 부서다. 프론트오피스는 당신을 싫어한다. 당신은 그들이 제출한 모든 숫자를 다시 계산하고, 0.5% 넘게 어긋나면 반려한다. 당신은 '대충 맞다'를 받아들인 적이 없다."
- **Tools**: `PortfolioMathTool`, `PositionSizer`, `ConstraintChecker`, `FundamentalsTool`
- `allow_delegation=False`, `temperature=0.0`

#### 5. Portfolio Manager (조립 & 리포트) — *2차*

- **Role**: 최종 포트폴리오 조립 및 투자 메모 작성
- **Goal**: 검증 통과한 배분·종목을 최종 포트폴리오 테이블로 조립하고, 리밸런싱 주문 리스트와 사람이 읽을 근거 메모를 생성한다. **새로운 수치를 만들지 않고** 상류 산출물만 조합한다
- **Backstory**: "당신은 편집자다. 저자(분석가)들이 팩트를 준다. 당신은 문장을 만들 뿐 팩트를 바꾸지 않는다."
- **Tools**: `ReportFormatterTool` (계산 툴 없음 — 의도적)
- `temperature=0.3`

#### 6. Devil's Advocate / Red Team — *3차*

- **Goal**: 최종 포트폴리오에 대해 반대 시나리오(레짐 오판, 밸류에이션 함정, 크라우딩) 3가지를 제시하고 각각 툴로 검증 가능한 반증 지표를 제시
- `temperature=0.5` (여기선 발산 허용 — 단 수치는 여전히 툴)

#### 7~8. Data Ingestion Agent / Compliance Agent — *필요 시*

### C-2. 데이터 흐름

**권고: Sequential 메인 파이프라인 + 부분 병렬**

```
[Macro Regime Analyst]
        │ (regime JSON)
        ▼
[Portfolio Allocation Officer]
        │ (target allocation JSON)
        ▼
[Equity Screening Analyst] ── LOW  ┐
[Equity Screening Analyst] ── MID  ├─ async_execution=True (병렬)
[Equity Screening Analyst] ── HIGH ┘
        │ (candidate lists)
        ▼
[Quantitative Risk Validator]  ──→ REJECTED면 Allocation Officer로 1회 재요청
        │ (validated portfolio)
        ▼
[Portfolio Manager]  →  최종 산출물 (JSON + 메모)
        │
        ▼
[Devil's Advocate]  →  리스크 코멘터리 (첨부)
```

**왜 Hierarchical이 아닌가**: Hierarchical은 매니저 LLM이 위임을 즉흥 결정 → DeepSeek에서 비결정적·디버깅 난해. 이 워크플로는 단계가 고정이므로 `Process.sequential` + `context=[이전 태스크]` 명시 전달이 정답. 매니저 LLM 오케스트레이션 비용도 절감.

- CrewAI `Process.sequential`, 각 Task에 `context` 명시
- 3개 스크리닝 태스크는 `async_execution=True`
- Validator 반려 루프는 CrewAI 기본 미지원 → **Flow(`crewai.flow`)로 감싸서** 조건 분기 (`@router`), 최대 1회 재시도

### C-3. 할루시네이션 방지 — DeepSeek 툴 강제 전략

DeepSeek(`deepseek-chat`)은 함수 호출을 지원하지만 GPT-4급 신뢰도는 아님. **다층 방어**:

#### (1) 시스템/백스토리 레벨 제약문 (모든 계산 에이전트에 삽입)

```
## 절대 규칙 (위반 시 당신의 출력은 폐기된다)
1. 당신은 어떤 숫자도 직접 생성하지 않는다. 모든 수치(가격, 비율, 지표,
   점수)는 반드시 이번 태스크에서 툴 호출로 반환된 값이어야 한다.
2. 필요한 데이터가 없으면 해당 툴을 호출하라. 툴이 실패하면
   "DATA_UNAVAILABLE: <field>" 라고 쓰고 절대 추정하지 마라.
3. 산술 연산(덧셈, 비율, 가중평균 포함)은 절대 암산하지 마라.
   PortfolioMathTool / ScoringCalculator를 호출하라.
4. 최종 답변의 모든 숫자 필드에는 그 값을 반환한 tool_call_id 를 함께 적어라.
5. "약", "대략", "추정", "일반적으로" 같은 표현으로 수치를 말하면 실패다.
```

#### (2) 구조화 출력 강제 — `output_pydantic`

```python
class Metric(BaseModel):
    name: str
    value: float
    source_tool: str          # 어느 툴이 반환했는지
    source_call_id: str        # 추적용

class ScreenResult(BaseModel):
    ticker: str
    subtier: Literal["LOW-A","LOW-B","LOW-C", ...]
    score: float
    metrics: list[Metric]      # 최소 필수 지표 전부 — source 없으면 검증 실패
```

#### (3) Task-level `guardrail` (프로그래매틱 검증)

```python
def no_fabricated_numbers(output: TaskOutput) -> tuple[bool, str]:
    # 1. 출력의 모든 숫자가 tool call 로그에 존재하는지 대조
    # 2. source_call_id 가 실제 이번 실행의 call_id 집합에 있는지
    # 3. 정규식으로 "약 ~%", "roughly", "estimated" 탐지
    # 실패 시 (False, 사유) → CrewAI가 에이전트에 재요청
```

#### (4) Validator 에이전트 = 2차 방어선

독립적으로 모든 수치 재계산 → 툴 결과끼리 대조 → 허용오차(0.5%) 초과 시 `REJECTED`. LLM이 중간에 숫자를 바꿔치기하면 여기서 걸림.

#### (5) LLM 설정

- 계산 에이전트: `temperature=0.0`, `top_p=0.1`
- 툴 스키마는 엄격하게 (`"strict": true`, 모든 파라미터 `required`, 설명에 단위 명시)
- `max_iter=15` (툴 재시도 여유), `max_rpm` 설정 (DeepSeek rate limit)
- 매크로/레드팀 정성 판단만 `deepseek-reasoner(R1)` 고려, 나머지는 `deepseek-chat`

#### (6) 툴 설계 원칙

- 툴이 **계산까지 완료**해서 반환 (에이전트는 조립만). 예: `ScoringCalculator`가 가중치 적용한 최종 점수를 주고, LLM은 랭킹 정렬만.
- 모든 숫자 계산을 Python 툴로 밀어내면 LLM은 "어떤 툴을 부를지"만 결정 → 환각 표면적 최소화.

---

## 과제 D. Claude Code 설정 파일

> **정확성 참고**: `.claudeignore`는 현재 Claude Code에서 공식 지원이 불확실. 검색·파일 스캔 제외의 **실효 메커니즘은 `.gitignore` + `.claude/settings.json`의 permission deny**. 아래에 `.claudeignore`도 제공하되, 확실한 격리는 `settings.json`으로.

### D-1. `.gitignore` (실질적 스캔 제외 — 우선 사용)

```gitignore
# venv / python
.venv/
venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/

# secrets
.env
*.key

# data cache (API 응답 캐시 — 대용량, 재생성 가능)
data/cache/
*.parquet
*.duckdb

# outputs
outputs/
logs/
*.log

# notebooks scratch
*.ipynb_checkpoints/
```

### D-2. `.claude/settings.json` (하드 격리)

```json
{
  "permissions": {
    "deny": [
      "Read(./.venv/**)",
      "Read(./data/cache/**)",
      "Read(./.env)",
      "Read(./**/*.parquet)",
      "Read(./logs/**)",
      "Bash(rm -rf*)",
      "Bash(git push*)"
    ],
    "allow": [
      "Bash(pytest*)",
      "Bash(ruff*)",
      "Bash(python -m*)",
      "Bash(uv*)"
    ]
  }
}
```

### D-3. `.claudeignore` (지원 시 보조용)

```
.venv/
venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
data/cache/
outputs/
logs/
*.parquet
*.duckdb
*.log
.env
```

### D-4. `CLAUDE.md`

```markdown
# AegisVest — CrewAI 미국주식 다중 에이전트 투자 시스템

## 프로젝트 개요
CrewAI + DeepSeek API로 미국 주식(S&P500/NASDAQ)을 대상으로 한 자율형
다중 에이전트 투자 조직. 파이프라인: 매크로 레짐 판별 → 카테고리 배분
결정 → 리스크별 종목 스크리닝 → 정량 검증 → 포트폴리오 조립.

## 기술 스택
- Python 3.11+, 패키지 관리: uv
- CrewAI (오케스트레이션), crewai-tools
- DeepSeek API via LiteLLM (`deepseek/deepseek-chat`)
- 데이터: FMP / FRED / yfinance, pandas, pandas-ta
- 검증: pytest, ruff, mypy

## 빌드 / 실행 / 테스트
    uv sync                          # 의존성 설치
    uv run python -m aegisvest.main   # 전체 크루 실행
    uv run pytest                     # 전체 테스트
    uv run pytest tests/test_tools/   # 툴 단위 테스트만
    uv run ruff check . && uv run mypy aegisvest/

## 3대 리스크 전략 (핵심 요약)
| 티어 | 정의 | 핵심 필터 | 포지션 |
|---|---|---|---|
| 저위험 | 배당성장·우량가치 | b 0.6~1.05, 연속증배>=10y, 배당성향 30~65%, ROE>=12%, F-Score>=6 | 3~6%/종목, 손절 없음 |
| 중위험 | GARP·빅테크 성장 | PEG 0.8~2.0, 매출CAGR 10~30%, ROE>=15%, GPM>=40%, Rule of 40 | 3~5%/종목, 소프트손절 -20% |
| 고위험 | 혁신테마·모멘텀 | 종가>200SMA, 50>200 SMA, RS 상위30%, RSI 45~78, 거래량 확인 | 1~2.5%/종목, 하드손절 -15~25% |

## 레짐별 배분 (주식 슬리브 100% 기준)
| 레짐 | 저 | 중 | 고 | 현금(전체) |
|---|---|---|---|---|
| 강세 | 40 | 40 | 20 | 5% |
| 평시 | 55 | 32 | 13 | 15% |
| 약세 | 72 | 23 | 5 | 35% |
| 위기 | 85 | 15 | 0 | 50% |
고위험 절대 상한 20%. 리밸런싱 밴드 +-4%p 또는 상대 +-25%.

## 아키텍처 규칙 (에이전트가 지켜야 함)
- 모든 수치는 Python 툴 반환값만 사용. LLM 암산 금지. 상세: PROMPTS.md
- 파이프라인은 Process.sequential + Flow 조건분기. Hierarchical 금지.
- 신규 의존성 추가 전 확인 요청. 기존 스택으로 해결 우선.
- 새 추상화(단일 구현 인터페이스, 팩토리) 만들지 말 것.

## 디렉토리
- aegisvest/agents/ 에이전트·태스크 정의
- aegisvest/tools/ Python 툴 (금융/매크로/계산)
- aegisvest/config/ 배분표·필터 임계값 (YAML)
- tests/ pytest
- report/ 구상·명세 단계 근거 문서 (개발 시 참조)
```

### D-5. `SKILLS.md`

```markdown
# SKILLS.md — Python 툴 인터페이스 규격

모든 툴은 crewai_tools.BaseTool 상속. 규칙:
- args_schema 는 Pydantic, 모든 필드 Field(description=..., 단위 명시)
- 반환은 항상 JSON 직렬화 가능 dict. 실패 시 {"error": "...", "field": "..."}
- 절대 예외를 raise 하지 않고 error dict 반환 (에이전트가 DATA_UNAVAILABLE 처리)
- 네트워크 호출은 data/cache/ 에 24h TTL 캐시 (requests-cache 또는 수동)
- 모든 수치 계산은 툴 내부에서 완료. 에이전트에 raw 만 주지 말 것.

## 1. MarketDataTool
목적: 가격/거래량/이동평균/베타
    Input:  ticker: str, lookback_days: int = 400
    Output: {
      "ticker": str, "last_price": float, "sma_50": float, "sma_200": float,
      "rsi_14": float, "atr_14": float, "beta_60m": float,
      "adv_20d_usd": float, "rs_vs_spx_6m": float,  # 백분위 0~100
      "mom_12_1": float, "pct_from_52w_high": float,
      "as_of": "YYYY-MM-DD"
    }
소스: yfinance 우선, FMP 폴백. 지표는 pandas-ta.

## 2. FundamentalsTool
목적: 재무제표 기반 지표
    Input:  ticker: str
    Output: {
      "market_cap_usd": float, "pe_forward": float, "pe_ttm": float,
      "pe_5y_median": float, "ev_ebitda": float, "peg_forward": float,
      "roe_5y_avg": float, "roic": float, "wacc_est": float,
      "gross_margin": float, "op_margin_trend_3y": "rising|flat|falling",
      "rev_cagr_3y": float, "eps_growth_fwd": float,
      "fcf_ttm_usd": float, "fcf_payout": float, "eps_payout": float,
      "net_debt_ebitda": float, "interest_coverage": float,
      "div_streak_years": int, "dgr_5y": float, "div_yield": float,
      "div_yield_5y_median": float,
      "piotroski_f": int, "altman_z": float, "rule_of_40": float,
      "eps_positive_years_10": int, "credit_rating": str,
      "as_of": "YYYY-MM-DD"
    }
소스: FMP (primary). 계산 지표(F-score, Z-score, Rule of 40, PEG)는 툴이 산출.

## 3. MacroDataTool
목적: 레짐 6축 raw 데이터
    Input:  {} (전부 최신)
    Output: {
      "vix": float, "vix3m": float, "vix_term_structure": "contango|backwardation",
      "spx_last": float, "spx_sma_200": float, "spx_sma_50": float,
      "spx_50_slope_20d": float,
      "pct_stocks_above_200dma": float,
      "yc_10y_3m": float, "yc_10y_2y": float,
      "yc_regime": "normal|flat|inverted|re-steepening",
      "fed_funds_trend": "hiking|hold|cutting",
      "hy_oas_bp": float, "hy_oas_4w_change_bp": float,
      "ism_pmi": float, "unemployment_rate": float, "sahm_gap": float,
      "as_of": "YYYY-MM-DD", "stale_fields": [str]  # 발표지연으로 오래된 필드
    }
소스: FRED (VIXCLS, T10Y3M, BAMLH0A0HYM2, UNRATE 등) + yfinance(^VIX, ^VIX3M, SPY).
ISM PMI 는 FRED 무료 미제공 -> 프록시 또는 수동 config 입력.

## 4. RegimeScoreCalculator
    Input:  MacroDataTool 출력 dict
    Output: {
      "axis_scores": {"vix": int, "spx_trend": int, "breadth": int,
                      "yield_policy": int, "credit": int, "macro": int},  # 각 -2~+2
      "total_score": int,
      "regime": "BULL|NEUTRAL|BEAR|CRISIS",
      "crisis_override": bool,
      "rationale": {axis: "임계값 대입 설명"}
    }
로직은 config/regime_rules.yaml 의 임계값 테이블. LLM 관여 0.

## 5. ScreenerTool
    Input:  category: "LOW"|"MID"|"HIGH", universe: "SP500"|"NASDAQ100"|"combined"
    Output: {
      "category": str,
      "passed": [{"ticker": str, "hard_filters": {name: {"value": float, "pass": bool}}}],
      "failed_count": int, "as_of": "YYYY-MM-DD"
    }
config/filters/{low,mid,high}.yaml 의 하드 필터 임계값 적용.
FundamentalsTool/MarketDataTool 를 배치 호출.

## 6. ScoringCalculator
    Input:  category: str, tickers: list[str]
    Output: {"scores": [{"ticker": str, "score": float, "subtier": str,
                         "component_scores": {...}}]}
config/scoring/{category}.yaml 가중치. 정규화(percentile rank) 후 가중합.

## 7. AllocationTableTool
    Input:  regime: str
    Output: {"equity_sleeve_pct": float, "cash_pct": float,
             "category_targets": {"LOW": float, "MID": float, "HIGH": float},
             "guardrails": {"high_abs_cap": 0.20, "single_name_cap": 0.08, ...}}
config/allocation.yaml.

## 8. PortfolioStateTool / RebalanceBandChecker
현재 보유(state/portfolio.json) 로드, 목표 대비 이탈 계산, 밴드 초과 종목만 반환.

## 9. PortfolioMathTool / PositionSizer / ConstraintChecker
- PortfolioMathTool: 가중평균, 노출 집계, 기여도 — 범용 산술
- PositionSizer: ATR 기반 고위험 사이징, 카테고리 예산 내 균등/스코어가중
- ConstraintChecker: 모든 가드레일 pass/fail + 위반 리스트

## 10. ReportFormatterTool
계산 없음. 상류 JSON -> 마크다운 테이블 + 주문 리스트 포맷팅만.
```

### D-6. `PROMPTS.md`

```markdown
# PROMPTS.md — 에이전트 프롬프트 관리 가이드

## 원칙
- 프롬프트는 코드가 아닌 config/agents.yaml, config/tasks.yaml 에 둔다
  (CrewAI YAML 방식). 이 파일은 작성 규칙과 리뷰 체크리스트.
- 모든 계산 에이전트 backstory 에 "절대 규칙" 블록(아래) 공통 삽입.
- 페르소나는 3~4문장. 장황 금지 (컨텍스트 낭비).

## 공통 삽입 블록: 절대 규칙 (계산 에이전트 전용)
    ## 절대 규칙 (위반 시 출력 폐기)
    1. 어떤 숫자도 직접 생성하지 않는다. 모든 수치는 이번 태스크의 툴
       호출 반환값이어야 한다.
    2. 데이터가 없으면 툴을 호출하라. 툴 실패 시 "DATA_UNAVAILABLE: <필드>"
       라고만 쓰고 추정하지 마라.
    3. 산술(비율, 가중평균 포함) 암산 금지. 계산 툴을 호출하라.
    4. 출력의 모든 숫자 필드에 source_tool 과 source_call_id 를 붙여라.
    5. "약", "대략", "추정" 으로 수치를 말하면 실패다.

## 에이전트별 규격

### macro_regime_analyst
- role: "미국 매크로 레짐 판별관"
- goal: "MacroDataTool 로 raw 데이터를 수집하고 RegimeScoreCalculator 로
  레짐을 확정한다. 6축 점수와 근거를 RegimeResult 스키마로 출력한다."
- backstory: [페르소나 3문장] + [절대 규칙 블록]
- llm: deepseek/deepseek-chat, temperature 0.0
- tools: MacroDataTool, MarketDataTool, RegimeScoreCalculator
- allow_delegation: false

### allocation_officer
- role: "최고투자책임자 — 카테고리 배분 결정관"
- goal: "레짐을 받아 AllocationTableTool 로 목표 배분을 조회하고,
  RebalanceBandChecker 로 실제 필요한 거래만 식별한다."
- llm: temperature 0.0
- tools: AllocationTableTool, PortfolioStateTool, RebalanceBandChecker

### equity_screener (파라미터화: category)
- role: "{category} 리스크 카테고리 종목 스크리너"
- goal: "ScreenerTool 로 하드필터 통과 종목을 얻고 ScoringCalculator 로
  점수·서브티어를 매긴 뒤 상위 {top_n} 를 ScreenResult 리스트로 반환한다."
- llm: temperature 0.1
- tools: ScreenerTool, FundamentalsTool, TechnicalIndicatorTool, ScoringCalculator

### risk_validator
- role: "정량 검증관 / 리스크 제약 집행관"
- goal: "상류 산출물의 모든 수치를 독립 재계산해 0.5% 허용오차로 대조하고,
  ConstraintChecker 로 전 가드레일을 검증한다. 불일치·위반 시 REJECTED 와
  사유 리스트를 반환한다."
- llm: temperature 0.0
- tools: PortfolioMathTool, PositionSizer, ConstraintChecker, FundamentalsTool

### portfolio_manager  (계산 툴 없음 — 의도적)
- role: "포트폴리오 조립 및 투자 메모 편집자"
- goal: "검증 통과 데이터만 조합해 최종 포트폴리오 테이블, 주문 리스트,
  근거 메모를 생성한다. 새 수치를 만들지 않는다."
- llm: temperature 0.3
- tools: ReportFormatterTool

## 태스크 작성 규칙 (config/tasks.yaml)
- description 에 입력 컨텍스트 출처 명시 (context: [이전 태스크])
- expected_output 에 Pydantic 스키마 이름 명시
- 3개 스크리닝 태스크: async_execution true
- 각 태스크에 guardrail 함수 지정 (no_fabricated_numbers 등)

## 리뷰 체크리스트 (프롬프트 수정 시)
- [ ] backstory 4문장 이하인가
- [ ] 계산 에이전트에 절대 규칙 블록 있는가
- [ ] goal 에 사용할 툴 이름이 명시되었는가
- [ ] temperature 가 역할에 맞는가 (계산 0.0, 조립 0.3, 레드팀 0.5)
- [ ] expected_output 에 스키마 지정되었는가
```

### D-7. `.env.example`

```bash
# --- LLM: DeepSeek (LiteLLM 경유) ---
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
MODEL=deepseek/deepseek-chat
DEEPSEEK_API_BASE=https://api.deepseek.com
REASONER_MODEL=deepseek/deepseek-reasoner
LLM_TEMPERATURE=0.0
LLM_MAX_RPM=20

# --- 금융 데이터 API ---
FMP_API_KEY=xxxxxxxx           # Financial Modeling Prep (재무제표·스크리너, primary)
FRED_API_KEY=xxxxxxxx          # FRED (매크로, 무료)
ALPHAVANTAGE_API_KEY=          # 폴백/보조 (선택)
POLYGON_API_KEY=
FINNHUB_API_KEY=

# --- 실행 설정 ---
UNIVERSE=combined              # SP500 | NASDAQ100 | combined
CACHE_TTL_HOURS=24
CACHE_DIR=./data/cache
PORTFOLIO_STATE_PATH=./state/portfolio.json
OUTPUT_DIR=./outputs
LOG_LEVEL=INFO

# --- ISM PMI 수동 입력 (FRED 무료 미제공 시) ---
MANUAL_ISM_PMI=
MANUAL_ISM_PMI_ASOF=

# --- 안전장치 ---
DRY_RUN=true                   # true면 주문 파일만 생성, 실행 안 함
MAX_HIGH_RISK_EXPOSURE=0.20
```

### D-8. `TEST_GUIDE.md`

```markdown
# TEST_GUIDE.md — 자율 코드 검증 시나리오

Claude Code 는 코드 작성 후 아래를 자율 실행하고, 실패 시 수정한다.
프레임워크는 pytest 만. fixture 남발 금지. 툴별 1개 스모크 테스트 원칙.

## 실행 순서
    uv run ruff check . --fix
    uv run mypy aegisvest/
    uv run pytest -x -q

## 시나리오 1 — 툴 계약 준수 (tests/test_tools/)
각 툴에 대해:
- 정상 입력 -> 반환 dict 에 규격(SKILLS.md)의 모든 키 존재, 타입 일치
- 잘못된 ticker ("ZZZZ") -> 예외 raise 하지 않고 {"error": ...} 반환
- 네트워크 차단 상황(monkeypatch) -> error dict, 프로세스 안 죽음
- 캐시: 2회 연속 호출 시 2번째는 네트워크 미호출 (호출 카운터 mock)

## 시나리오 2 — RegimeScoreCalculator 결정성 (핵심)
config 임계값 대비 경계값 테스트:
- VIX=14.9 -> vix 축 +2 / VIX=15.0 -> 0 / VIX=28.1 -> -2
- 인위적 6축 raw -> total_score 계산이 B-1 표와 정확히 일치
- total_score +5 -> BULL, +4 -> NEUTRAL, -5 -> BEAR
- VIX=36 이면 total_score 무관 CRISIS (override 플래그 true)
- 같은 입력 3회 -> 완전히 동일한 출력 (LLM 미개입 확인)

## 시나리오 3 — 스크리닝 필터 정확성
합성 종목 데이터셋(fixtures/synthetic_universe.json, ~30종목):
- b=1.2 종목은 LOW 하드필터 탈락
- PEG=2.5 종목은 MID 탈락
- 종가 < 200SMA 종목은 HIGH 탈락
- 통과 종목 수가 0이면 빈 리스트 반환 (크래시 아님)

## 시나리오 4 — 배분 가드레일 (ConstraintChecker)
- 고위험 합계 22% 포트 -> 위반 감지, violation 리스트에 "high_abs_cap"
- 단일 종목 9% -> 위반
- 리밸런싱 밴드: 목표 40% vs 현재 42% -> 거래 불필요 (밴드 내)
- 목표 40% vs 현재 47% -> 거래 필요

## 시나리오 5 — 파이프라인 통합 (mock LLM)
- DeepSeek 호출을 결정적 stub 로 교체 (recorded responses)
- 전체 크루 실행 -> 최종 출력이 PortfolioResult 스키마 통과
- Validator 가 REJECTED 반환하도록 조작 -> Flow 가 재시도 1회 후 중단
- 최종 포트폴리오 카테고리 합 + 현금 = 100% (+-0.1%)

## 시나리오 6 — 할루시네이션 가드
- 에이전트 출력에 source_call_id 없는 숫자 필드 주입 -> guardrail 이 reject
- 출력에 "약 15%" 문자열 -> 정규식 guardrail 이 reject

## 통과 기준
- 모든 테스트 green, ruff/mypy 클린
- 시나리오 2, 4, 6 은 반드시 통과 (시스템 신뢰성 핵심). 실패 시 배포 불가.
- 커버리지 목표는 두지 않음. 위 시나리오가 실제 리스크를 커버함.
```

---

## Phase 1 미해결 항목 (Phase 2 논의 대상)

1. **매크로 판별 기준 정교화**: 데이터 발표 지연 처리, FRED 미제공 지표(ISM PMI) 프록시, 레짐 스코어 연속값 → 배분 연속 보간 vs 이산 3구간, 히스테리시스 파라미터 튜닝
2. **리밸런싱 주기**: 고정 월간 vs 밴드 트리거+쿨다운 vs 이벤트 드리븐의 회전율·비용·추적오차 트레이드오프, 레짐 전환 리밸런싱과 종목 리밸런싱 분리 여부
3. **에이전트 수 확정**: MVP 4개 → 최종 6~8개 확장 시점

## Phase 2 이후로 명시적으로 미룬 것

- 백테스트 엔진 상세 설계
- 세금 / 거래비용 모델
- 6개 설정 파일의 실제 레포 커밋 (명세 확정 후)
