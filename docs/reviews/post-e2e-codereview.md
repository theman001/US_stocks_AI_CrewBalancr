# 이전 검토 이후 추가분 독립 `/code-review` (2026-09-02)

7패스 감사(`d09ab03`) 이후 커밋된 코드. 스코프 `git diff d09ab03..HEAD`:

- `ec9aacf` 배포 config + DRY_RUN 배선 + 골든/데스크로스 신호
- `7ae6087` ponytail 정리 (삭제 위주)
- `305f316` E2E 통합 테스트
- `3570122` watchdog dry_run · recall_log 바운드 · reviews 인덱스
- `cc7fdcc` 배당 rate 정규화

코드 15파일 (+680/−289). ponytail 삭제분은 참조 0 확인 (`requests_cache`/`crewai_tools`/
`reasoner`/`llm_temperature`/`max_high_risk_exposure`/`FRED_SERIES_*` grep clean).

## 수정 (4건)

| # | 심각도 | 파일 | 문제 | 수정 |
|---|---|---|---|---|
| 1 | 중 | `tests/test_e2e.py` | Phase 2 가 `ev.run(today="2027-02-01")` 하드코딩인데 일기 `evaluate_after` 는 mock 안 된 `dt.date.today()` 로 계산 → 벽시계가 ~2026-11-09 지나면 `not_due` 로 스푸리어스 실패. 시드 NavPoint("2026-11-20")·regime_history 도 run_id≈9월 가정 | 시드·채점일을 `res1.run_id` 기준 상대날짜로. `_frame` 도 run_d 인자. `today=max(evaluate_after)`. 시간 비의존 |
| 2 | 중 | `docker-compose.yml` | Dockerfile 이 bge-m3(~2.3GB) 를 `/app/hf-cache` 에 베이크하는데 compose 가 빈 `./data/hf-cache` 를 **bind mount** 로 덮음 → 런타임에 베이크본 안 보임 → 첫 `up` 에서 재다운로드. bind mount 는 이미지 내용을 상속 안 함 (명명 볼륨만) | `hf-cache` 명명 볼륨으로 전환 + top-level `volumes:` 선언. 첫 생성 시 이미지 내용 복사받음 |
| 3 | 하 | `aegisvest/diary/rag.py` | `_log_recall` 절삭이 `write_text` (truncate-then-write) — `recall()` 은 `diary_lock` 밖이라 동시 실행 가능, 크래시·경합 시 손상. 감사가 세운 원자 쓰기 규율과 불일치 | `_io._write_atomic` (pid tmp + os.replace) 재사용 |
| 4 | 하(nit) | `aegisvest/tools/fundamentals.py` | `_annual_dividends` docstring 이 특별배당 완화를 일반화 — 연 1회 배당사는 `[정규, 특별]` 2건 → 중앙값이 평균 = 부풀림 (분기·월만 걸러짐). 기존 calendar-sum 대비 회귀는 아님 | docstring 에 "연 1회 배당사는 완화 안 됨" 명시 |

## 노트 (수정 안 함 — 판단·명세 필요)

- **골든/데스크로스 1거래일 창** (`config/diary_taxonomy.yaml`) — `spx_sma_50_prev` = 1거래일 전.
  주간 크루는 실행 직전 거래일에 교차가 났을 때만 태그. 다른 signal_rules 는 4주 창.
  주중 교차는 누락. RAG 검색 보조 태그라 영향은 낮음 — 창 폭은 4-6 튜닝/명세 결정.
- **DRY_RUN 이 일기는 기록** (`main.py`) — `run_organization` 이 dry_run 플래그를 안 받아
  크루 콜백 `log()` 가 항상 실행. 가동 전 스모크 기간의 일기 항목은 (a) shadow/regime_history
  미저장이라 대부분 `expired` 로 채점되거나 (b) exclusion/catalyst 만 SPY 대비 채점돼 RAG
  코퍼스 편입. **의도 확인 필요**: RAG 웜스타트면 유지, 순수 스모크면 dry_run 을 콜백까지 배선.
  ([test_e2e 가 이 동작을 명시적으로 검증 중])

## 검토했으나 finding 아님

- `main.py` DRY_RUN — `write_run` (리포트) 는 dry_run 에도 실행: `outputs/` 는 상태 아님, 스모크 산출물로 유용. OK.
- cron `evaluate && reviewer && rag` — reviewer 의 per-entry LLM 실패는 `_reflect` 가 삼킴 (None→errored++). `&&` 가 끊기는 건 load/save/import 파탄 시뿐이고 그땐 rag 스킵이 맞음. OK.
- `_annual_dividends` freq tie-break `max(sorted(set(counts)), key=counts.count)` — 동률이면 큰 빈도 (정상값). 결정론적. OK.
- ponytail `_load_shadow`/`report._load_org_pf`/`pipeline._demo` 레거시 폴백 제거 — `paper_portfolio.json` 은 미배포라 존재 불가. 호출부 None 처리 확인. OK.

## 검증
ruff / format / mypy(50) / pytest **282 passed, 2 deselected**.
커밋: `fix(post-e2e-review): E2E 시간의존·docker 볼륨 섀도·recall_log 원자성 4건`
