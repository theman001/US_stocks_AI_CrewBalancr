# AegisVest — Phase 4 구상 보고서: 판단 일기 RAG

> **작성일**: 2026-09-01
> **상태**: 확정 (가동은 모의투자 데이터 ~3개월 축적 후)
> **선행 문서**: [phase-3-organization-and-paper-trading.md](phase-3-organization-and-paper-trading.md)

파인튜닝 없이 "쌓일수록 똑똑해지는" 메커니즘. 에이전트의 판단을 실제 결과로 채점하고, 반성을 남기고, 태깅·벡터화해서 RAG로 저장 → 이후 판단 시 유사 사례를 회상.

---

## 0. 결정 요약

| # | 결정 | 선택 |
|---|---|---|
| I | 벡터 DB | **ChromaDB 임베디드** (PersistentClient, 디렉토리, 새 컨테이너 없음) |
| J | 임베딩 모델 | **bge-m3 로컬** (~2.3GB, 1024차원, 다국어, `FlagEmbedding`/`sentence-transformers`) |
| K | Reviewer 자율성 | 대형 틸트·위기 콜·레짐 콜 → **인간 확인 후 RAG 진입**, 나머지 자동 |
| L | 채점 주체 | **100% 결정론 파이썬** (LLM은 서술만) |
| M | 채점 job 실행 | **주간 별도 cron** (감시견·크루와 분리, 배치) |
| N | 임베딩 대상 | **이중 벡터** — situation 벡터 + lesson 벡터 별도 |
| O | 랭킹 가중 | **`0.65·코사인 + 0.20·구조매칭 + 0.15·최근성`** (3항). 추후 O-D 학습형으로 전환 예정 |
| P | 주입 tier | **적응형** — top-1(코사인≥0.75) 중간 요약 ~120토큰 + 나머지 카드 ≤25토큰, 툴 없음 |
| Q | 후보 좁히기 | **캐스케이드 없음** — 벡터 프리필터 top-40 → 단일 채점 패스 |

---

## 1. 5단계 생애주기

```
① 기록 ───→ ② 채점 ───→ ③ 반성 ───→ ④ 벡터화·저장
  (기록시)   (파이썬,     (Reviewer   (bge-m3 이중벡터
             주간배치)     LLM)         + ChromaDB)
   │                                        │
   └──────────── ⑤ 회상 (판단 전 유사 사례 주입) ◀──┘
```

**분업**: ①④⑤ = 파이썬 / ② 채점 = 파이썬 (점수는 정량 규칙) / ③ 서술 = LLM (⑨ Performance Reviewer)

---

## 2. 단계 ① 기록

### 2.1 일기로 남기는 판단 (`claim_type`)

| claim_type | 생성 에이전트 | 채점 방법 | 기본 horizon |
|---|---|---|---|
| `regime_call` | Macro Strategist | 예측 레짐 유지 여부 + watch_item 발동 | 4주 예비 + 12주 최종 |
| `sleeve_stance` | Research Director | 슬리브 상대 성과 vs 예측 | 12주 |
| `allocation_tilt` | Portfolio Manager | 섀도 A/B 틸트 기여도(±%p) | 12주 |
| `exclusion` | Fund/Thematic/RD | 제외 종목 수익률 vs 카테고리 중앙값 | 12주 |
| `event_risk` | News Analyst | 이벤트 발생 여부 × 예측 방향·크기 | 이벤트일 + 2주 |
| `catalyst` | Thematic Analyst | catalyst_date ±2주 가격 반응 | 이벤트일 + 2주 |
| `risk_veto` | Risk Officer | 지적 리스크 실현 여부 | 8주 |
| `cio_override` | CIO | override 결과 타당성 | 12주 |

### 2.2 항목 스키마 (최종)

