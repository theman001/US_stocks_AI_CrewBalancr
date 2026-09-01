# TOOLS.md — Layer 0 결정론 툴 인터페이스 계약

> 이 문서가 툴 I/O의 **단일 근거**. 구현 전 `report/phase-1-conception.md` D-5,
> 관련 Phase 절, 그리고 `.claude/skills/add-tool` 을 읽어라.

## 공통 규칙
- 툴은 **순수 파이썬 함수** `def <name>(...) -> <Model> | ToolError`. CrewAI `BaseTool`
  래퍼는 3a-9에서 추가 (`.model_dump()`). 결정론 코어·백테스트는 함수 직접 호출.
- **예외 raise 금지.** 실패 시 `ToolError(error=..., field=...)` 반환.
- 성공 시 Pydantic 모델 (`aegisvest/schemas.py`). 아래 스키마의 **모든 필드**, 없는 값은 `None`.
- 파생 지표는 **툴이 계산해서** 반환 (호출자에 계산 떠넘기지 말 것).
- 네트워크 호출은 `aegisvest/tools/_io.py` 캐시 헬퍼 경유 (TTL `CACHE_TTL_HOURS`, 기본 24).
- `as_of` (YYYY-MM-DD) 포함. 발표 지연 데이터는 `stale_fields: list[str]`.
- 결정론적: 같은 입력 → 같은 출력. 아래 `Output:` 표기는 모델 필드.

---

## 1. MarketDataTool
가격·거래량·이동평균·베타·기술지표. 이력은 항상 5년 조회 (60개월 베타 커버).
```
Input:  ticker: str
Output: {
  "ticker": str, "last_price": float, "sma_50": float, "sma_200": float,
  "sma_50_prev": float, "sma_200_prev": float,
  "rsi_14": float, "atr_14": float, "beta_60m": float,
  "adv_20d_usd": float, "rs_vs_spx_6m": float,        # 백분위 0~100
  "mom_12_1": float, "pct_from_52w_high": float,
  "vol_20d_avg": float, "vol_ratio_latest": float,     # 최근/20일평균
  "as_of": "YYYY-MM-DD"
}
```
소스: yfinance → FMP 폴백. 지표는 pandas-ta.

## 2. FundamentalsTool
재무제표 기반 지표.
```
Input:  ticker: str
Output: {
  "market_cap_usd": float, "pe_forward": float, "pe_ttm": float,
  "pe_5y_median": float, "ev_ebitda": float, "peg_forward": float,
  "roe_5y_avg": float, "roic": float, "wacc_est": float,
  "gross_margin": float, "op_margin_trend_3y": "rising|flat|falling",
  "rev_cagr_3y": float, "eps_growth_fwd": float, "eps_revision_3m": "up|flat|down",
  "fcf_ttm_usd": float, "fcf_payout": float, "eps_payout": float,
  "net_debt_ebitda": float, "interest_coverage": float,
  "div_streak_years": int, "dgr_5y": float, "div_yield": float, "div_yield_5y_median": float,
  "piotroski_f": int, "altman_z": float, "rule_of_40": float,
  "eps_positive_years_10": int, "credit_rating": str, "sector": str,
  "as_of": "YYYY-MM-DD"
}
```
소스: FMP. 계산 지표(F-score, Z-score, Rule of 40, PEG, WACC)는 툴이 산출.

