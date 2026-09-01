# AegisVest — 구상(명세) 단계 리포트

이 폴더는 개발 착수 전 **구상·명세 단계에서 논의된 모든 내용**을 단계별로 축적한다.
개발 단계에서는 이 폴더를 단일 근거(source of truth)로 참조한다.

## 인덱스

| 단계 | 파일 | 내용 | 상태 |
|---|---|---|---|
| Phase 1 | [phase-1-conception.md](phase-1-conception.md) | 리스크별 전략 카테고리(A), 동적 자산배분(B), CrewAI 조직구조(C), Claude Code 설정파일(D) | ✅ 확정 |
| Phase 2 | [phase-2-macro-and-rebalancing.md](phase-2-macro-and-rebalancing.md) | 매크로 레짐 판별(복합 경기축), 슬라이드식 배분, 리밸런싱 주기, 현금흐름 리밸런싱, Radxa/OMV8 단일 컴포즈 배포, 성공 판정 2단 게이트, Mattermost 알림, 백테스트 데이터 2단계 | ✅ 확정 (세제 잠정) |
| Phase 3 | [phase-3-organization-and-paper-trading.md](phase-3-organization-and-paper-trading.md) | 9-에이전트 4계층 조직, 재량 한계(B), 백테스트↔조직 분리(C), Mattermost 모니터링, PaperBroker, 섀도 A/B, 소액 포트 NAV 티어, 빌드 단계 3a/3b | ✅ 확정 (Phase 1 과제 C 대체) |
| Phase 4 | [phase-4-judgment-diary-rag.md](phase-4-judgment-diary-rag.md) | 판단 일기 RAG — 기록·채점·반성·태깅·이중벡터·회상, ChromaDB + bge-m3 로컬, 통제 어휘 태그, 콜드스타트 전략 | ✅ 확정 (가동은 모의투자 ~3개월 후) |

**명세 단계 완료.** 개발은 Phase 3 §9 빌드 순서(3a-1 스캐폴딩)부터 착수.

## 규칙

- 각 Phase 논의가 끝나면 해당 마크다운 파일을 이 폴더에 추가하고 위 인덱스를 갱신한다.
- 확정된 수치·임계값은 개발 시 `aegisvest/config/*.yaml` 로 옮기며, 원 근거는 이 리포트에 남긴다.
- 모든 임계값은 백테스트·페이퍼트레이딩으로 재보정 전제. 이 문서는 투자 자문이 아니다.
