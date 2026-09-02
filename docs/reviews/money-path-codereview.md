# Pre-Phase-4 감사 — money path 독립 `/code-review` (high)

`broker/` · `tools/portfolio_math.py` · `pipeline.py` · `main.py` · `state.py` 를 빌트인
`/code-review` high 로 검토 (Phase 3a/3b 는 당시 자가 review-stage 만 거침). 7건 전부 수정.

## 수정

| # | 위치 | 문제 | 수정 |
|---|---|---|---|
| 1 | `broker/metrics.py` + `main.py` | **TWR 기여 보정이 항상 무효** — `Contribution.date`(=run_id, 일요일 KST)와 `NavPoint.date`(=거래일 마감, 금요일)가 달라 `cf_by_date.get(cur.date)` 가 절대 매칭 안 됨. 매 월 납입이 투자수익으로 계상 → CAGR/Sharpe/총수익/섀도델타 전부 부풀려짐 (Gate B 핵심 수치) | `main.run()` 이 NAV·기여·벤치를 전부 `mkt_date`(직전 미국장 마감일) 로 스탬프. `_daily_returns` 는 기여를 "그 날짜 이후 첫 NavPoint"(없으면 마지막)에 귀속 — 규약 어긋나도 유실 안 됨 |
| 2 | `main.py` | `_persist_regime` 이 org 파이프라인 직후 `history` 를 **in-place append** → 이어서 도는 결정론(det) 파이프라인은 오늘 포인트가 이미 든 history 로 실행 → `_ema([*prior, total])` 가 오늘 점수 2번 계산 → 다른 `score_smooth` → 다른 배분·주문. **섀도 A/B 비교(및 diary evaluate 섀도델타 채점)가 오염** | `_persist_regime` 을 org·det 파이프라인 **둘 다 실행한 뒤로** 이동 |
| 3 | `state.py` | `save_model`/`save_list` 가 truncate-then-write, `load_*` 는 손상 시 조용히 None/[] → 쓰다 죽으면 **`shadow.json`(포트폴리오 이력 전체) 유실** | `_atomic_write` — `<name>.<pid>.tmp` 에 쓰고 `os.replace` (POSIX atomic) |
| 4 | `broker/benchmarks.py` | `contribute` 가 가격 결측 leg 를 조용히 드롭 — 60/40 벤치가 AGG 가격 없는 날엔 SPY 만 매수, 0.4 는 증발 (cash 필드 없음) → 벤치 영구 저평가 → Gate B 가 전략에 유리하게 편향 | `BenchmarkState.pending_usd` 추가. 한 티커라도 결측이면 그 벤치 전체 투입액을 이월, 다음 납입에서 재시도. `mark_to_market` NAV 에 pending 포함 (유령 급락 방지) |
| 5 | `main.py` | `WeeklyRunResult.n_orders = len(pr.orders)` 인데 조직 틸트 실행 시엔 `crew.org_orders` 가 체결됨 → 보고 불일치 | `n_orders = len(org_orders)` |
| 6 | `main.py:105` | `_execute_and_mark` docstring 이 실행문 뒤에 위치 → docstring 아님 (no-op) | 함수 첫 줄로 이동 |
| 7 | `main.py` | `_bench_prices()` · `latest_close_date()` 를 run 당 2회 호출 (캐시되나 중복) | 각 1회 계산 후 재사용 (`_maybe_contribute` 추출) |

## Round 2 — 0건

### 검토했으나 finding 아님 / 수용
- `_daily_returns` 의 "첫 NavPoint 이후 귀속" — 기여일이 히스토리 전체보다 앞서면 `history[0]`
  (기준점, `pairwise` 의 `cur` 아님)에 귀속되어 수익 계상 안 됨 = 최초 납입이 시작자본이 되는
  올바른 동작. `mkt_date` 정상 시엔 항상 정확 일치.
- `mkt_date` 가 None(네트워크 실패)일 때만 기여 스탬프(`run_id`)와 mark(`pr.as_of`)가 어긋날
  수 있으나, 방어적 귀속으로 총수익은 정직 유지. 드묾.
- `os.replace` 는 같은 디렉토리(같은 fs)라 항상 atomic. 크로스 fs 아님.

## 검증
- ruff / ruff format / mypy(50) / pytest **251 passed, 2 deselected**
- 신규 테스트 5: TWR 날짜 어긋남·벤치 결측 leg 이월·pending NAV·state atomic write·섀도 파이프라인 동일 입력
- 커밋: `fix(money-path): 독립 code-review 7건 (TWR 기여일·섀도 레짐 이중계산·state atomic·벤치 leg 유실)`

## 다음 감사 패스 (미실행)
- pass 2: `agents/guardrails.py` · `agents/pm.py` (하드 안전망)
- pass 3: `tools/regime.py` · `screener.py` · `scoring.py` · `allocation.py` (시나리오 2·4)