```json
{
  "id": "2026-10-05_PM_tilt_high",
  "run_id": "2026-10-05", "agent": "Portfolio Manager",
  "created_at": "2026-10-05T13:00:00Z",
  "claim_type": "allocation_tilt",
  "claim": "고위험 목표 13% → 10.5% 방어 틸트",
  "reasoning": "RD underweight + News 11/5 규제 리스크(high) + Thematic PLTR crowding",
  "supporting_refs": ["2026-10-05_RD_high_uw", "2026-10-05_NEWS_reg_1105"],
  "data_snapshot": {
    "score_smooth": 1.2, "regime": "NEUTRAL",
    "hy_oas_bp": 355, "hy_oas_4w_change_bp": 12, "vix": 17.1, "vix3m": 18.0,
    "vix_1d_change_pct": 0.02, "pct_above_200dma": 58, "pct_above_200dma_4w_change": -3,
    "yc_10y_3m_bp": 45, "sma50": 5820, "sma200": 5510, "sp500_vs_200dma": 1.06,
    "high_target_pre_tilt": 0.13
  },
  "decision": {"high_target": 0.105, "delta_pp": -2.5, "excluded": ["SMCI"], "reallocated_to": "low"},
  "horizon_weeks": 12,
  "evaluate_after": ["2026-11-02", "2026-12-28"],
  "shadow_link": "state/shadow.json#2026-10-05",
  "status": "open",

  "situation_text": "[상황] 2026-10, 레짐 NEUTRAL(+1.2). HY OAS 355bp 4주 +12bp 확대. VIX 17(콘탱고). S&P 200일선 +6%. AI 섹터 11/5 규제 이벤트 리스크. PLTR 크라우딩.\n[판단] PM 고위험 13%→10.5% 방어 틸트, SMCI 제외.",
  "situation_vector_id": "chroma:sit:...",

  "outcome": null,
  "post_mortem": null,
  "lesson_card": null,
  "lesson_vector_id": null,
  "tags": ["regime:neutral", "sleeve:high", "claim_type:allocation_tilt",
           "action:defensive_tilt", "magnitude:large", "rates_dir:hold",
           "signal:credit_spread_widening"],
  "rag_status": "pending_schema"
}
```

기록 시점: `situation_text` + `situation_vector` + 결정론 태그(regime/sleeve/claim_type/action/magnitude/rates_dir/signal) 확정. **벡터 재계산 불필요** (결과·나머지 태그는 나중에 append).

### 2.3 저장
- 원본: `state/diary/<연도>/<id>.json` (append-only, OMV 볼륨, git-ignored)
- Phase 3a부터 모든 에이전트 출력이 `status: open` 항목으로 자동 기록 (채점은 Phase 4 가동 시)

---

## 3. 단계 ② 채점 — 결정론 파이썬 (`aegisvest/diary/evaluate.py`)

### 3.1 job
주간 별도 cron. `evaluate_after` 최근 날짜 ≤ today 인 `open` 항목을 `claim_type`별 규칙으로 채점.

### 3.2 채점 루브릭 (예시)

**`allocation_tilt`**
```
tilt_contribution_pp = shadow_b_return − shadow_a_return          (해당 기간)
score   = clip(round(tilt_contribution_pp / 0.5), -2, +2)
verdict = hit(score≥+1) | miss(score≤-1) | partial | inconclusive
attribution = high  if |슬리브 변동| > 노이즈 임계 AND 방향 일치
              low   otherwise
```

**`exclusion`**
```
excess = 제외종목_수익률 − 카테고리_중앙값_수익률   (horizon)
score  = clip(round(-excess / 0.05), -2, +2)         # -10% 루저 회피=+2, +10% 위너 놓침=-2
```

**`event_risk`**
```
occurred     = 이벤트 실제 발생?  (NewsScraper 확인, 0/1)
moved_as_pred = 예측 방향·크기 버킷 일치?
score: 무산+무영향 → -1 (늑대소년) | 발생+예측대로 → +2 | 발생+반대 → -2
```

**`regime_call`**
```
4주 예비: 예측 레짐이 유지됐나 (부분 점수)
12주 최종: 전체 기간 레짐 경로 + watch_item 발동 여부
```

나머지 claim_type도 동일 형식의 정량 규칙. **점수·verdict·attribution은 100% 파이썬.**

