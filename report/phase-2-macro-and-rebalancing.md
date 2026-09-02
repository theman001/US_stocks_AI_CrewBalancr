# AegisVest — Phase 2 구상 보고서: 매크로 판별 기준 & 리밸런싱 주기

> **작성일**: 2026-09-01
> **상태**: 확정 (일부 항목 Phase 3 이월, 세제 항목 잠정)
> **선행 문서**: [phase-1-conception.md](phase-1-conception.md)

---

## 0. 결정 요약

| # | 결정 사항 | 선택 | 비고 |
|---|---|---|---|
| 1 | 점수 → 배분 변환 방식 | **슬라이드식(연속 보간)** + 라벨 유지 | 계단식의 경계 절벽·휩쏘 회피 |
| 2 | "경기" 축 데이터 | **복합 지표** (WEI + 지역연준 + 실업청구) | `MANUAL_ISM_PMI` 오버라이드 유지, 유료 ISM API 전환 지점 문서화 |
| 3 | 실행 주기 | **주간 풀 크루 + 매일 감시견** | 감시견이 일일 매크로 점수 계산도 겸함 (LLM 미사용) |
| 4-a | 초기 운용 방식 | 10만원 모의투자 → 성적 양호 시 적금형 월납입 | **현금흐름 리밸런싱** 규칙 추가. 모의투자 하네스는 Phase 3 |
| 4-b | 계좌·세제 | 나무증권 해외주식 (한국 거주자), **추후 확정** | 잠정 세제 규칙 문서화 |
| 4-c | 주문 집행 | **리포트만** (`MODE=paper` / `DRY_RUN=true`) | 신뢰 축적 후 자동 집행 검토 |
| 4-d | 실행 환경 | Radxa Rock 5 ITX (ARM64, 32GB), **컨테이너 내 스케줄러** | supercronic + 단일 컴포즈 파일 (OMV8) |
| 5 | 성공 판정 기준 | **2단 게이트** (백테스트 A + 모의투자 B) | 상세 §6 |
| 6 | 알림 채널 | **Mattermost 인커밍 웹훅** | URL은 `.env`의 `MATTERMOST_WEBHOOK_URL` (문서·git 미포함) |
| 7 | 백테스트 데이터 | **2단계**: 무료 프로토(yfinance) → Sharadar 2–3개월 일회성 검증 | 상세 §8 |

---

## 1. 매크로 레짐 판별

### 1.1 6개 축 (각 -2 ~ +2점)

Phase 1의 5개 축 유지, "경기" 축만 복합 지표로 교체.

| 축 | 데이터 소스 | +2 (강세) | 0 (중립) | -2 (약세/위기) |
|---|---|---|---|---|
| VIX + 기간구조 | `^VIX`, `^VIX3M` (yfinance) | VIX < 15 & 콘탱고 | 15 ~ 22 | VIX > 28 또는 백워데이션 |
| S&P 500 추세 | `^GSPC`, 50/200일 SMA | 종가 > 200SMA & 50SMA 상승 | 200SMA ±2% 횡보 | 종가 < 200SMA & 50SMA 하락 |
| 시장 폭 (Breadth) | 구성종목 중 %>200DMA (직접 계산) | > 60% | 45 ~ 60% | < 35% |
| 일드커브 + 정책 | FRED `T10Y3M`, `DFF` | 정상(+) & Fed 동결/인하 | 평탄 | 역전 심화 또는 역전 후 급격 재정상화 |
| 신용 스프레드 | FRED `BAMLH0A0HYM2` | < 350bp & 축소 | 350 ~ 500bp | > 500bp 또는 주간 +75bp |
| **경기 (복합)** | 아래 1.2 | (하위 3신호 평균) | | |

### 1.2 "경기" 축 = 하위 3개 신호 점수의 평균(반올림)

| 하위 신호 | 데이터 | +2 | +1 | 0 | -1 | -2 |
|---|---|---|---|---|---|---|
| WEI (주간경제지수) | FRED `WEI` | > 2.0 | 1.0 ~ 2.0 | 0 ~ 1.0 | -1.0 ~ 0 | < -1.0 |
| 지역연준 제조업 평균 | Empire State / Philly Fed / Dallas / KC / Richmond 일반활동지수 평균 | > +10 | +3 ~ +10 | -3 ~ +3 | -10 ~ -3 | < -10 |
| 실업청구 4주 이동평균 추세 | FRED `IC4WSA`, 3개월 전 대비 변화율 | ≤ -5% | -5% ~ -1% | ±1% | +1% ~ +10% | > +10% |

