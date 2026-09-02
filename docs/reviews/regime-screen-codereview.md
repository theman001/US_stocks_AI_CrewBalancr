# Pre-Phase-4 감사 pass 3 — regime/screen/score 독립 `/code-review` (high)

`tools/regime.py` · `screener.py` · `scoring.py` · `allocation.py` (+ config, pipeline 소비부).
시나리오 2·4 (필수) 대상. 6건 중 6건 처리.

## 수정

| # | 위치 | 문제 | 수정 |
|---|---|---|---|
| 1 | `regime.py:219` | `low_confidence` 는 **라벨만** NEUTRAL 강등, `score_smooth` 는 여전히 외삽(±12). `pipeline` 이 이걸 `allocation_targets` 로 그대로 넘겨 3축만으로 95% 주식·20% 고위험 스냅 가능 (콜드 스타트) | `low_confidence` 일엔 EMA 입력을 외삽값 대신 **관측 축 원합** (`sum(present)`). 리포트용 `total_score` 는 명세대로 외삽값 유지 |
| 2 | `screener.py:52` | HIGH RS 컷: RS 데이터 있는 종목이 하나라도 있으면 RS 결측 종목은 탈락, **아무도 없으면 전부 통과** — SPX 조회가 티커별로 흔들리면 결과가 데이터 운에 좌우 | RS 커버리지 < 50%(통과 후보 대비)면 RS 컷 **전체 스킵** + 경고 로그. 일관성 확보 |
| 3 | `regime.py:223` | `_ema([*prior_scores, total])` 가 오늘 점수를 무조건 append → 같은 날 재실행(감시견 위기 재점검·수동) 시 오늘 이중계산, EMA ~1.55x 왜곡 | `prior_scores` 에서 `h.date >= macro.as_of` 제외 (오늘 이후 포인트 배제) |
| 4 | `regime.py:32` | CRISIS 해제의 "5거래일" 을 `np.busday_count` 로 셈 → 미국장 공휴일 무시 → 창 안에 공휴일 있으면 1세션 일찍 해제 | `_elapsed_trading_days` — `regime_history`(실제 거래일 기록)가 조밀하면 그걸로 카운트, 부족하면 busday 폴백 |
| 5 | `regime.py:51` | 백워데이션 `vix > vix3m` 인데 `config/regime_rules.yaml` 명세는 `vix >= vix3m` | 명세대로 `>=` |
| 6 | `allocation.py:61` | 고위험 절대캡 초과분을 `low` 로 스필 — 현 앵커로는 도달 불가(dead) + 도달 시 risk-on 레짐에서 방어자산으로 스필은 `sizing.underfill_spill_to: mid` 와 모순 | 스필 대상 `mid`, "현 앵커 미도달" 주석 |

## Round 2 — 0건

- `_elapsed_trading_days` 는 `hist_count >= busday - 3` 일 때만 정확값 사용 (히스토리 truncate·
  감시견 미가동 시 undercount 방지). `test_crisis_latch_and_exit`(sparse history) 폴백 확인.
- 백워데이션 `>=` 로 "저VIX·평탄 term structure = -2" 가 되나 명세가 그럼. 정확 동률은 실무상 없음.
- `low_confidence` EMA 입력 = `sum(present)` = 외삽 전 원합 — n=3, 전축 +2 면 6 (외삽 12 대신).

## 검증
- ruff / ruff format / mypy(50) / pytest **261 passed, 2 deselected**
- 신규 테스트 4: low_conf EMA 원합·같은날 무이중계산·공휴일 반영 해제·RS 저커버리지 스킵
- 커밋: `fix(regime-screen): 독립 code-review 6건 (low_conf 외삽·RS 데이터운·EMA 이중계산·공휴일)`

## 감사 완료
money-path / guardrails-pm / regime-screen 3 패스 완료. 나머지 3a/3b 모듈(watchdog·report·
notify·data tools·rebalance·constraints·universe)은 상대적으로 위험 낮음 — 필요 시 추가.
