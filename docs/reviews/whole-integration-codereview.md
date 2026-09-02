# 전체 통합 검토 (2026-09-02)

섹터별 감사(8패스) 이후, **섹터 간 연결부 중심** 전체 검토. 데이터 플로우 정합성 ·
논리 모순 · 로직 버그 · 의도 불일치. 커밋 상태 기준 (diff 아님).

## 수정 (9건 — #2 는 D옵션으로 후속 처리)

| # | 심각도 | 위치 | 문제 | 수정 |
|---|---|---|---|---|
| 1 | **높음** | `watchdog.py:38` `main.py:39` ↔ `diary/evaluate.py:203` | `_MAX_HISTORY=40`(5일 EMA 용) 이 `regime_history.json` 를 ≈8주로 절삭. `_score_regime_call` 은 12주(≈60거래일) 창으로 채점 → 모든 regime_call 채점창의 ~33%(앞 4주) 소실, 최근 레짐 쪽으로 편향 | `_MAX_HISTORY=70` (12주 + 여유). EMA 는 tail 만 봐 무해, 파일 +2KB. `test_history_capped` 를 정확절삭 검증으로 강화 |
| 3 | 중 | `diary/logger.py:128` | `save_entries` 만 비원자적 `write_text` — 감사가 `state`/`_io`/`rag._log_recall` 에 세운 atomic 규율에서 유일 예외. reviewer 가 반성 건별 rewrite → 크래시 시 판단 일기 전체 truncate | `_io._write_atomic` (temp + os.replace) 재사용 |
| 4 | 중 | `state.py:34-56` | 존재하는 `shadow.json`/`benchmarks.json` 파싱 실패 → 조용히 None → 빈 상태 → 다음 save 가 덮어써 수개월 이력 복구 불능. "부재"와 "손상"이 동일 처리 | `_quarantine` — `.corrupt` 로 rename 보존 + ERROR 로그. 부재만 신규 취급. `test_corrupt_*` 강화 |
| 5 | 낮음 | `crew.py:509` ↔ `organization.py:317` | `_diary_snapshot` 동명 2개, 필드셋 상이 (crew 쪽에 `total_score` 등 추가). 현재는 signal 태그 동일하나, 그 필드 참조하는 rule 이 생기면 로그시점 vs 회상시점 태그 어긋남 | crew 의 리치 버전을 canonical, organization 이 import |
| 6 | 낮음 | `pipeline.py` `main.py` | `pending_contribution_usd` — `run_pipeline`/`run_organization` 이 노출하나 main 은 항상 0 (기여를 `cash_usd` 에 선반영). `_demo`·11 test 는 씀 → 계약 모호 | **버그 아님으로 판명** (정상 운영은 현금≈하한이라 두 계약 동일 결과). `run_pipeline` 에 계약 설명 주석 |
| 7 | 낮음 | `schemas.py` | stale docstring 3건: `CrisisFlag` "main 이 읽어" (실제론 watchdog 이 `main.run()` 직접 호출) · `PaperPortfolio` "paper_portfolio.json" (ponytail 제거됨) · `WeeklyRunResult.dry_run` 설명 | 갱신 |
| 8 | 낮음 | `pipeline.py:258` | 신규 타깃 종목 가격조회 실패 시 sizing 은 예산 배정, `build_orders` 는 조용히 드롭 → 그 주 예산 유휴현금. 문서화 안 됨 | `notes.append("타깃 가격 결측 ...")` |
| 9 | 낮음 | `diary/logger.py:103` | 같은 날 crisis 재실행 → `entry_id`(run_id+agent+claim_type) 충돌 → `entries.jsonl` dupe 축적 (RAG 는 id dedup, evaluate 는 base-rate 이중계상) | `load_entries` 가 id 로 dedup (마지막 유지, 위치 보존). `test_load_entries_dedups_by_id_keeping_last` |

## #2 후속 — D옵션 (근본 수정, 2026-09-02)

**내용** (`b051444` + 후속 `/code-review` 반영): `run_pipeline` 이 반환 전
**절대 가드레일**(고위험캡·단일·섹터·현금하한·비중합) 위반이면 `RuntimeError` (ToolError 3종과
동일). `max_change_per_rebal` 은 raise 대상 아님 — rate 정책이라 구조적 초과 가능. 불변식:
반환된 draft 는 절대 가드레일을 항상 만족.

D 를 적용하니 **결정론 파이프라인이 실제로 위반 draft 를 내는 2가지**가 드러남 (B/C 였다면
가려졌을 것):

1. **fp 경계 과민** — `check_constraints` 캡 검사가 `+ 1e-9` 인데 `size_positions` 는 weight 를
   여러 단계 `round(_, 6)` 누적(~1e-5 잔차) → 섹터가 캡 정확히 차면 오탐 FAIL. **`_EPS = 5e-5`**.
2. **`max_change_per_rebal` 구조적 초과** — 집중 포트 해소·screen 결측(category 0)·스필·티어
   강등 시 실제 이동 > 10%p. 스로틀 자체(현재→계획 ≤ 10%p)는 `rebalance.max_move_usd` 캡이
   구조적 보장 → `check_constraints` 는 계속 `prior = current_cat_usd/nav` (실제 이동)를 재나,
   위반은 **raise 가 아니라 note + WARNING**. screen 결측 같은 소프트 조건이 주간 실행을
   크래시시키면 안 됨. 임계는 `+ 1.0`%p 버퍼 (fp·경계 노이즈 배제).

**후속 `/code-review` (2026-09-02)**: 첫 D 커밋이 (a) 모든 FAIL 에 raise (max_change 포함 →
screen 결측이 크래시), (b) `prior = post_action_weights` 로 실제-이동 검증 상실, (c) `_EPS`
코멘트 오류·과대(1e-4) 를 지적 → 위처럼 재수정. `test_absolute_guardrail_fail_raises` +
`test_max_change_fail_is_note_not_raise` + `test_screen_outage_zeroes_held_category_does_not_crash`.
runtime-codereview #4 는 이걸로 개정 (raise 는 절대 가드레일만).

## 검토했으나 정상 (연결부 정합 확인)

- **writer↔reader decision dict 계약** — 6종 claim_type (`_dc_*` 빌더 → `evaluate._score_*`) 전부 키/타입 일치
- **기여 현금흐름** — `_maybe_contribute` → cash 선반영 → 파이프라인 배치 → 체결. 단일 경로, 이중계상 없음. `nav` 도 pending=0 이라 정확
- **shadow NAV 타임라인** — org/det NavPoint 가 `_execute_and_mark` 에서 동일 `mark_date` 스탬프 → `_score_shadow_delta` 의 org_s/det_s 시점 일치
- **`use_org`/`held` 재계산** — organization 과 main 이 각각 계산하나 동일 규칙, `held` 시 org_orders 무시로 무해
- **recall 주입** — `_RECALL_TASKS` = ①②③⑤⑥⑦ (phase-4 §6), guardrail hedge_only 로 회상 수치 통과
- **crisis latch** — watchdog·main 이 순차(cron) 실행이라 `crisis_state.json` 경합 없음
- **benchmark pending_usd** — 가격 결측 leg 이월, `mark_to_market` 부분가격 스킵

## 검증
ruff / format / mypy(50) / pytest **286 passed, 2 deselected**.
커밋: `fix(integration): 전체 통합 검토 8건` + `fix(pipeline): #2 D옵션 raise` +
`fix(pipeline): D옵션 /code-review 반영 — raise 를 절대 가드레일로 한정`