- 데이터 결측 시 가용한 신호만 평균
- **WEI**: 10개 주간 데이터(소매판매·실업청구·전력사용·철강생산 등)를 합친 실시간 경제 성장률 근사치. 원 개발: 뉴욕 연준. FRED 무료, 주간 갱신, 지연 며칠.

### 1.3 미래 ISM PMI 전환 지점

- **현재**: 위 복합 지표 사용. `MANUAL_ISM_PMI` 환경변수가 설정되면 해당 값을 최우선 사용.
- **전환 조건**: 유료 ISM PMI API(예: ISM 공식, Trading Economics, Nasdaq Data Link) 확보 시.
- **전환 방식**: ISM PMI를 "경기" 축의 4번째 하위 신호로 추가하거나 주 신호로 승격 (WEI는 보조로 강등). `RegimeScoreCalculator`의 config에서 신호 목록·가중치만 수정하면 되도록 설계.
- ISM PMI 점수 기준(전환 시): > 55 → +2 / 52~55 → +1 / 48~52 → 0 / 45~48 → -1 / < 45 → -2

### 1.4 점수화 → 스무딩 → 라벨 → 위기 오버라이드

1. **6축 합산** → `total_score` ∈ [-12, +12]
2. **감시견이 매일 계산** (`RegimeScoreCalculator`는 순수 파이썬, LLM 불필요) → `state/regime_history.json`에 일별 누적
3. **5일 EMA** → `score_smooth` (일간 노이즈 감쇠. Phase 1 초안의 "3거래일 연속 확인" 규칙 폐기, EMA로 대체)
4. **라벨** (raw `total_score` 기준, 리포트·소통 전용):
   - `total_score ≥ +5` → 🐂 **BULL**
   - `-4 ≤ total_score ≤ +4` → ⚖️ **NEUTRAL**
   - `total_score ≤ -5` → 🐻 **BEAR**
5. **CRISIS 오버라이드** (raw 값, 하나라도 참이면 발동):
   - VIX > 35, **또는**
   - HY OAS > 700bp, **또는**
   - S&P 500 종가가 200일 SMA 아래로 10% 초과 이탈
   - → 배분을 2.2 표의 `-12` 행으로 강제 (스코어 무관)
   - **해제**: `score_smooth ≥ -5` **AND** 마지막 트리거 후 5거래일 경과

---

## 2. 점수 → 배분 (슬라이드식 보간)

### 2.1 왜 슬라이드식인가

계단식(이산 3구간)은 경계에서 **절벽 효과**: `total_score`가 +4 → +5로 1점만 움직여도 레시피가 바뀌며 전체 자산의 ~15%를 즉시 매매. 점수가 경계를 오가면 **휩쏘**(반복 역전 매매)로 수수료·세금만 소모. 슬라이드식은 1점 변화 시 배분이 ~2%p만 이동 → 부드럽고 회전율 낮음.

라벨(`BULL/NEUTRAL/BEAR/CRISIS`)은 계속 산출 → 리포트 가독성 + CRISIS 비상 브레이크용.

> **⚠️ regime-screen 감사 수정 (2026-09-02).** `low_confidence`(관측 축 < `min_axes_for_label`)
> 일엔 `score_smooth`·배분에 외삽값(`sum × 6/n`)이 아닌 **관측 축 원합**만 반영 — 얇은 데이터로
> 95% 주식·20% 고위험 스냅 방지. `total_score`(리포트용)는 명세대로 외삽. CRISIS 해제의
> "5거래일"은 `regime_history`(실제 거래일) 로 카운트 (공휴일 정확). `regime_score` 는 오늘
> 이후 날짜의 히스토리 포인트를 EMA 에서 제외 (같은 날 재실행 이중계산 방지). 상세:
> `docs/reviews/regime-screen-codereview.md`.

### 2.2 보간 기준점 테이블

`score_smooth`를 아래 기준점 사이 **피스와이즈 선형 보간**. 카테고리 %는 **주식 슬리브 내부 기준** (합 100).