> **⚠️ 4-1 구현 결정 (2026-09-01) — `aegisvest/diary/evaluate.py`.** 명세의 4개 예시
> 루브릭을 현재 스키마·인프라 한계 내에서 구현하며 3계열로 정리:
> - **섀도 델타 계열** (`allocation_tilt`/`cio_override`/`risk_veto`/`sleeve_stance`):
>   `state/shadow.json` 의 organization − deterministic NAV 수익률 차 (0.5%p/점). 이 4개는
>   전부 "조직 재량이 도움됐나" 질문이고 섀도 A/B 가 바로 그 답이라 재사용.
> - **초과수익 계열** (`exclusion`/`catalyst`): 종목 수익률 vs **SPY 벤치마크** (±10%→±2점).
>   정확한 "카테고리 중앙값" 은 시점별 스코어링 재구성 필요 → 3a-11 백테스트와 동일 이유로
>   프로토타입 단계 미지원, Sharadar 도입 시 정밀화.
> - **`regime_call`**: `regime_history.json` 궤적이 예측 레짐 부호와 맞은 날 비율.
>   4주 예비 채점은 생략, 12주 최종에서 1회만 채점 (스키마에 preliminary outcome 없음).
> - **`event_risk`**: EventRisk 스키마에 예측 방향 필드가 없어, SPY 변동폭이 severity 임계
>   (low 2% / medium 3.5% / high 5%) 이상인지로 "발생" 근사. attribution 은 항상 `low`.
>   방향 검증하려면 EventRisk/ThematicNote 에 `predicted_direction` 추가 필요 (후속).
> - 임계 상수(0.5%p, ±10%, severity 임계)는 실데이터 축적 후 튜닝 (4-6). 지금은 배관 검증.

### 3.3 채점 후
- `status: evaluated`, `outcome` 필드 채움
- Reviewer 큐 진입 조건: `verdict ∈ {miss, partial}` **또는** `attribution == low` **또는** 무작위 샘플링된 `hit` (RAG가 실패만 담지 않도록)
- 채점 불가 (데이터 결측 등) → `status: expired`, base-rate 통계 제외

---

## 4. 단계 ③ 반성 — ⑨ Performance Reviewer (LLM)

### 4.1 산출물
```json
"outcome": {
  "evaluated_at": "2026-12-28", "verdict": "hit", "score": 1, "attribution": "high",
  "what_happened": "AI 규제안 통과(12/3), 고위험 -18%. 틸트로 -1.1%p 선방. HY OAS 355→470"
},
"post_mortem": {
  "root_cause": null,
  "lesson": "HY OAS 상승 추세 + 섹터 특정 규제 헤드라인 겹칠 때 방어 틸트 유효",
  "base_rate_note": "유사 셋업(규제 공포) 과거 3건 중 2건 hit, 1건 miss(규제 무산)",
  "what_would_change": "News Analyst가 CPI/PPI 서프라이즈를 event_risk 후보로 승격"
},
"lesson_card": "[HYspread↑·섹터규제·high] 방어 틸트 유효(-1.1%p). 조건: HY OAS 상승추세+규제헤드라인",
"tags": [... + "event:regulation", "theme:ai_software", "mistake:none"]
```

### 4.2 사후확신 편향 방지 (프롬프트 핵심)
- Reviewer 입력 = `data_snapshot` + **판단일 당일·이전** 뉴스 헤드라인 + `outcome`. 하인드사이트 내러티브 미제공.
- 강제 구조: "당시 가용했으나 놓친 신호: ___ (인용). 저평가한 이유: ___. 수정 휴리스틱: ___"
- "더 신중했어야" 등 구체 신호 없는 출력 반려. `no_fabricated_numbers` 가드레일 적용.
- `lesson_card` ≤ 25 토큰 강제.

### 4.3 RAG 진입 게이트 (K)
```
rag_status:
  auto           → 자동 진입 (소형 exclusion, catalyst, event_risk, risk_veto)
  pending_review → 인간 확인 대기 (allocation_tilt magnitude≥large, regime_call, crisis_shift, cio_override)
  approved       → 인간 승인 완료
  retired        → 검색 제외 (이력 보존)
```
회상은 `auto` + `approved` 만 대상.

