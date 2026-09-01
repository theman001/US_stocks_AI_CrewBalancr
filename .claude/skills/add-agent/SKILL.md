---
name: add-agent
description: Scaffold a new CrewAI agent + task for the AegisVest fund organization. Use when adding/implementing any of the 9 agents (Macro Strategist, Fundamental Analyst, Thematic Analyst, News Analyst, Research Director, Portfolio Manager, Risk Officer, CIO, Performance Reviewer). Triggers - "새 에이전트", "add agent", "X 에이전트 구현", "implement the ... agent".
---

# add-agent — AegisVest 조직 에이전트 규격

먼저 `report/phase-3-organization-and-paper-trading.md` §3 (해당 에이전트 상세)와
`docs/PROMPTS.md` 를 읽어라. 에이전트는 **판단만** 한다 — 숫자는 Layer 0 툴에서.

## 규칙

1. 정의는 `config/agents.yaml` (role/goal/backstory) + `config/tasks.yaml`
   (description/expected_output/context). 코드에 하드코딩 금지.
2. **계산·판단 에이전트**의 backstory 에 `docs/PROMPTS.md` 의 "절대 규칙" 블록 삽입.
3. `backstory` 페르소나는 3~4문장. 장황 금지 (컨텍스트 낭비).
4. temperature (역할별):
   - Risk Officer 0.1 / Macro·Fund·RD·PM·CIO·Reviewer 0.2 / Thematic·News 0.3
5. **툴 최소화.** 툴 사용 = ①Macro ②Fund ③Thematic ⑨Reviewer 만.
   ④~⑧ 은 툴 없음 (상류 구조화 출력 + 파이썬 결과만 소비). DeepSeek 툴콜 리스크 축소.
6. `output_pydantic` 로 출력 스키마 강제 (`aegisvest/schemas.py`). 숫자 필드엔
   `source_tool` / `source_call_id`.
7. 태스크에 `guardrail=no_fabricated_numbers` 지정 — 출력의 모든 숫자를 입력
   페이로드와 대조, 불일치 시 재요청.
8. 애널리스트 태스크(①~④)는 `async_execution=True`.
9. `context` 명시로 상류 태스크 산출물 전달 (Process.sequential).
10. **판단 일기 로깅**: 태스크 완료 콜백에서 `diary.logger.log(agent, claim_type,
    claim, reasoning, data_snapshot, decision, horizon_weeks)` 호출.
    claim_type: report/phase-4 §2.1 표 참조.
11. **회상 주입**: 태스크 실행 전 `DiaryRAG.recall(situation, role, k=4)` 결과를
    태스크 description 에 "과거 유사 판단 사례" 로 주입 (Phase 4 가동 후).
12. `task_callback` 으로 노트를 Mattermost 게시 (`notify.post_agent_note`) —
    ①~⑤ → `#aegis-research`, ⑥~⑧ → `#aegis-decisions`.

## 재량 한계 (⑥ Portfolio Manager 전용, 하드)
- 카테고리 목표 대비 ±3%p
- 종목은 카테고리별 스코어 상위 N (= max_positions × 1.5) 안에서만
- `ResearchView.excluded_tickers` 강제 제외
- 신규 종목 추가·하드 가드레일 위반·주문 수량 임의조정 불가 (PortfolioMathTool 고정)

## 스캐폴딩 순서
1. `aegisvest/schemas.py` 에 출력 모델 (예: `MacroBrief`, `ResearchView`).
2. `config/agents.yaml` / `config/tasks.yaml` 항목 추가.
3. `aegisvest/agents/<name>.py` — Agent·Task 빌더 + 콜백 바인딩.
4. 파이프라인(`main.py` / Flow)에 순서·context 연결.
5. `tests/` — mock LLM(recorded) 로 스키마 통과 + guardrail 동작 (TEST_GUIDE 시나리오 6).