| score_smooth | 🟢 저위험 | 🟡 중위험 | 🔴 고위험 | 주식 슬리브 | 현금 |
|---|---|---|---|---|---|
| **-12** | 85 | 15 | 0 | 50% | 50% |
| -8 | 78 | 19 | 3 | 60% | 40% |
| -4 | 68 | 26 | 6 | 72% | 28% |
| **0** | 55 | 32 | 13 | 85% | 15% |
| +4 | 48 | 36 | 16 | 90% | 10% |
| +8 | 43 | 39 | 18 | 94% | 6% |
| **+12** | 40 | 40 | 20 | 95% | 5% |

- 기준점 사이는 선형 보간. `RegimeScoreCalculator`(또는 `AllocationTableTool`)가 보간에 사용한 상·하 기준점 2개를 출력에 포함 (설명 가능성 확보).
- **예시**: `score_smooth = +2` → 저 51.5 / 중 34 / 고 14.5 (슬리브 87.5%). 전체 포트 환산: 저 45.1% / 중 29.75% / 고 12.7% / 현금 12.5%.

### 2.3 가드레일 (Phase 1 B-3 + 추가)

- 고위험 카테고리 전체 포트 **절대 상한 20%** (레짐 무관)
- 단일 종목 상한 8%, 단일 섹터 상한 30%, 현금 하한 3%
- **1회 리밸런싱당 카테고리 변동 ≤ 10%p** (데이터 글리치로 인한 점수 급변 방어)
- 카테고리 조정 **쿨다운 10거래일** (CRISIS 예외)