> **⚠️ 4-2 구현 결정 (2026-09-01) — `aegisvest/diary/reviewer.py` + `agents/crew.run_reviewer`.**
> - **하인드사이트 방지**: Reviewer 입력은 항목의 **기록 시점** 필드(`claim`/`reasoning`/
>   `supporting_refs`/`data_snapshot`/`situation_text`/`decision`) + 채점 수치(`outcome`)뿐.
>   NewsScraper 툴은 **주지 않는다** — 오늘 RSS 헤드라인은 사후정보라 §4.2 목적과 정면 배치.
>   "판단일 당일·이전 뉴스" point-in-time 인용은 Sharadar 도입 시 (3a-11 보류와 같은 근거).
> - **강제 구조**는 `ReviewerOutput` 필드로: `missed_signal`(인용, 없으면 `none: <이유>`) /
>   `underestimated_because` / `what_would_change`. `missed_signal`·`what_would_change` 가
>   8자 미만이거나 모호어("신중","조심","주의"…) 포함 시 폐기 대신 **`rag_status=pending_review`
>   강등** + `post_mortem.flags` 기록 (거버넌스 CLI 가 검토). `no_fabricated_numbers`
>   는 `hedge_only=True` (①②③ 와 동일 — 기록 텍스트 인용이라 수치 대조 불가).
> - **`lesson_card` ≤ 25 토큰**: 공백어수·문자수(토큰≈2-3자) 이중 상한 근사로 절삭.
>   정밀 토크나이저는 4-6 튜닝.
> - **게이트**: `pending_review` = `claim_type ∈ {regime_call, cio_override}` **또는**
>   `action:crisis_shift` 태그 **또는** (`allocation_tilt` **그리고** `magnitude:{large,structural}`).
>   그 외 `auto`. "소형 exclusion" 의 크기 구분은 exclusion 에 magnitude 태그가 없어 미적용
>   (전부 auto). `mistake:none` 태그는 검색 신호가 없어 저장 생략 (실제 mistake 만 태깅).
> - **status 전이**: `evaluated` → `reflected`(반성함) / `gated`(needs_reflection 아님 — 상황벡터만
>   RAG 진입). 둘 다 종결. 채점(evaluate.py) 과 별도 cron: `evaluate && reviewer` 체이닝.

---

## 5. 단계 ④ 벡터화·저장

### 5.1 이중 벡터 (N-D)

| 벡터 | 임베딩 텍스트 | 생성 시점 | 컬렉션 |
|---|---|---|---|
| **situation 벡터** | `situation_text` (`[상황]+[판단]`, ≤350토큰) | 기록 시 (결과 전) | `diary_situations` |
| **lesson 벡터** | `post_mortem.lesson` + `lesson_card` + `event/theme/mistake` 태그를 문장화 | 반성 시 | `diary_lessons` |

- ChromaDB 컬렉션 2개, 공유 키 = 항목 `id`, 메타데이터(태그·outcome·regime·sleeve·created_at) 양쪽 미러
- lesson 벡터는 반성 완료 후에만 존재 → 콜드 스타트 초기엔 situation 검색만 작동 (정상)
- inconclusive hit (전체 post_mortem 없음) → lesson 벡터 없음, situation 벡터만 (교훈 검색 가치 낮으므로 무방)
- 벡터는 각각 1회 생성, 재계산 없음

### 5.2 인프라
- **ChromaDB** `PersistentClient(path="state/chroma")` — 임베디드, 새 컨테이너 없음, ARM64 OK
- **bge-m3** 로컬, 같은 컨테이너 내. RK3588 CPU 1건 ~1–3초, 연 ~200건 임베딩 = 무부담
- 검색 품질 약하면 `bge-reranker-v2-m3` 크로스 인코더 추가 (top-40 → 재랭킹) — 옵션