## 3. MacroDataTool
레짐 6축 raw 데이터.
```
Input:  {}
Output: {
  "vix": float, "vix3m": float, "vix_1d_change_pct": float,
  "spx_last": float, "spx_sma_200": float, "spx_sma_50": float, "spx_50_slope_20d": float,
  "pct_above_200dma": float, "pct_above_200dma_4w_change": float,
  "yc_10y_3m_bp": float, "yc_10y_3m_4w_change_bp": float, "yc_10y_3m_prev_bp": float,
  "yc_10y_2y_bp": float, "fed_funds_trend": "hiking|hold|cutting",
  "hy_oas_bp": float, "hy_oas_4w_change_bp": float,
  "wei": float, "regional_fed_mfg_avg": float, "claims_4w_trend_pct": float,
  "ism_pmi": float | None,                              # MANUAL_ISM_PMI 우선
  "as_of": "YYYY-MM-DD", "stale_fields": [str]
}
```
소스: FRED (`VIXCLS` `T10Y3M` `BAMLH0A0HYM2` `WEI` `IC4WSA` `UNRATE` 등) + yfinance
(`^VIX` `^VIX3M` `^GSPC`). 지역연준: Empire/Philly/Dallas/KC/Richmond 평균.
시장 폭은 구성종목 가격에서 직접 계산.

## 4. RegimeScoreCalculator  → `regime_score(macro, history, crisis_state) -> RegimeResult`
```
Input:  macro: MacroData
        history: list[RegimeHistoryPoint]  (감시견이 state/regime_history.json 에 누적)
        crisis_state: CrisisState  (직전 래치 상태, 감시견이 persist)
Output: RegimeResult {
  axis_scores: {vix, spx_trend, breadth, yield_policy, credit, economy}  # 각 -2~+2 또는 None
  economy_subscores: {wei, regional, claims}                             # 각 -2~+2 또는 None
  n_axes_present: int
  low_confidence: bool          # present < min_axes_for_label(4) → 라벨 NEUTRAL 강등
  total_score: int              # -12~+12, present 축 합 * 6/n_present 정규화 후 clamp
  score_smooth: float           # 5일 EMA (adjust=False)
  regime: BULL|NEUTRAL|BEAR|CRISIS
  crisis_active: bool, crisis_reason: str | None
  crisis_state: CrisisState     # 갱신본 — 호출자(감시견)가 persist
  rationale: {axis: "임계값 대입 설명"}
}
```
임계값은 `config/regime_rules.yaml` (Pydantic 검증: `aegisvest/rules.py`). **LLM 관여 0.**
감시견(3a-4)이 매일 호출하고 `total_score` 를 history 에 append (단 `low_confidence` 인 날 제외).
보간 앵커는 AllocationTableTool(§5) 소관 — 레짐 계산기엔 없음.

## 5. AllocationTableTool  → `allocation_targets(score_smooth, nav_usd=0, *, crisis=False, mode="paper") -> AllocationTargets | ToolError`
```
Output: AllocationTargets {
  score_smooth, crisis, equity_sleeve_pct, cash_pct,
  category_targets_sleeve: {low, mid, high},   # 슬리브 100 기준 소수
  category_targets_total:  {low, mid, high},   # 전체 포트 기준 소수
  max_positions: {low, mid, high},             # mode=paper → 20/15/15, live → nav_tiers
  interp_anchors: [int, int],                  # 보간에 쓴 상·하 정수 앵커
  guardrails: {...}                            # config/allocation.yaml guardrails
}
```
`config/allocation.yaml` (score→[low,mid,high,sleeve,cash] 앵커, nav_tiers, guardrails).
앵커 사이 선형 보간. `crisis=True` → -12 앵커 스냅. 고위험 절대 상한 20% 강제.
근거: report/phase-2 §2.2.

## 6. ScreenerTool  → `screen(category, universe="combined", limit=None) -> ScreenResult | ToolError`
```
Output: ScreenResult {
  category, passed: [ScreenedTicker{ticker, passed, checks: {name: {result, value}}, subtier}],
  failed_count, evaluated_count, errored: [str], as_of
}  # check.result: pass | fail | skip
```
`config/filters/{low,mid,high}.yaml`. `_screen.merged_values()` 가 fundamentals + market_data 병합.
HIGH 는 통과 후보군 내 RS 상위 30% 추가 컷. `limit` 은 레이트리밋 대응(무료 데이터 느림).
소스: yfinance (FMP 무료 티어 종목 제한으로 전환, 2026-09).

