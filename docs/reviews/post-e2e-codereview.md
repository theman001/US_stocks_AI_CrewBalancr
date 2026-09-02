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

## 노트 → 사용자 판단 후 수정 (2026-09-02)

- **DRY_RUN 이 일기 기록** → **옵션 1: `run_organization(dry_run=)` 스레딩** (최초엔 `persist_diary`,
  후속에서 개명). `main` 이 `dry_run=s.dry_run` 전달 → `make_task`/`_callback`/`_Ctx`/
  `_log_org_diary`/`_recall_block` 가 가드. 엄격 계약 = 드라이런은 shadow·regime·일기·RAG·
  회상·Slack 노트 전부 스킵, `state/` 무접촉. `log()` 전역 의미는 안 건드림 (오케스트레이터가
  결정). `test_dry_run_full_chain_no_persistence` → `load_entries() == []` + chroma 미생성.
- **골든/데스크로스 창** → **옵션 1: 상태 기반**. `spx_sma_50 < spx_sma_200` (1거래일 prev
  비교 제거). `yield_curve_inversion` 과 동일 패턴. `MacroData.spx_sma_*_prev` 2필드 제거
  (다른 사용처 없음). report/phase-4 §7.2 결정 노트.

## 검토했으나 finding 아님

- `main.py` DRY_RUN — `write_run` (리포트) 는 dry_run 에도 실행: `outputs/` 는 상태 아님, 스모크 산출물로 유용. OK.
- cron `evaluate && reviewer && rag` — reviewer 의 per-entry LLM 실패는 `_reflect` 가 삼킴 (None→errored++). `&&` 가 끊기는 건 load/save/import 파탄 시뿐이고 그땐 rag 스킵이 맞음. OK.
- `_annual_dividends` freq tie-break `max(sorted(set(counts)), key=counts.count)` — 동률이면 큰 빈도 (정상값). 결정론적. OK.
- ponytail `_load_shadow`/`report._load_org_pf`/`pipeline._demo` 레거시 폴백 제거 — `paper_portfolio.json` 은 미배포라 존재 불가. 호출부 None 처리 확인. OK.

## A+B 재검토 (2026-09-02) — 수정 0건

`e32da9e` (A: persist_diary 스레딩 / B: 크로스 상태 기반) 독립 재검토.

**확인 (정상)**
- 일기 쓰기 경로 3곳 전부 게이트: `crew._log_diary` (`_callback` 의 `dry_run`),
  `organization._log_org_diary` ×2 (`if not dry_run`). 누락 없음.
- `run_reviewer` 는 `make_task`/callback 안 쓰고 Task 직접 생성 → `diary.log()` 미호출.
  post_mortem 은 기존 항목에 append (월요일 배치, 드라이런엔 evaluated 항목 없음). 갭 아님.
- `_last_float` 이 NaN→None 변환 → `spx_sma_50/200` 은 `float|None`, `is not None` 가드로 충분.
- 제거된 `spx_sma_*_prev` — 디스크 영속 상태에 없음 (미배포). 옛 일기 `data_snapshot` dict 에
  키가 남아도 새 룰은 `spx_sma_50/200` (여전히 존재) 만 참조 → 무해.
- `build_query` 도 스냅샷에서 `signal:death_cross` 를 방출 → 쿼리·문서 코호트 매칭 일관
  (이벤트 버전은 쿼리가 태그를 거의 안 달아 매칭 실패했음 — 상태 버전이 실제로 더 나음).

**노트**
- `death_cross`/`golden_cross` 가 상태 태그화 → 추세장엔 다수 항목에 붙어 약한 판별자
  (`regime:bear` 급). 위기 시 signal 다발이면 8-태그 캡이 밀어낼 수 있음. `yield_curve_inversion`
  과 동일 성질. 사용자 선택한 트레이드오프.

**후속 처리 (2026-09-02) — 리뷰 노트 소규모 2건**
- `persist_diary` (bool, 기본 True) → **`dry_run`** (bool, 기본 False) 로 개명. 이제 일기뿐
  아니라 `_recall_block` (→ `state/chroma` 생성 방지)·`post_agent_note` (Slack 노트) 까지 게이트.
  드라이런 = `state/` **완전 무접촉**, 크루 출력은 리포트·`outputs/<run_id>/crew.json` 에만.
  `test_dry_run_full_chain_no_persistence` 에 `not (state_dir/"chroma").exists()` 추가.
- crisis 픽스처 현실화 — `make_pipeline_result(crisis=True)` 매크로에 `spx_last=88`,
  `spx_sma_50=94`, `spx_sma_200=100` (SPX 가 양 SMA 아래, 50<200). `test_diary_tags_include_
  macro_signals` 에 `signal:death_cross` assert (태그 7개, 8-캡 이내).

## 검증
ruff / format / mypy(50) / pytest **282 passed, 2 deselected**.
커밋: `fix(post-e2e-review): E2E 시간의존·docker 볼륨 섀도·recall_log 원자성 4건`
+ `fix(dry-run): 엄격 계약 — 일기·RAG 미기록 (persist_diary 스레딩) + 크로스 신호 상태 기반`