> **⚠️ 4-3 구현 결정 (2026-09-01) — `aegisvest/diary/rag.py`.**
> - **situation 벡터를 기록 시가 아니라 주간 백필 시 생성.** `situation_text` 는 기록 후
>   불변이라 임베딩 시점 무관하고, 회상 자격(`rag_status ∈ {auto, approved}`)은 채점·게이트
>   후에야 성립하므로 기록 시점 색인은 실익 없음. 주간 크루 실행 중 bge-m3(2.3GB) 로드도 회피.
>   `python -m aegisvest.diary.rag` (cron: `evaluate && reviewer && rag`).
> - **색인 자격**: `rag_status ∈ {auto, approved}` **그리고** `status ∈ {reflected, gated}`.
>   `evaluated`(채점됐으나 미반성 — DeepSeek 잔액 림보) 는 reflected/gated 로 이동 후 색인.
>   `retired` → 양쪽 컬렉션에서 삭제.
> - **lesson 벡터 텍스트** = `post_mortem.lesson` + `lesson_card` + `{event,theme,mistake,signal}`
>   태그 문장화. `lesson` 없으면 lesson 벡터 미생성 (situation 만).
> - ChromaDB `hnsw:space=cosine`, 메타데이터에 태그(공백 join)·outcome·regime·sleeve 미러.
>   배치 임베딩 (situation 일괄 → lesson 일괄), `_embed` 개수 불일치 시 중단.

---

## 6. 단계 ⑤ 회상 — `DiaryRAG.recall()`

### 6.1 호출 시점
판단 에이전트(①②③⑤⑥⑦) 실행 전, 관련 과거 사례를 태스크 컨텍스트에 주입.

### 6.2 쿼리 구성
- `recall` 래퍼가 현재 상황 문자열 1개 생성: "레짐 NEUTRAL, HY OAS 355bp 4주 +12bp, VIX 17, AI 규제 헤드라인, PLTR 크라우딩, 고위험 방어 틸트 검토"
- bge-m3로 **1회 임베딩** → 두 컬렉션 모두 검색 (bge-m3 단일 공간이므로 동일 쿼리 벡터로 situation·lesson 양쪽 비교 가능)
- `situation_tags` = 현재 `data_snapshot`에 **동일한 결정론 태그 엔진** 적용 (`signal_rules` 등). `event/theme` 는 이번 run의 News/Thematic Analyst 출력에서 취득. LLM 불필요.

### 6.3 검색·랭킹 (Q-D + O-A)
```
recall(query_text, situation_tags, k=4):
  q = embed(query_text)                                   # bge-m3, 1 vector
  cand = chroma.diary_situations.query(q, n=40)
       ∪ chroma.diary_lessons.query(q, n=40)              # 메타 필터 없음
  for c in cand:
    structural = 0.5·(|{claim_type,sleeve,regime} 교집합|/3)
               + 0.5·jaccard({signal,event,theme}_q, {signal,event,theme}_c)
    recency    = max(exp(-months_since(c.evaluated_at or c.created_at)/18),
                     0.15 if 'regime:crisis' in c.tags else 0)
    c.rank     = 0.65·cosine(q, c.vec) + 0.20·structural + 0.15·recency
  cand = dedupe_by_entry_id(cand, keep=max rank)
  cand = [c for c in cand if c.cosine ≥ 0.55
                          and not (c.tags.attribution=='low' and c.cosine < 0.62)]
  # 다양성: DB에 crisis + |score|≥2 항목이 있는데 top-k에 없으면 최고 1건 교체
  return top k
```

### 6.4 주입 형식 (P-D)

```
## 판단 일기 — 유사 사례 (참고용, 현재 데이터 우선)

[2026-10 · hit +1 · 유사도 0.81 · 상황매치]
상황: NEUTRAL, HY OAS 355(+12bp/4주), VIX 17, AI 규제 헤드라인, PLTR 크라우딩
판단: PM 고위험 13%→10.5% 방어 틸트, SMCI 제외
결과: 규제안 통과, 고위험 -18%, 틸트 -1.1%p 선방
교훈: HY OAS 상승추세 + 섹터 규제 겹칠 때 방어 유효 (과거 3건 중 2건 hit)

· [2025-07 miss-1 | vix_spike·high]  단발 VIX 스파이크 컷 → V자 반등 -4%p. 콘탱고 유지 시 컷 아님
· [2024-03 hit+2 | breadth↓·bear·alloc]  브레드스 40↓+하락 시 저위험 상향 유효

⚠️ 참고용. 현재 데이터가 우선. 상황이 다를 수 있으니 맹신 금지.
```

