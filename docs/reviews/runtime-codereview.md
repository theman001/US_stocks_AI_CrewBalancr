# Pre-Phase-4 감사 pass 4 — 런타임 오케스트레이션 독립 `/code-review` (high)

`watchdog.py` · `report.py` · `notify.py` · `tools/rebalance.py` · `tools/constraints.py` · `state.py`.
6건 전부 수정.

## 수정

| # | 위치 | 문제 | 수정 |
|---|---|---|---|
| 1 | `report.py:199` | 벤치마크 `performance_stats` 를 `contributions` 없이 호출 → 월 납입이 벤치 수익으로 계상, 벤치 총수익/MDD 가 기여 보정된 전략 TWR 대비 크게 부풀려짐 → Gate B 비교 무의미 | `performance_stats(hist, pf.contributions)` — 벤치는 동일 현금흐름이므로 org 포트의 기여 스트림 사용 |
| 2 | `state.py:27,41` (+`rules.py`·`universe.py`·`_io.py`) | `read_text()`/`write_text()` 인코딩 미지정 — `_atomic_write` 는 UTF-8 강제인데. 컨테이너의 C 로케일에서 한글(crisis_reason 등) 읽으면 `UnicodeDecodeError`(ValueError) → `load_model` None 반환 → **shadow.json/crisis_flag 등 상태 유실·CRISIS 알림 매일 반복** | 모든 read/write 에 `encoding="utf-8"` 명시 (5개 파일) |
| 3 | `watchdog.py:91` | `_mark_nav` 의 "이미 마킹했나" 가드가 `shadow.organization.history` 만 봄 — 부트스트랩(org 비고 det 라이브) 시 항상 통과 → 같은 거래일 재실행·주말에 det NavPoint 를 (stale/부분) 가격으로 덮어씀 | `max(p.history[-1].date for p in pfs if p.history)` — 실제 마킹된 포트 기준 |
| 4 | `constraints.py:68` | `max_change_per_rebal`(카테고리 10%p/회, CLAUDE.md 절대 규칙 3) 를 `if draft.prior_category_weights:` 로 감쌌는데 **결정론 `run_pipeline` 은 이 필드를 안 채움** → 하드 게이트가 메인 경로에서 실제로 안 돎 | `run_pipeline` 이 `current_cat_usd / nav` 로 `prior_category_weights` 채움. 램프업이 10%p 지키는지 실제 검증 |
| 5 | `watchdog.py:94` | USD/KRW 조회 실패 시 하드코딩 1400 → nav_krw 시계열에 3~5% 인위적 점프 | `_fx_or_carry` — 마지막 NavPoint 의 암시 환율(nav_krw/nav_usd) 이월, 이력 없을 때만 1400 |
| 6 | `watchdog.py:97` | 가격 조회 루프가 `[*held, *BENCH_TICKERS]` — 보유 티커가 벤치(SPY/AGG/ACWI)면 중복 조회, 0주 포지션도 조회 | `sorted(held \| set(BENCH_TICKERS))`, `held` 는 `shares > 0` 만 |

## Round 2 — 0건

- `broker/shadow.delta_report` 는 이미 `.contributions` 전달 (문제 없음).
- `state._atomic_write` (money-path 패스) 는 이미 UTF-8 — 이번엔 read 쪽 + config/cache 로더.
- `prior_category_weights` 추가로 결정론 FAIL 이 나도 실행은 안 막음 (기존대로 리포트에만
  노출) — 램프업이 정상이면 애초에 안 남. 실행 차단은 별도 설계 결정.
  **개정 (2026-09-02, whole-integration #2 D옵션)**: `prior = current_cat_usd/nav` →
  `post_action_weights`(스로틀 계획), `run_pipeline` 이 FAIL 시 raise. reviews/whole-integration.

## 검증
- ruff / ruff format / mypy(50) / pytest **263 passed, 2 deselected**
- 신규 테스트 2: pipeline prior_cw 채움·10%p 준수 / watchdog mark_nav guard·FX 이월
- 커밋: `fix(runtime): 독립 code-review 6건 (벤치 기여보정·인코딩·mark_nav guard·max_change 게이트)`