## 7. ScoringCalculator  → `score_category(category, tickers, theme_strength_overrides=None) -> ScoringResult | ToolError`
```
Output: ScoringResult { category, scores: [ScoredTicker{ticker, score(0~100), rank, subtier,
        component_scores: {name: float}}], errored, as_of }  # scores 는 score 내림차순
```
`config/scoring/{category}.yaml` (components/weights/directions/subtiers). 후보군 내 percentile
rank 정규화 → direction 적용 → component 평균 → weight 가중합 ×100. 결측 metric 은 중립 0.5.
`theme_strength` 는 `llm_fed` — Thematic Analyst(3b) 가 `theme_strength_overrides` 로 주입.

### 7.1 market_breadth  → `market_breadth(tickers) -> dict | ToolError`
`{pct_above_200dma (%), pct_above_200dma_4w_change (%p), n, as_of}`. 3a-8 파이프라인이
유니버스로 호출해 `MacroData.pct_above_200dma` 를 패치 → 레짐 breadth 축 활성화.

### 7.2 get_universe  → `get_universe(name="combined") -> list[str]`
`config/universe/{sp500,nasdaq100}.txt` 정적 명단 (FMP 구성종목 엔드포인트 프리미엄).

## 8. CashFlowRebalancer  → `cash_flow_rebalance(targets_total, current_category_usd, cash_usd, pending_contribution_usd=0, cooldown_state=None, *, crisis=False) -> RebalancePlan | ToolError`
```
Output: RebalancePlan {
  new_cash_deployable_usd,
  buys_from_new_cash: [RebalanceOrder{category, amount_usd}],
  sell_needed: bool, sell_orders: [RebalanceOrder],
  cooldown_blocked: [str],                       # 쿨다운으로 조정 못 한 카테고리
  post_action_weights: {low, mid, high, cash}
}
```
report/phase-2 §3.3 ①: (1) 가용 현금(입금 + 현금-하한)으로 부족 카테고리 매수 (상대
부족률 큰 순) → (2) 그래도 밴드 밖(±4%p / ±25%)인 과대 카테고리 매도. 쿨다운 10거래일
(CRISIS 예외), 1회 변동 상한 10%p. `current_category_usd`: 카테고리별 보유 평가액(USD).

## 9. ConstraintChecker  → `check_constraints(draft: DraftPortfolio) -> ConstraintResult`
```
DraftPortfolio { category_weights: {low, mid, high, cash}, positions: [Position{ticker,
  category, weight, sector}], prior_category_weights: {...} (선택) }
ConstraintResult { verdict: "PASS"|"FAIL", violations: [{rule, detail, value}] }
```
하드 가드레일: high_abs_cap(20%), single_name_cap(8%), sector_cap(30%), cash_floor(3%),
weights_sum(≈1), max_change_per_rebal(prior 있을 때 10%p). ⑦ Risk Officer 강제 실행.
밴드는 리밸런싱 로직(§8) 소관 — 여기선 검증 안 함.

## 10. PortfolioMathTool / PositionSizer
- **PortfolioMathTool**: 가중평균, 노출 집계, 기여도, 주문 수량 산출 — 범용 산술.
  최종 주문의 모든 수량·비중은 여기서 계산.
- **PositionSizer**: 카테고리 예산 내 스코어 가중 배분, 고위험 ATR 기반, 단일종목 상한.

## 11. NewsScraperTool
```
Input:  scope: "macro"|"ticker", ticker: str | None, days: int = 7
Output: {"headlines": [{"title": str, "source": str, "published": "YYYY-MM-DD",
                        "url": str, "summary": str}], "as_of": "YYYY-MM-DD"}
```
매크로 헤드라인 + 종목별 뉴스. 소스 미정 (RSS/무료 API). 캐시 필수.
**스크랩만** — 요약·해석은 에이전트.

## 12. (Phase 4) DiaryRAG
`recall(query_text, situation_tags, k) -> list[dict]` — report/phase-4 §6.
ChromaDB 이중 컬렉션 + bge-m3 로컬. 검색 로직 Q-D, 랭킹 O-A, 주입 포맷 P-D.