> **구현 노트 (2026-09-02, whole-integration #2)** — 10%p 스로틀(현재→계획)은
> `cash_flow_rebalance` 의 `max_move_usd` 캡이 구조적으로 보장. `check_constraints` 의
> `max_change_per_rebal` 은 `size_positions` 가 그 계획에 충실했나(계획→실현 ≤ 10%p)만 검증
> — 집중 포트 해소 시 구조적 캡으로 실현이 계획보다 더 팔릴 수 있으나 안전 방향이라 허용.
> 절대 가드레일(고위험 20%·단일 8%·섹터 30%·현금 하한)은 `run_pipeline` 이 위반 시 `RuntimeError`.

---

## 3. 리밸런싱 주기

### 3.1 3층 실행 구조

| 층 | 주기 | 실행 커맨드 | 내용 | LLM |
|---|---|---|---|---|
| **일일 감시견** | 매일 06:30 KST | `python -m aegisvest.watchdog` | ① 위기 임계 체크 ② 일일 6축 매크로 점수 계산·EMA 갱신 | ✕ |
| **주간 크루** | 일요일 22:00 KST | `python -m aegisvest.main` | 레짐·스크리닝·리밸런싱 평가 → 매매 리포트 | ○ (풀 크루) |
| **위기 트리거** | 감시견 감지 시 | 주간 크루 즉시 실행 | 쿨다운·주간주기 무시 | ○ |

### 3.2 감시견 스펙 (`watchdog.py`, ~60줄, LLM 미사용)

```
입력: FRED(BAMLH0A0HYM2, WEI, IC4WSA, T10Y3M, 지역연준),
      yfinance(^VIX, ^VIX3M, ^GSPC + 200SMA), 구성종목 breadth

매일:
  1. 6축 매크로 점수 계산 → state/regime_history.json 누적, 5일 EMA 갱신
  2. 위기 조건 체크:
       - VIX > 35
       - HY OAS > 700bp
       - S&P 500 종가 < 200SMA × 0.90
       - VIX 1일 변화 > +50%
  3. 하나라도 참 → state/crisis_flag.json 기록 + 알림(텔레그램/이메일, 선택)
                 + 주간 크루 즉시 트리거
  4. 아니면 로그만 남기고 종료
```

### 3.3 행동 규칙 (주간 크루)

#### ① 현금흐름 리밸런싱 (적금형 최적화 — 핵심)

매도는 한국 거주자 기준 양도세 22% + 수수료를 유발. 신규 입금 현금 매수는 세금 0. 따라서:

1. 목표 비중 계산 (2.2 표)
2. 현재 비중 계산 (포트 평가액 기준)
3. 가용 현금 `C` = 이번 달 입금액 + (현재 현금 − 현금 목표 하한)
4. 카테고리별 부족액 = 목표$ − 현재$
5. **`C`를 부족한 카테고리부터 매수에 배정** (상대 부족률 큰 순), `C` 소진 또는 부족 해소까지
6. `C`를 다 써도 여전히 밴드(**±4%p 절대** 또는 **±25% 상대**) 밖인 카테고리 → **그때만 매도**로 조정
7. 최근 10거래일 내 조정한 카테고리는 6단계 건너뜀 (CRISIS 예외)

→ 적금 납입이 지속되는 동안엔 대부분 매수만으로 리밸런싱 완료. 회전율·세금 급감.

#### ② 종목 드리프트 (개별 주식 레벨)

- 스크린 탈락 또는 목표 비중의 1.5배 초과 → 트림/교체
- 재스크리닝 주기: 저·중위험 **매월 첫 주**, 고위험 **매주** (모멘텀 감쇠 빠름)

### 3.4 백테스트 검증 항목

- 주간 vs 월간 vs 일간: CAGR / 최대낙폭(MDD) / 샤프지수 / 회전율 / 거래비용·세금 후 수익
- 쿨다운 10d vs 20d vs 없음
- 밴드 폭 ±3 / ±4 / ±5 %p
- score EMA 3d / 5d / 10d
- 현금흐름 리밸런싱 유무에 따른 세금·회전율 차이

---

## 4. 실행 환경 (Radxa Rock 5 ITX, ARM64, 32GB, OMV8)

### 4.1 제약: OMV8 + openmediavault-compose

- Docker를 OMV8의 `openmediavault-compose` 플러그인으로 관리
- **컴포즈 파일 1개**만 OMV에 등록 → 그 파일이 이미지 확보 + 스케줄 주입 + 스택 기동을 모두 처리해야 함
- host crontab / 별도 Dockerfile·crontab 파일을 OMV에 얹는 방식 불가

### 4.2 해결: 단일 컴포즈 파일 (git build context + 인라인 configs)

**트릭 2가지**
1. `build.context`에 **git URL** → Docker가 빌드 시점에 repo를 직접 clone (Dockerfile은 repo 안에만 존재)
2. Compose **`configs` 인라인 `content`** → crontab 텍스트를 컴포즈 파일 안에 직접 작성 (별도 crontab 파일 불필요). *요구: Docker Compose ≥ v2.23.1 — OMV8 기본 만족*

**스케줄러**: supercronic (컨테이너 전용 cron, Go 단일 바이너리, ARM64). 이 컨테이너가 곧 상시 프로세스 — PID 1로 유휴 대기(~5MB), 시간 되면 잡 실행. `restart: unless-stopped`로 재부팅 자동 복구.

대안 비교: 평범한 `cron`(env 스크러빙·stdout 미로깅), APScheduler(의존성 트리 상주), Ofelia(Docker 소켓 노출) — 모두 supercronic보다 열위.

### 4.3 `docker-compose.yml` (repo 루트, OMV-compose에 등록하는 유일 파일)

```yaml
services:
  aegisvest:
    build:
      context: "https://github.com/OWNER/US_stocks_AI_CrewBalancr.git#main"
    image: aegisvest:local
    command: supercronic -passthrough-logs /app/crontab
    env_file: .env                 # OMV-compose "Environment" 탭이 생성/관리
    environment:
      TZ: Asia/Seoul
    configs:
      - source: crontab
        target: /app/crontab
    volumes:
      - ${AEGIS_DATA}/state:/app/state
      - ${AEGIS_DATA}/cache:/app/data/cache
      - ${AEGIS_DATA}/outputs:/app/outputs
      - ${AEGIS_DATA}/logs:/app/logs
    restart: unless-stopped
    mem_limit: 2g
    cpus: 1.0

configs:
  crontab:
    content: |
      CRON_TZ=Asia/Seoul
      # 매일 06:30 KST — 감시견 + 일일 매크로 점수
      30 6 * * *  flock -n /tmp/wd.lock   python -m aegisvest.watchdog
      # 일요일 22:00 KST — 주간 풀 크루
      0 22 * * 0  flock -n /tmp/crew.lock python -m aegisvest.main
```

### 4.4 `.env` (OMV-compose "Environment" 탭, git 미커밋)

```bash
AEGIS_DATA=/srv/dev-disk-by-uuid-XXXX/appdata/aegisvest   # OMV 공유폴더 경로
TZ=Asia/Seoul
DEEPSEEK_API_KEY=sk-...
FMP_API_KEY=...
FRED_API_KEY=...
MODE=paper
DRY_RUN=true
```

### 4.5 `Dockerfile` (repo 안, git build가 사용 — OMV는 몰라도 됨)

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends util-linux curl \
    && rm -rf /var/lib/apt/lists/*
ARG SC=v0.2.33
RUN curl -fsSLo /usr/local/bin/supercronic \
    "https://github.com/aptible/supercronic/releases/download/${SC}/supercronic-linux-arm64" \
    && chmod +x /usr/local/bin/supercronic
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev
COPY . .
ENV PATH="/app/.venv/bin:$PATH"
```

`util-linux` = `flock` 제공 (스케줄 잡 중복 실행 방지).

### 4.6 private repo 대응

- git build context는 **public repo에서 무마찰**. 코드에 비밀 없음(키는 전부 `.env`, git-ignored) → **repo public 권고**.
- private 유지 시: GitHub Actions로 ARM64 이미지를 `ghcr.io`에 push, 컴포즈는 `build:` 대신 `image: ghcr.io/OWNER/aegisvest:latest`. OMV에 GHCR 로그인 1회 필요.

### 4.7 수동 실행

```bash
docker compose run --rm aegisvest python -m aegisvest.backtest --from 2005
```

로그: `docker logs -f <스택명>-aegisvest-1`. 리소스: 1 CPU / 2GB 충분, 평소 유휴. 스택 전부 ARM64 호환 (pandas/numpy ARM 휠, DeepSeek/FRED는 HTTP). GPU 불필요.

---

## 5. Phase 3 이월 항목 (결정 4-a에서 파생)

| 항목 | 잠정 방향 |
|---|---|
| **모의투자 하네스** | `MODE=paper` → `PaperBroker`가 매매 리스트를 가상 원장(`state/paper_portfolio.json`)에 반영. 체결가 = 당일 종가(또는 익일 시가), 소수점 주식 허용, 나무증권 수수료(~0.25%) + 환전 스프레드(~1%) 모사. 일일 종가 평가 → equity curve 기록 |
| **벤치마크 병행 추적** | 동일 현금흐름으로 (a) SPY 100% 매수보유, (b) SPY 60 / AGG 40 시뮬레이션 → 전략과 비교 |
| **성공 판정 기준** | §6에서 확정 (2단 게이트) |
| **소액 구간 포트폴리오 구성** | 모의투자는 소수점 매매로 30종목 전략 그대로 검증. 실제 소액 전환 시 바구니별 상위 3~5종목 집중 포트로 시작, 자금 증가 시 확대. ETF 프록시(저=SCHD, 중=QQQ, 고=테마 ETF)는 대안으로만 |
| **한국 거주자 세제 (나무증권 확인 후 확정)** | 잠정: 해외주식 양도차익 연 250만원 기본공제 후 **22% 단일세율**, **보유기간 무관**(미국식 장·단기 구분 없음). 같은 해 손익 통산, 이월 불가. 배당은 미국 원천징수 15%. → 세금 최적화 포인트는 **연말 손실 하베스팅** + **250만원 공제 활용 위한 이익 실현 연도 분산** (Phase 1의 "장기 보유 세제 혜택" 로직은 불필요) |
| **자동 집행 (Phase 4+)** | 신뢰 축적 후 브로커 API(나무증권 OpenAPI 등) 연동 검토. 안전장치 코드 대폭 추가 필요 |

---

## 6. 성공 판정 기준 — "실제 돈을 넣을지" 판단

### 6.1 목적

10만원 모의투자 후 "적금형 전환" 여부를 **사후 합리화 없이** 결정하기 위해 기준을 사전에 못 박음.

### 6.2 성과 지표 & 벤치마크

| 지표 | 뜻 |
|---|---|
| CAGR | 연평균 복리 수익률 |
| MDD (최대낙폭) | 고점 대비 최대 하락폭 — 방어력 척도 |
| 변동성 | 수익률 연율 표준편차 |
| 샤프 지수 | (수익률 − 안전이자) ÷ 변동성 = 위험 1단위당 수익 |
| 소르티노 지수 | 샤프인데 하락 변동성만 벌점 (방어 전략 평가에 공정) |
| 초과수익 | 벤치마크 대비 더/덜 번 수익 |

**벤치마크 3종 병행 추적** (동일 현금흐름 시뮬): `SPY` (주 기준), `60/40` (SPY 60 + AGG 40), `ACWI` (전세계).

> **⚠️ money-path 감사 수정 (2026-09-02).** 지표는 **시간가중수익률(TWR)** — 적금 납입을
> 수익으로 계상하지 않으려면 `Contribution.date == NavPoint.date` 여야 한다. `main.run()` 이
> 둘 다 직전 미국장 마감일(`latest_close_date`)로 스탬프. 벤치마크는 가격 결측 leg 발생 시
> 해당 벤치 전체 투입액을 `pending_usd` 로 이월(부분매수로 영구 저평가 방지). 상세:
> `docs/reviews/money-path-codereview.md`.

### 6.3 전략 성격 전제

방어형 전략 — 장기 강세장에서는 SPY보다 총수익이 **뒤처지는 게 정상**. 목표는 "시장 초과수익"이 아니라 **"수익 대부분을 훨씬 적은 낙폭으로"**. 합격선도 그 기준.

### 6.4 Gate A — 백테스트 (통계적 근거, 2000~현재)

전부 통과:

| 항목 | 합격선 |
|---|---|
| 수익 포착 | 전체 사이클 총수익 **≥ SPY의 80%** |
| **방어력 (핵심)** | MDD **≤ SPY MDD × 0.65** |
| 위험 효율 | 샤프 **≥ SPY × 1.2** AND 소르티노 **≥ SPY × 1.2** |
| 스트레스 구간 | 2000–02 / 2008 / 2020 / 2022 각 하락장에서 SPY보다 손실 작음 |
| 비용 반영 | 수수료·세금 반영 후에도 위 전부 유지 |

### 6.5 Gate B — 모의투자 (운영·현실 검증)

최소 12개월 **AND 조정장(-10%) 1회 이상 경험**. 미충족 시 관찰 연장 또는 Gate A 비중 상향.

| 항목 | 합격선 |
|---|---|
| 운영 안정성 | 12개월 중단 없이 매주 리포트 생성 |
| 백테스트 정합성 | 실현 수익률이 백테스트 예측 범위(±1σ) 안 |
| 방어 재현 | 동기간 MDD ≤ SPY MDD |
| 행동 건전성 | 회전율이 백테스트 예상 수준, 폭주·휩쏘 없음 |
| 레짐 판정 | 사후적으로 합리적 (조정장에서 방어 전환) |

### 6.6 판정

- **합격 = A AND B** → 적금형 실제 자금 투입 시작
- Gate A 실패 → 전략 자체 문제: 파라미터 재보정 / 고위험 바구니 제거 / 프로젝트 재고
- Gate B만 실패 → 구현·운영 버그: 코드 수정 후 재관찰

---

## 7. 알림 (Mattermost 인커밍 웹훅)

### 7.1 방식

- **Mattermost 인커밍 웹훅** — 자체 호스팅(`chat.taeuk.site`), 인프라 추가 0
- 웹훅 URL은 **`.env`의 `MATTERMOST_WEBHOOK_URL`** 에만 저장. 이 문서·`docker-compose.yml`·git에 **평문 포함 금지** (URL 보유자는 누구나 채널에 게시 가능)
- 구현: `requests.post(url, json=payload)` — 전용 라이브러리 불필요
- `MATTERMOST_WEBHOOK_URL` 미설정 시 → 알림 스킵, `outputs/`에 리포트 파일만 (graceful degradation)

### 7.2 메시지 2종

| 종류 | 발생 | 페이로드 |
|---|---|---|
| **위기 알림** | 감시견 트리거 | `{"username": "AegisVest 🆘", "text": "**CRISIS TRIGGERED**\nVIX 38.2 (>35)\n풀 크루 실행 중"}` |
| **주간 리포트** | 주간 크루 완료 | 요약 (레짐/스코어/배분/매매 건수) + `attachments` 필드. 전체 리포트는 `outputs/`에 저장 |

### 7.3 파일 첨부

인커밍 웹훅은 파일 업로드 미지원. 전체 리포트를 채팅에 올리려면 Mattermost API v4(`/api/v4/files` + 봇 토큰) 필요 → **당장은 불필요**. 요약만 웹훅, 전체는 `outputs/` 볼륨.

---

## 8. 백테스트 데이터 & 엔진

### 8.1 생존 편향 (Survivorship Bias)

오늘의 지수 명단으로 과거를 백테스트하면 살아남은 회사만 테스트 → 결과 과대평가. 엔론·리먼·베어스턴스·워싱턴뮤추얼·GM(구)·코닥 등 당시 지수 편입 후 소멸한 종목이 빠짐.

**제대로 하려면**: 시점별 지수 구성종목(폐지 종목 포함), 시점별 재무(공시일 기준), 배당·분할 반영 총수익.

### 8.2 벤더 선택 — 2단계

| 단계 | 데이터 | 비용 | 용도 |
|---|---|---|---|
| **1. 프로토타입** (Phase 3) | yfinance + FRED, 현재 구성종목 | 무료 | 배관 구축 + 대략적 감. 생존 편향 인정 |
| **2. 최종 검증** (실제 자금 투입 전) | **Sharadar** (Nasdaq Data Link): SF1 재무 + SEP 가격 + ACTIONS + TICKERS | ~$50–100/월 × **2–3개월 후 해지** (일회성 ~$150) | 생존편향 없는 2000~현재 백테스트 1회 |
| **3. 운영 (라이브)** | FMP + FRED + yfinance (Phase 1 명세) | Phase 1 수준 | 현재 종목 앞으로 스크리닝만 → Sharadar 불필요 |

### 8.3 엔진: 별도 구축 안 함

- 주기가 주간이므로 **주간 루프 + pandas**로 충분. 이벤트 드리븐 엔진(`backtrader` 등) 불필요.
- **백테스트는 결정론적 파이썬 툴만 호출** (`ScreenerTool`, `ScoringCalculator`, `AllocationTableTool`, `RegimeScoreCalculator`)에 과거 데이터 주입. **LLM 에이전트는 백테스트 루프에 미포함** (느림·비용).
- → 백테스트는 **전략**(필터·스코어·배분)을 검증. LLM 오케스트레이션은 별도 통합 테스트(Phase 1 TEST_GUIDE 시나리오 5).
- 라이브 프로덕션 로직 그대로 재사용 → 백테스트-라이브 괴리 최소화.
- 시점 규율: 구성종목 as-of-date, 재무 `공시일 ≤ T`, 기술지표 룩어헤드 금지. 매크로는 as-published 허용(엄격판은 FRED ALFRED vintage).

---

## 9. Phase 1 `.env.example` 갱신 사항

Phase 2에서 추가되는 환경변수 (Phase 1 D-7에 병합):

```bash
# --- 실행 모드 ---
MODE=paper                     # paper | live
AEGIS_DATA=/srv/.../appdata/aegisvest   # OMV 공유폴더 (bind mount 루트)
TZ=Asia/Seoul

# --- 알림 ---
MATTERMOST_WEBHOOK_URL=        # 미설정 시 알림 스킵, outputs/ 파일만. git 미커밋

# --- 매크로 복합 경기축 (FRED 시리즈, 무료) ---
FRED_SERIES_WEI=WEI
FRED_SERIES_CLAIMS=IC4WSA
FRED_SERIES_HY_OAS=BAMLH0A0HYM2
FRED_SERIES_YC=T10Y3M

# --- 백테스트 최종 검증 (일회성, 평소 비움) ---
NASDAQ_DATA_LINK_API_KEY=      # Sharadar SF1/SEP/ACTIONS/TICKERS, 2~3개월만
```

## 10. 다음: Phase 3

- CrewAI 조직 구조 (Phase 1 과제 C) MVP 4-에이전트 최종 확정
- 모의투자 하네스 (`PaperBroker`, equity curve, 벤치마크 병행)
- 소액 구간 포트폴리오 구성 (소수점 30종목 vs 집중 3–5종목)
- 한국 거주자 세제 확정 (나무증권 확인 후)
