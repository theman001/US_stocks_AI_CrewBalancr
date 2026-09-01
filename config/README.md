# config/ — 임계값·가중치·에이전트 정의

숫자 임계값은 **전부 여기 YAML에**. 코드에 하드코딩 금지. 원 근거는 `report/`.

| 파일 | 생성 단계 | 근거 |
|---|---|---|
| `regime_rules.yaml` | 3a-3 | report/phase-2 §1 (6축 임계값 + 보간 앵커 + signal_rules) |
| `allocation.yaml` | 3a-6 | report/phase-2 §2 + phase-3 §8 (가드레일, nav_tiers) |
| `filters/{low,mid,high}.yaml` | 3a-5 | report/phase-1 A (하드 필터) |
| `scoring/{low,mid,high}.yaml` | 3a-5 | report/phase-1 A (스코어링 가중치) |
| `agents.yaml` / `tasks.yaml` | 3a-9, 3b | docs/PROMPTS.md |
| `diary_taxonomy.yaml` | Phase 4 | report/phase-4 §7 |