- top-1 (코사인 ≥ 0.75): 중간 요약 ~120토큰
- 나머지 (k−1건): `lesson_card` ≤ 25토큰
- 총 ~350–450 토큰/에이전트. 전체 문단 주입 대비 ~3배 절감. **툴 호출 없음** → DeepSeek 툴콜 리스크 0.
- 검색 시점 LLM 호출 0 (카드는 사전 생성분 이어붙이기)

> **⚠️ 4-4 구현 결정 (2026-09-01) — `aegisvest/diary/rag.py` + `agents/{crew,organization}.py`.**
> - **단일 회상, ①②③⑤⑥⑦ 공용.** §6.2 는 event/theme 를 애널리스트 출력에서 취득하나
>   회상은 그 전(§6.1)이라 모순 → `build_query` 는 스냅샷 기반 signal·regime 태그만 사용
>   (claim_type/sleeve 는 "현재 상황"엔 없어 제외). ①②③(매크로만) → ⑤⑥⑦(강화) 2단계
>   회상은 4-6.
> - **주입 = `extra_desc` append** (tasks.yaml 플레이스홀더 미사용). ④ News·⑧ CIO·⑨ Reviewer
>   제외. 회상 블록의 수치(채점 결과 + 파이썬 lesson_card)는 `no_fabricated_numbers`
>   `extra_allowed` 로 통과 — fabrication 이 아니라 결정론 생성분.
> - **랭킹 순서**: Q-D(top-40×2) → O-A rank 계산 → **entry_id dedupe(max rank)** →
>   floor(0.55)·attribution 게이트(low 는 코사인 < 0.62 제외) → crisis 다양성(|score|≥2).
> - **`format_recall` top-1** = `[월·verdict±score·유사도]` + 원문 120토큰 절삭 (스펙 예시의
>   상황/판단/결과/교훈 4줄 템플릿은 4-6 폴리시). `clip_tokens` 는 `diary.schema` 공용.
> - **콜드 스타트**: 두 컬렉션 모두 비면 임베딩 없이 즉시 `[]`. RAG 오류도 크루 중단 안 함.

### 6.5 O-D 전환 경로 (추후)
- 조건: 채점 완료 항목 ≥ ~150건 + "회상 유용성" 신호 확보 (해당 사례가 회상된 run의 shadow-B − shadow-A 델타 개선 상관)
- 방법: `[cosine, structural, recency, attribution, claim_type_match, age]` 피처로 로지스틱 회귀 → 학습 가중이 고정 `0.65/0.20/0.15` 대체. 분기 재학습.
- 고정 가중은 폴백으로 유지.

---

## 7. 태깅 전략 (상세)

### 7.1 통제 어휘 — `config/diary_taxonomy.yaml`

```yaml
# ── CLOSED: enum 강제, 검색 구조매칭에 사용 ──
regime:      [bull, neutral, bear, crisis,
              bull_to_neutral, neutral_to_bear, bear_to_neutral, neutral_to_bull]
sleeve:      [low, mid, high, allocation, cash]
claim_type:  [regime_call, sleeve_stance, allocation_tilt, exclusion,
              event_risk, catalyst, risk_veto, cio_override]
action:      [defensive_tilt, offensive_tilt, exclusion, hold, crisis_shift, catalyst_bet, veto]
outcome:     [hit, miss, partial, inconclusive]
magnitude:   [minor, moderate, large, structural]     # <1pp / 1-2pp / >2pp / 슬리브 on-off
rates_dir:   [hiking, hold, cutting]
attribution: [high, low]
mistake:     [missed_leading_signal, overreacted_to_news, anchoring, crowding_blindspot,
              premature_exit, stale_thesis, ignored_base_rate, over_hedged, none]

# ── SEMI-OPEN: 큐레이션, 거버넌스로 확장 ──
signal:  [credit_spread_widening, credit_spread_tightening, yield_curve_inversion,
          yield_curve_resteepening, vix_spike, vix_term_backwardation,
          breadth_deterioration, breadth_thrust, momentum_break, golden_cross, death_cross,
          earnings_revision_down, earnings_revision_up, dollar_strength, dollar_weakness]
event:   [fomc, cpi_surprise, ppi_surprise, jobs_report, regulation, antitrust, tariff,
          geopolitical, election, bank_stress, sovereign_stress, earnings, guidance_cut,
          fda_decision, product_launch, index_rebalance]
theme:   [ai_infra, ai_software, semis, biotech, glp1, clean_energy, nuclear, space,
          quantum, fintech, crypto_adjacent, defense, rate_sensitive, defensives]

# ── 결정론 태그 규칙: snapshot 조건 → signal 태그 ──
signal_rules:
  credit_spread_widening:   "hy_oas_4w_change_bp >= 10"
  credit_spread_tightening: "hy_oas_4w_change_bp <= -10"
  vix_spike:                "vix_1d_change_pct >= 0.25"
  vix_term_backwardation:   "vix > vix3m"
  breadth_deterioration:    "pct_above_200dma < 40 and pct_above_200dma_4w_change < 0"
  breadth_thrust:           "pct_above_200dma_4w_change >= 20"
  yield_curve_inversion:    "yc_10y_3m_bp < 0"
  yield_curve_resteepening: "yc_10y_3m_4w_change_bp >= 15 and yc_10y_3m_prev_bp < 0"
  death_cross:              "sma50 < sma200 and sma50_prev >= sma200_prev"
  golden_cross:             "sma50 > sma200 and sma50_prev <= sma200_prev"

max_tags_per_entry: 8
similarity_floor: 0.55
recency_halflife_months: 18
```

