# Phase 4 — 독립 `/code-review` (high) 후속 수정

`84da276..HEAD` (4-1~4-5) 를 빌트인 `/code-review` high 로 별도 검토. 7건 중 6건 수정,
1건은 본질적 한계로 문서화. review-stage 스킬(자가 검토)이 놓친 것들.

## 수정

| # | 위치 | 문제 | 수정 |
|---|---|---|---|
| 1 | `diary/logger.py` | `save_entries` 전체 rewrite 가 동시 `log()` append 와 경합 → 위기 크루가 주간 배치·거버넌스 CLI 와 겹치면 항목 유실 | `diary_lock()` (fcntl.flock) 추가. `log()` 은 append 시 짧게, evaluate/reviewer/rag/governance 는 load→save 전체를 감쌈 |
| 2 | `diary/governance.py:52` | `_recall_counts` 가 `ValueError` 만 포획 — 비-dict JSON 라인이면 `.get()` AttributeError 로 `review` CLI 전체 크래시 (4-2 에서 고친 것과 동일 버그류) | `isinstance(row, dict)` 가드 |
| 3 | `diary/reviewer.py:114` | `_merge_tags` 가 entry.tags 먼저 + 8개 절삭 → 이미 8태그면 event/theme/mistake 전부 유실 (하이임팩트 pending_review 케이스에서), pending_tags 엔 적용된 것처럼 기록 | 초과 시 `signal:` 태그부터 버림 (data_snapshot 에서 재도출 가능, 반성 태그는 1회뿐) |
| 4 | `agents/crew.py` | `_numbers_in` 이 회상 블록 전체(유사도 0.82·월 2026-07 등)를 파싱해 ⑤⑦ guardrail `extra_allowed` 에 whitelist → 조작 수치 통과 가능 (CLAUDE.md 절대 규칙) | `_numbers_in`/`_DESC_NUM` 삭제. 회상 주입 태스크는 `hedge_only=True` (카드 수치는 참고 컨텍스트지 이번주 페이로드 아님, ①②③⑥ 와 동일). `recall` 를 `make_task` 에 별도 파라미터로 |
| 5 | `diary/reviewer.py:193` | `run()` 이 루프 끝에 1회만 save → 배치 중간 종료 시 완료된 유료 LLM 반성 전부 유실·재과금 | 반성 1건마다 `save_entries` |
| 6 | `diary/evaluate.py:182` | `_label_matches` 가 정확히 BULL/BEAR/CRISIS 만 인식 — LLM 자유서술('cautiously bullish')은 조용히 NEUTRAL 밴드로 오채점 | `_normalize_regime` (부분일치, CRISIS·BEAR 우선). 불명확 → None → expired (오채점 대신) |

## 문서화만 (코드 변경 없음/최소)

- **#7 `_recall_block` 이 크루 실행 중 bge-m3(~2.3GB) 로드** — 쿼리 임베딩은 크루 시점에만
  가능해 본질적으로 회피 불가 (§6.1). 완화: `_MIN_CORPUS=5` 게이트 추가 — 얇은 일기 기간엔
  임베딩 자체를 스킵. 상주 컨테이너에선 `@lru_cache` 로 모델 1회 로드 후 유지. `report/phase-4 §6`
  노트를 정직하게 갱신 ("~1-3s" 는 추론만, 초회 로드는 별도).
- **#4 트레이드오프**: ⑤⑦ 가 회상 주간엔 hedge_only 라 "페이로드에 없는 55%" 류를 못 잡음.
  단 ⑤⑦ 출력은 PM(파이썬 ±3%p 클램프)·CIO(승인/보류만)가 소비하고 최종 수치는 Layer 0 툴이
  내므로 실질 리스크 낮음. 카드 본문 수치만 추출하는 정밀화는 4-6.

## 검토했으나 finding 아님 (`/code-review` 가 clear)

- `recall` dedupe-before-floor: `_structural`/`_recency` 가 entry 레벨이라 max-rank == max-cosine,
  floor 가 above-floor 벡터 있는 항목을 떨구지 않음 → 4-4 R1 의 "스펙 순서" 수정은 불필요했으나 무해.
- `DiaryEntry.post_mortem` str→dict: 외부 reader 없음 (grep 확인).
- reviewer hedge_only, `_diversify`, `needs_reflection` 재현성, `_score_excess_return` invert,
  `clip_tokens` 한글 근사, `rag.index` 자격/idempotency — 전부 정상.

## 검증
- ruff / ruff format / mypy(50) / pytest **246 passed, 2 deselected**
- 신규 테스트 3: `_normalize_regime` + 미채점 만료, 태그 오버플로 signal 우선 폐기, `_MIN_CORPUS` 스킵
- 커밋: `fix(4-post-review): 독립 code-review 7건 (동시성 락·태그 오버플로·guardrail·레짐 정규화)`
