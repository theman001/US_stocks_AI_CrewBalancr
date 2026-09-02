# Pre-Phase-4 감사 pass 2 — guardrails/pm 독립 `/code-review` (high)

`agents/guardrails.py` · `agents/pm.py` (+ `organization._clamped`/`run_organization` 영향).
7건 중 5건 수정, 2건 문서화.

## 수정

| # | 위치 | 문제 | 수정 |
|---|---|---|---|
| 1 | `guardrails._HEDGE` | `~` 를 무조건 헤지로 봐서 `"2~4주"`·`"-0.2~0.2"` 같은 범위 표기(프롬프트가 지시)를 조작으로 반려 → 태스크 무한 재시도·실패 | `~` 는 **앞에 숫자 없을 때만** 헤지 (`(?<!\d)~\s*\d`). 범위는 통과 |
| 2 | `pm.py` + `organization.py` | `clamp_pm_draft` 가 **섹터캡(30%) 미적용** (결정론 사이저는 적용), 게다가 `check_constraints` FAIL 시 `_log.warning` 만 하고 org_orders 그대로 체결 → CLAUDE.md 절대 규칙 3(하드 가드레일 불가침) 위반 | `_enforce_sector_cap` 추가 (`portfolio_math._apply_sector_cap` 과 동형). 그래도 FAIL 이면 org_orders 를 **결정론 주문으로 폴백** |
| 3 | `pm.py:50` | 풀 매칭이 `p.category == pool[ticker]` — pool 은 소문자, LLM 이 `'LOW'` 로 내면 **전 종목 드롭 → PM 틸트 통째로 소실** (에러 없이). `_clamped` 의 `pm_cats` 도 같은 문제 | 카테고리를 `pool[ticker]`(소문자)로 정규화. `_clamped` 도 `.lower()`. `Position` 스키마 주석 수정 |
| 4 | `pm.py:47` | PM 이 같은 티커 2번 내면 `SizedPosition` 2행 → category_weights 이중계상, build_orders 중복 주문 | `seen` set 으로 티커 dedup (첫 항목만) |
| 5 | `guardrails._REFERENCE` | full 모드에서 `"-15%"`·`"-20%"`·`"-25%"` (3티어 손절 규격) 이 페이로드에 없어 반려 → Risk/Research 가 규격 인용 시 실패 | 손절·Rule of 40·배당성향 상수(`15/25/40/65/-15/-20/-25`) 를 `_REFERENCE` 에 추가 |

## 문서화만 (수정 안 함)

- **finding: 카테고리 종목 수가 `max_positions` 미제한** — `cat_pos` 가 이미 pool(=`max_positions
  x1.5`) 로 필터돼 있어 `n <= 1.5x max_positions`. 그 1.5x 여유는 "PM 재량"으로 **의도된 설계**
  (`report/phase-3 §5`). 각 종목은 여전히 밴드 하한 이상·단일캡 이하.
- **finding: `_NUM` 이 맨 정수(`%` 없는 `55`)를 검사 안 함** — "200일선"·"Rule of 40"·"S&P 500"
  같은 참조 정수를 반려하지 않으려는 **문서화된 트레이드오프**. 조작 정수가 프로즈에 섞여도
  다운스트림 수치는 전부 Layer 0 툴 산출(PM 제안은 `clamp_pm_draft` 가 override) — 시스템 보호
  유지. CLAUDE.md 절대 규칙 1.

## Round 2 — 0건

- `_HEDGE` "약 2~4주" → "약 2" 가 `약\s*\d` 로 매칭 = 여전히 헤지 (올바름, "약" 빼고 쓰면 통과).
- `_enforce_sector_cap` 이 `_enforce_caps`(고위험) 뒤 적용 — 둘 다 "캡까지 축소"라 순서 무관, 겹치면
  이중 축소가 맞음.
- 카테고리 정규화는 `model_copy(update=)` 로 새 Position — 원본 불변.

## 검증
- ruff / ruff format / mypy(50) / pytest **257 passed, 2 deselected**
- 신규 테스트 6: 범위표기·손절상수·대문자카테고리·티커중복·섹터캡·constraints FAIL 폴백
- 커밋: `fix(guardrails-pm): 독립 code-review 5건 (범위표기 헤지오탐·섹터캡 미적용·카테고리 대소문자·티커중복)`

## 남은 감사 패스
- pass 3: `tools/regime.py` · `screener.py` · `scoring.py` · `allocation.py`
