# 검토 문서 인덱스

빌드 단계 게이트(`review-stage` 스킬) + 독립 `/code-review` 감사 + 오버엔지니어링 스캔 기록.
진행 현황은 [../BUILD_PLAN.md](../BUILD_PLAN.md).

## 단계 게이트 (review-stage — 0건까지 반복)

| 단계 | 대상 |
|---|---|
| [3a-2](3a-2.md) | 데이터 툴 (market_data · fundamentals · macro_data · news + _io/_prices) |
| [3a-3](3a-3.md) | 레짐 엔진 (regime_score · 6축 채점 · EMA · CRISIS 래치) |
| [3a-4](3a-4.md) | 감시견 (일일 macro→regime · crisis_state persist · 알림) |
| [3a-5](3a-5.md) | 스크리너 + 스코어링 (FMP→yfinance 전환) |
| [3a-6](3a-6.md) | 배분 + 리밸런싱 (슬라이드 보간 · 밴드 · 쿨다운 · 하드 가드레일) |
| [3a-7](3a-7.md) | PaperBroker + 벤치마크 + 섀도 A/B (TWR 지표) |
| [3a-8](3a-8.md) | pipeline.py 결정론 코어 조립 + PositionSizer |
| [3a-9](3a-9.md) | 에이전트 ①②③⑧ + 가드레일 + 판단 일기 훅 |
| [3a-10](3a-10.md) | report.py + main.py 주간 오케스트레이션 |
| [3b-1](3b-1.md) | 애널리스트 4분할 (②③④) + ⑤ Research Director |
| [3b-2](3b-2.md) | ⑥ PM + ⑦ Risk Officer + 반려 루프 (crewai.Flow) |
| [3b-3](3b-3.md) | 섀도 A/B 이중 포트폴리오 병행 추적 |
| [4-0](4-0.md) | 판단 일기 태깅 하네스 (통제 어휘 + signal_rules + 원자료 스냅샷) |
| [4-1](4-1.md) | diary/evaluate.py 결정론 채점 |
| [4-2](4-2.md) | ⑨ Performance Reviewer (post_mortem + 태깅 + lesson_card) |
| [4-3](4-3.md) | diary/rag.py bge-m3 이중 벡터 저장 |
| [4-4](4-4.md) | DiaryRAG.recall + O-A 랭킹 + P-D 주입 |
| [4-5](4-5.md) | 거버넌스 CLI (`python -m aegisvest.diary review`) |

## 독립 `/code-review` 감사

Pre-Phase-4 7패스 + 4-post + post-e2e + whole-integration = 9패스, 전 `aegisvest/` 커버.
~58 findings / ~55 수정 — 대부분 "조용한 왜곡" (크래시 아닌 미묘한 숫자 오류) 으로
Gate B 성공 판정을 오염시킬 부류. whole-integration 은 섹터 간 연결부 전담.

| 패스 | 대상 |
|---|---|
| [money-path](money-path-codereview.md) | broker/ · portfolio_math · pipeline · main · state (TWR 기여일 · 섀도 레짐 이중계산 · atomic write) |
| [guardrails-pm](guardrails-pm-codereview.md) | guardrails.py · pm.py (`~` 헤지 오탐 · 섹터캡 미적용 · 카테고리 대소문자 틸트 소실) |
| [regime-screen](regime-screen-codereview.md) | regime.py · screener.py · allocation.py (low_confidence 외삽 · EMA 이중계산 · 고위험캡 스필) |
| [runtime](runtime-codereview.md) | watchdog · report · constraints · state (벤치 기여 미보정 · 인코딩 미지정 · 리밸 게이트 미작동) |
| [data-tools](data-tools-codereview.md) | macro_data · market_data · fundamentals · news · _io · _prices (dropna 최신봉 손실 · 캐시 손상 · _cagr 기준연도) |
| [scoring-derived](scoring-derived-codereview.md) | scoring · _derived · breadth · universe · config (폭 4w 분모 · roic 결측 · piotroski 부분점수) |
| [4-post](4-post-codereview.md) | 4-1~4-5 빌트인 `/code-review` (동시성 fcntl 락 · _normalize_regime · 회상 guardrail) |
| [post-e2e](post-e2e-codereview.md) | 감사 이후 추가분 (ponytail·DRY_RUN·E2E·배당 rate) — E2E 시간의존 · docker 볼륨 섀도 · recall_log 원자성 |
| [whole-integration](whole-integration-codereview.md) | **섹터 간 연결부** 전체 검토 — regime_history 절삭이 regime_call 채점창 침범 · 일기 save 비원자 · state 손상 격리 · _diary_snapshot 통합 |

## 그 외

| 문서 | 내용 |
|---|---|
| [ponytail-cleanup](ponytail-cleanup.md) | 오버엔지니어링 스캔 — 죽은 config·스키마·레거시 코드 + `requests-cache`/`crewai-tools` 의존성 제거 (동작 변화 0) |
| [e2e](e2e.md) | E2E 통합 테스트 — 실 파이프라인 + 실 조직(ScriptedLLM) + 실 일기 체인 한 번에 태우기 |
