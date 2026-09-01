# PROMPTS.md — 에이전트 프롬프트 관리 가이드

> 조직 상세는 `report/phase-3-organization-and-paper-trading.md` §2~§5.
> 스캐폴딩은 `.claude/skills/add-agent`.

## 원칙
- 프롬프트는 코드가 아닌 `config/agents.yaml`(role/goal/backstory) +
  `config/tasks.yaml`(description/expected_output/context) 에 둔다.
- 계산·판단 에이전트 backstory 에 아래 "절대 규칙" 블록 공통 삽입.
- 페르소나는 3~4문장. 장황 금지 (컨텍스트 낭비).
- **파이썬 = 사실(scrape·계산), AI = 판단(정리·해석·분석·결정).**

## 공통 삽입 블록: 절대 규칙 (계산·판단 에이전트)
```
## 절대 규칙 (위반 시 출력 폐기)
1. 어떤 숫자도 직접 생성하지 않는다. 모든 수치는 이번 태스크의 툴 호출
   반환값 또는 상류 태스크가 전달한 값이어야 한다.
2. 데이터가 없으면 툴을 호출하라. 툴 실패 시 "DATA_UNAVAILABLE: <필드>"
   라고만 쓰고 추정하지 마라.
3. 산술(비율·가중평균 포함) 암산 금지. 계산 툴을 호출하라.
4. 출력의 모든 숫자 필드에 source_tool 과 source_call_id 를 붙여라.
5. "약", "대략", "추정" 으로 수치를 말하면 실패다.
```

## 현재 구현 (3a-9): 3 에이전트
`config/agents.yaml` — `macro_strategist`(①) / `analyst`(②③④ 통합) / `cio`(⑧).
`config/tasks.yaml` — `macro_brief` → `analyst_view` → `cio_decision` (Process.sequential).
CIO 는 `APPROVED`/`HOLD` (HOLD = 이번 주 리밸런싱 보류, 주문 수량·비중 불변).
공통 삽입 블록은 `agents/crew.py._ABSOLUTE_RULES` 가 `{absolute_rules}` 자리에 주입.
분할(②③④⑤)·⑥PM·⑦Risk·⑨Reviewer 는 3b/Phase 4.

## 9 에이전트 규격 요약 (목표 조직)

| # | 에이전트 | role 요지 | temp | 툴 | 재량 |
|---|---|---|---|---|---|
| ① | Macro Strategist | 레짐 해설·상충·리스크 시나리오 | 0.2 | MacroData(선택) | 없음 |
| ② | Fundamental Analyst | 저·중위험 재무 코멘트·정성 리스크 플래그 | 0.2 | News, Fundamentals | exclude 권고 |
| ③ | Thematic Analyst | 고위험 테마·촉매·크라우딩 | 0.3 | News, Technical | 테마강도 조정(제한), exclude |
| ④ | News & Sentiment | 주간 내러티브·이벤트 리스크 | 0.3 | News | 없음 |
| ⑤ | Research Director | 노트 4종 상충 조정 → 하우스뷰 | 0.2 | 없음 | 슬리브 스탠스 권고 |
| ⑥ | Portfolio Manager | 결정론 배분 + 하우스뷰 틸트 → 초안 | 0.2 | PortfolioMath, PositionSizer | **±3%p, 상위풀 내, 편입불가** |
| ⑦ | Risk Officer | 독립 검증, 거부권 | 0.1 | ConstraintChecker, PortfolioMath | REJECT 1회 반려 |
| ⑧ | CIO | 최종 승인 + IC 메모 | 0.2 | 없음 | 승인/보류만, 숫자 불변 |
| ⑨ | Performance Reviewer | 과거 판단 채점·반성·태깅 | 0.2 | MarketData, News | 없음 (사후) |

## 태스크 작성 규칙 (`config/tasks.yaml`)
- `context: [상류 태스크]` 명시 (Process.sequential).
- `expected_output` 에 Pydantic 스키마 이름 명시 (`aegisvest/schemas.py`).
- 애널리스트(①~④)는 `async_execution: true`.
- 각 태스크에 `guardrail: no_fabricated_numbers`.
- 태스크 완료 콜백: (1) `diary.logger.log(...)` (2) `notify.post_agent_note(...)`.
- 실행 전: `DiaryRAG.recall()` 결과를 description 에 "과거 유사 판단 사례" 주입 (Phase 4).

## ⑥ Portfolio Manager 재량 한계 (하드, 절대)
- 카테고리 목표 대비 ±3%p
- 종목은 카테고리별 스코어 상위 N (= max_positions × 1.5) 안에서만 선택
- `ResearchView.excluded_tickers` 강제 제외
- 신규 종목 추가 불가, 하드 가드레일 위반 불가
- 주문 수량 임의 조정 불가 (PortfolioMathTool 계산 고정)

## ⑨ Performance Reviewer — 사후확신 편향 방지
- 입력: `data_snapshot` + **판단일 당일·이전** 뉴스 + `outcome`. 하인드사이트 서술 미제공.
- 강제 구조: "당시 가용했으나 놓친 신호: ___(인용). 저평가한 이유: ___. 수정 휴리스틱: ___"
- "더 신중했어야" 등 구체 신호 없는 출력 반려.
- `lesson_card` ≤ 25 토큰 강제.

## 리뷰 체크리스트 (프롬프트 수정 시)
- [ ] backstory 4문장 이하
- [ ] 계산·판단 에이전트에 절대 규칙 블록
- [ ] goal 에 사용할 툴 이름 명시
- [ ] temperature 가 위 표와 일치
- [ ] expected_output 에 스키마 지정
- [ ] guardrail·diary·notify 콜백 연결
- [ ] ⑥은 재량 한계 4항 전부 명시
