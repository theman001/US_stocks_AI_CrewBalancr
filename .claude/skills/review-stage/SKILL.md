---
name: review-stage
description: Round-based development review gate run when a build stage completes. Reviews the stage's new code plus any earlier-stage code even slightly affected by it, for logic errors, typos, code simplification, and performance. Repeats review→fix rounds until a round finds zero items needing fix. Triggers - "단계 검토", "빌드 단계 리뷰", "review-stage", "review stage 3a-3", "이 단계 검토해줘", or before checking off a docs/BUILD_PLAN.md step.
---

# review-stage — 개발 단계 완료 검토 게이트

빌드 단계 하나가 끝났을 때 실행한다. **라운드를 반복**해 수정 필요 건이 0이 될 때까지
검토→수정을 돈다. 한 라운드가 findings 0건이면 그 라운드에서 종료.

---

## 1. 스코프 결정

### 1.1 이번 단계 코드
- `git diff <단계 시작 커밋>..HEAD --name-only` 로 신규·변경 파일 수집.
- 단계 시작 커밋을 모르면: `docs/BUILD_PLAN.md` 의 직전 완료 단계 커밋, 또는 사용자에게 확인.

### 1.2 영향받는 이전 단계 코드 (impact scope)
이번 코드와 결합된 기존 모듈을 포함한다. "**조금이라도 영향**" 기준 — 애매하면 포함.
- **정방향**: 이번 코드가 import/호출하는 기존 모듈 → 호출되는 인터페이스 검토
- **역방향**: 이번 코드가 시그니처·반환값·부작용·예외·성능 특성을 바꾼 기존 모듈
  → 그것을 쓰는 **모든 기존 호출부** (`grep -rn "모듈명\|심볼명" aegisvest/`)
- **공유 자원**: 이번 코드가 읽고/쓰는 `state/*.json` · `config/*.yaml` 키를
  함께 만지는 기존 모듈
- **스키마**: 변경된 Pydantic 모델(`schemas.py`)을 쓰는 모든 곳
- 기본 1-hop 이웃, 강결합이면 2-hop.

### 1.3 스코프 확정
검토 대상 파일 목록 + 각 파일이 스코프에 든 사유를 출력하고 시작.

---

## 2. 검토 차원 (매 라운드 전부 적용)

| 차원 | 확인 항목 |
|---|---|
| **논리 오류** | 경계 조건, off-by-one, 부호, **단위**(bp↔%, KRW↔USD, 비율↔퍼센트), None/빈 컬렉션, 잘못된 비교 연산자(`>` vs `>=`), 조기 반환, 예외 삼킴, 잘못된 기본값, 시점 오염(look-ahead) |
| **오타** | 변수·dict 키·태그 문자열, config 키 불일치, 컬럼명, 로그·에러 메시지, 주석과 코드 불일치 |
| **코드 최적화** | 중복 로직, 재구현된 stdlib, 불필요한 추상화(단일 구현 인터페이스·팩토리), 죽은 코드, 반복 상수→config, 복잡한 분기 단순화 (ponytail 사다리) |
| **성능 최적화** | 루프 내 반복 계산·IO, N+1 API 호출(배치 가능?), 불필요한 DataFrame 복사, 캐시 미적용, 벡터화 가능한 pandas 반복, 재계산되는 임베딩 |
| **명세 대조** | 해당 `report/phase-N-*.md` 절과 구현 동작 일치? 임계값·공식·규칙·기본값이 문서와 **정확히** 동일한가 |
| **프로젝트 불변식** | 숫자는 파이썬 툴만(LLM 암산 없음) · 툴은 예외 raise 안 하고 error dict · 에이전트 재량 ±3%p 하드 · `Process.sequential` · 결정론 코어에 LLM 미포함 |
| **계약 준수** | 툴 → `docs/TOOLS.md` I/O 스키마 / 에이전트 → `docs/PROMPTS.md` 규격 / 테스트 → `docs/TESTING.md` 시나리오 커버 |

각 finding: `file:line · 차원 · 문제 · 수정안`. **확신 없는 지적은 제외** (verify 후 남은 것만).

---

## 3. 라운드 루프

```
round = 1
while True:
    findings = 스코프 전체를 §2 차원으로 검토
    docs/reviews/<stage>.md 에 Round N 결과 기록
    if len(findings) == 0:
        "Round N: 수정 필요 0건 — 검토 종료" 기록 후 break
    수정 적용
    uv run ruff check aegisvest && uv run ruff format aegisvest \
      && uv run mypy aegisvest && uv run pytest -q        # 회귀 확인
    if 테스트 실패:
        그 수정을 재작업 (다음 라운드로 넘기지 않음)
    수정으로 새로 바뀐 파일을 스코프에 추가
    round += 1
    if round > 6:
        남은 findings 보고하고 중단, 사용자 개입 요청     # 안전 상한
```

- **종료 조건**: 한 라운드의 findings 가 0건.
- 각 라운드는 이전 라운드 수정으로 파생된 변경까지 새로 훑는다 (수정이 새 버그를 만들 수 있음).
- 수정이 명세와 충돌하면 코드가 아니라 판단을 사용자에게 확인 (명세가 우선).

---

## 4. 산출물 — `docs/reviews/<stage>.md`

```markdown
# Stage <stage> 검토

## 스코프
- 신규: aegisvest/tools/rebalance.py, tests/test_tools/test_rebalance.py
- 영향: aegisvest/tools/allocation.py (rebalance 가 보간 결과 소비 — 반환 키 의존)
        config/allocation.yaml (밴드 임계값 공유)

## Round 1
- [논리] rebalance.py:47 — 밴드 비교 `abs(drift) > band` 인데 `>=` 여야 (경계값 4.0%p 누락). → `>=`
- [성능] rebalance.py:88 — 카테고리별 현재가 개별 조회. MarketDataTool 배치 호출로. → batch
- [명세대조] rebalance.py:31 — 쿨다운 7거래일. phase-2 §3.3 은 10거래일. → 10

## Round 2
- [오타] rebalance.py:52 — dict 키 `"contrib"` vs 생성부 `"contribution"`. → 통일

## Round 3
- 수정 필요 0건. 검토 종료.

## 최종
ruff / mypy / pytest 통과. 커밋: review(3a-6): 3 rounds, 4 findings fixed
```

---

## 5. 완료 후
- `docs/BUILD_PLAN.md` 해당 단계에 ✅ + `docs/reviews/<stage>.md` 링크
- 커밋: `review(<stage>): N rounds, M findings fixed` + Co-Authored-By 라인
- 빌트인 `/code-review`·`/ponytail-review` 와 병행 가능 — 이 스킬은 **단계 게이트 +
  0건까지 반복** 이 핵심.