태그는 `차원:값` 네임스페이스.

### 7.2 태그 부여 — 결정론 70% / LLM 30%

| 시점 | 태그 | 방법 |
|---|---|---|
| 기록 시 (파이썬) | `regime` `sleeve` `claim_type` `action` `magnitude` `rates_dir` | data_snapshot·decision 직접 |
| 기록 시 (파이썬) | `signal:*` | `signal_rules` 조건식 평가 |
| 채점 시 (파이썬) | `outcome` `attribution` | evaluate.py |
| 반성 시 (Reviewer LLM) | `event:*` `theme:*` `mistake:*` + `signal:*` 보완 | 뉴스 읽기·분류·원인 판단 필요분만 |

### 7.3 태그의 검색 역할
- **구조매칭 점수** (O-A의 0.20 항): `{claim_type, sleeve, regime}` 교집합 + `{signal, event, theme}` Jaccard
- 메타데이터 하드 필터로는 **안 씀** (Q-D — 캐스케이드 없음). 태그는 배제가 아닌 부스트.
- 쿼리 시점: 현재 상황을 동일 결정론 엔진으로 태깅 → 구조매칭 계산

### 7.4 태그 위생
- CLOSED: 스키마가 미지값 거부
- SEMI-OPEN: Reviewer가 YAML에서 선택. 신규값 → `state/diary/pending_tags.json` 기록, 분기 검토 전까진 작동하되 플래그
- 항목당 최대 8 태그
- deprecated → alias 테이블로 canonical 매핑

---

## 8. 거버넌스

`python -m aegisvest.diary review` — 분기 1회:
- 가장 많이 회상된 교훈 top 20 + 각 base rate
- `pending_review` 큐 (대형 틸트·위기·레짐 콜의 post_mortem) → 승인/수정/은퇴
- `pending_tags.json` 신규 태그 검토
- 신규 교훈이 기존 고신뢰 교훈과 충돌 → Reviewer가 플래그한 목록

> **⚠️ 4-5 구현 결정 (2026-09-01) — `aegisvest/diary/governance.py` + `__main__.py`.**
> - `report_text()` = pending_review 큐 + 신규 SEMI-OPEN 태그 + top-20 회상 교훈(+claim_type
>   base rate). 회상 빈도는 `rag._log_recall` 가 `state/diary/recall_log.jsonl` 에 주간 append.
> - 액션 플래그: `--approve` (→approved), `--retire` (→retired), `--edit --lesson` (+`--lesson-card`),
>   `--ack-tags` (pending_tags.json 비움). RAG 재색인은 다음 `python -m aegisvest.diary.rag`
>   배치 (거버넌스 CLI 가 bge-m3 를 로드하지 않음). taxonomy YAML 편입은 수동.
> - **교훈 충돌 탐지는 미구현** — 교훈 임베딩 간 유사도 비교가 필요해 4-6 으로. 지금은
>   `post_mortem.flags` (4-2 모호성 플래그)만 표시.

