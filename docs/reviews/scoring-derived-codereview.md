# Pre-Phase-4 감사 pass 5b — 스코어링·파생지표 독립 `/code-review` (high)

`tools/scoring.py` · `_derived.py` · `_screen.py` · `breadth.py` · `universe.py` · `fx.py` ·
`config.py` · `rules.py`. 8건 전부 수정.

## 수정

| # | 위치 | 문제 | 수정 |
|---|---|---|---|
| 1 | `breadth.py:40` | `pct_above_200dma_4w_change` 가 `above_4w` 에 같은 `evaluated` 분모 사용 — 200~219봉 종목은 `sma_prev(200,back=20)` 불가라 4w 분자엔 못 드는데 분모엔 들어감 → 폭 모멘텀 상방 편향 → 레짐 risk-on 왜곡 | `evaluated_4w` 별도 분모 (4주전 SMA 가능 종목만) |
| 2 | `_derived.py:136` | `roic` 가 `long_term_debt` 결측 시 0 으로 대체 → 레버리지 종목 ROIC 부풀림 → `roic > wacc` 하드필터·LOW-B 서브티어 오통과 (다른 함수는 전부 None 게이트) | `total_liabilities - current_liabilities` 로 장기부채 근사, 정보 자체 없으면 None |
| 3 | `scoring.py:94` | 비숫자 metric 값 / metrics·directions 길이 불일치 시 `float()`·`zip(strict=True)` 가 ValueError raise → Layer-0 툴 no-raise 규칙 위반 (CLAUDE.md 규칙 2) | `_num()` 가드 (비숫자 → 중립) + 계산부 `_score_rows` try/except → ToolError |
| 4 | `config.py:27` | `_bool_env` 가 존재하나 빈 값(`DRY_RUN=`)을 False 로 → dry-run 안전 플래그가 조용히 꺼짐 | 빈 문자열 → 기본값 유지. (참고: `dry_run` 은 현재 미소비 — `mode` 가 실제 스위치) |
| 5 | `_derived.py:69` | `piotroski_f` 가 일부 체크 결측 시 부분 점수(최대 6~8) 반환 → 데이터 완전성만으로 `>= 6` 필터 탈락, 재무제표 풍부한 종목 편애 | 결측분 9점 스케일 정규화 (`< 6 resolved` 는 여전히 None) |
| 6 | `scoring.py:22` | `_add_derived` 가 음수 `pe_ttm` 으로 `pe_vs_5y_median` 계산 → direction -1(valuation) 에서 "가장 싼" 값으로 랭크 → 적자 기업이 밸류에이션 최고점 | `pe > 0` 가드 → 음수 PE 는 None (중립 0.5) |
| 7 | `universe.py:33` | `_from_fmp` 가 `BRK.B` (FMP 점 표기) 를 yfinance `BRK-B` 로 정규화 안 함 → FMP 키 설정 시 클래스주가 전 다운스트림 조회 실패 → 조용히 errored | `.replace(".", "-")` |
| 8 | `_derived.py:108` | `dividend_streak_years` 가 연간총액만 비교, 연도 연속성 미확인 → 데이터 갭(2019 결측)이 2018→2020 을 연속 증배로 오인, 지급시기 이동은 오탐 리셋 | `cur[0] == prev[0] + 1` 연속성 체크 (갭 → 리셋). 지급시기 왜곡은 per-payment 데이터 필요 (미지원, 주석) |

## Round 2 — 0건

- `roic` LTD 근사: 무차입 기업은 `total_liab ≈ current_liab` → ≈0 → 정상. 레버리지+미파싱은 근사 포착.
- `piotroski_f` 정규화는 count → ratio×9 로 의미가 약간 바뀌나, sparse-data 편향 제거가 우선.
- `_bool_env` 는 제네릭 헬퍼 — 현재 `DRY_RUN` 만 쓰지만 향후 bool env 전반에 안전.

## 검증
- ruff / ruff format / mypy(50) / pytest **274 passed, 2 deselected**
- 신규 테스트 6: roic LTD 근사·piotroski 정규화·배당갭 리셋·음수PE 중립·비숫자 no-raise·bool_env 빈값
- 커밋: `fix(scoring-derived): 독립 code-review 8건 (폭 4w 편향·roic 결측·piotroski 부분점수·음수PE·배당갭)`

## 감사 완료 — 6 패스
money-path / guardrails-pm / regime-screen / runtime / data-tools / scoring-derived.
전 `aegisvest/` 커버. 4-post-review(Phase 4) 포함 총 **7 패스, ~46 findings, ~43 수정**.