---

## 9. 콜드 스타트 & 실패 모드

| 문제 | 대응 |
|---|---|
| 콜드 스타트 (0~3개월) | 일기 빔 → `recall()` 무반환, 기본 지능 작동. Gate B 12개월 관찰과 겹쳐 무방 |
| 3~12개월 (얇은 일기) | 유사도 하한 0.55 → 약한 매치는 무반환 (엉뚱한 교훈 방지) |
| 최근 miss 과적합 | `base_rate_note` 항상 포함, 최근성 감쇠 하한, 위기 항목 상시 후보, 분기 인간 검토 |
| 일기 오염 (나쁜 반성 전파) | 고임팩트 판단은 `pending_review` → 인간 확인 후 진입 |
| 귀인 문제 (실력 vs 운) | `attribution: low` → score 크기 축소 + 회상 자격 강화(코사인 ≥ 0.62). 다건 누적 시 운은 평균회귀 |
| 일기 생존 편향 | `expired` 항목은 보존하되 base-rate 제외. expired 과다 → 채점 규칙 수정 신호 |

---

## 10. 빌드 순서

| # | 산출물 | 선행 조건 |
|---|---|---|
| 1 | 일기 스키마 + logger (`diary/schema.py`, `diary/logger.py`) | Phase 3a에 포함 |
| 2 | `diary/evaluate.py` (결정론 채점, claim_type별 루브릭) | 모의투자 ~3개월 + 섀도 A/B 데이터 |
| 3 | ⑨ Performance Reviewer 에이전트 (post_mortem + 태깅 + lesson_card) | 2 |
| 4 | `diary/rag.py` (bge-m3 이중 벡터 + ChromaDB, 기존 채점 항목 백필) | 3 |
| 5 | `DiaryRAG.recall()` + 에이전트 주입 (Q-D 검색, O-A 랭킹, P-D 포맷) | 4 |
| 6 | `diary review` CLI (거버넌스) | 5 |
| 7 | 튜닝 — 유사도 하한·반감기·k. **RAG on/off 섀도 A/B로 측정** | 5 |
| 8 | (추후) O-D 학습형 가중 | 채점 항목 ≥ ~150 |

**cron 추가** (`docker-compose.yml` configs 인라인 crontab):
```cron
# 월요일 23:00 KST — 판단 일기 채점(결정론) → 반성(⑨ Reviewer LLM) → RAG 색인 배치 (크루·감시견과 분리)
0 23 * * 1  flock -n /tmp/eval.lock sh -c 'python -m aegisvest.diary.evaluate && python -m aegisvest.diary.reviewer && python -m aegisvest.diary.rag'
```

**의존성 추가**: `chromadb`, `FlagEmbedding` (또는 `sentence-transformers`), bge-m3 가중치 (이미지 빌드 시 다운로드 또는 볼륨 캐시).

---

## 11. 명세 단계 종료

Phase 1~4로 구상(명세) 단계 완료. 개발은 Phase 3 §9 빌드 순서(3a-1 스캐폴딩)부터 착수하며, 각 단계에서 `report/` 를 단일 근거로 참조한다.

| Phase | 문서 | 범위 |
|---|---|---|
| 1 | phase-1-conception.md | 리스크 3티어(A), 동적 배분(B), 조직 원안(C→Phase 3 대체), Claude Code 설정(D) |
| 2 | phase-2-macro-and-rebalancing.md | 레짐 판별, 슬라이드 배분, 리밸런싱, 현금흐름 리밸런싱, OMV8 배포, 성공 게이트, 알림, 백테스트 데이터 |
| 3 | phase-3-organization-and-paper-trading.md | 9-에이전트 조직, 재량 한계(B), 백테스트↔조직 분리(C), 모니터링, PaperBroker, 소액 포트, 빌드 단계 |
| 4 | phase-4-judgment-diary-rag.md | 판단 일기 RAG — 기록·채점·반성·태깅·이중벡터·회상, ChromaDB/bge-m3 |
