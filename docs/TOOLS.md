# TOOLS.md — Layer 0 결정론 툴 인터페이스 계약

> 이 문서가 툴 I/O의 **단일 근거**. 구현 전 `report/phase-1-conception.md` D-5,
> 관련 Phase 절, 그리고 `.claude/skills/add-tool` 을 읽어라.

## 공통 규칙
- `crewai.tools.BaseTool` 상속. `args_schema` 는 Pydantic (모든 필드 단위 명시).
- **예외 raise 금지.** 실패 시 `{"error": "설명", "field": "필드명"}` 반환.
- 반환은 JSON 직렬화 가능 dict. 아래 스키마의 **모든 키 포함**, 없는 값은 `None`.
- 파생 지표는 **툴이 계산해서** 반환 (에이전트에 계산 떠넘기지 말 것).
- 네트워크 호출은 `data/cache/` 에 TTL 캐시 (`CACHE_TTL_HOURS`, 기본 24).
- `as_of` (YYYY-MM-DD) 포함. 발표 지연 데이터는 `stale_fields: [str]`.
- 결정론적: 같은 입력 → 같은 출력.

---

## 1. MarketDataTool
가격·거래량·이동평균·베타·기술지표.
```
Input:  ticker: str, lookback_days: int = 400
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

## 4. RegimeScoreCalculator
```
Input:  MacroDataTool 출력 dict, history: list[dict] (일별 누적)
Output: {
  "axis_scores": {"vix": int, "spx_trend": int, "breadth": int,
                  "yield_policy": int, "credit": int, "economy": int},   # 각 -2~+2
  "economy_subscores": {"wei": int, "regional_fed": int, "claims": int},
  "total_score": int,                                   # -12~+12
  "score_smooth": float,                                # 5일 EMA
  "regime": "BULL|NEUTRAL|BEAR|CRISIS",
  "crisis_override": bool, "crisis_reason": str | None,
  "interp_anchors": [float, float],                     # 보간에 쓴 상·하 기준점
  "rationale": {axis: "임계값 대입 설명"}
}
```
로직은 `config/regime_rules.yaml`. **LLM 관여 0.** watchdog 이 매일 호출.

## 5. AllocationTableTool
```
Input:  score_smooth: float, nav_usd: float
Output: {
  "equity_sleeve_pct": float, "cash_pct": float,
  "category_targets_sleeve": {"low": float, "mid": float, "high": float},   # 슬리브 100 기준
  "category_targets_total": {"low": float, "mid": float, "high": float},    # 전체 포트 기준
  "max_positions": {"low": int, "mid": int, "high": int},                   # nav_tiers
  "guardrails": {"high_abs_cap": 0.20, "single_name_cap": 0.08,
                 "sector_cap": 0.30, "cash_floor": 0.03,
                 "rebal_band_abs_pp": 4.0, "rebal_band_rel": 0.25,
                 "max_change_per_rebal_pp": 10.0, "cooldown_trading_days": 10},
  "interp_anchors": [float, float]
}
```
`config/allocation.yaml` (보간 앵커, nav_tiers, 가드레일).

## 6. ScreenerTool
```
Input:  category: "LOW"|"MID"|"HIGH", universe: "SP500"|"NASDAQ100"|"combined"
Output: {
  "category": str,
  "passed": [{"ticker": str, "hard_filters": {name: {"value": float, "pass": bool}}}],
  "failed_count": int, "as_of": "YYYY-MM-DD"
}
```
`config/filters/{low,mid,high}.yaml` 임계값. FundamentalsTool/MarketDataTool 배치 호출.

## 7. ScoringCalculator
```
Input:  category: str, tickers: list[str], theme_strength_overrides: dict | None
Output: {"scores": [{"ticker": str, "score": float, "subtier": str,
                     "component_scores": {name: float}, "rank": int}]}
```
`config/scoring/{category}.yaml` 가중치. percentile rank 정규화 후 가중합.
`theme_strength_overrides` 는 Thematic Analyst 피드백 (HIGH 한정, 제한 범위).

## 8. CashFlowRebalancer
```
Input:  targets_total: dict, current_positions: dict, cash_usd: float,
        pending_contribution_usd: float, cooldown_state: dict, guardrails: dict
Output: {
  "new_cash_deployable_usd": float,
  "buys_from_new_cash": [{"category": str, "amount_usd": float}],
  "sell_needed": bool,
  "sell_orders": [{"category": str, "amount_usd": float}] | [],
  "cooldown_blocked": [str],                             # 조정 못 한 카테고리
  "post_action_weights": {"low": float, "mid": float, "high": float, "cash": float}
}
```
report/phase-2 §3.3 ① 규칙. 신규 현금 우선 매수, 밴드 밖일 때만 매도, 쿨다운.

## 9. ConstraintChecker
```
Input:  draft_portfolio: dict
Output: {"verdict": "PASS"|"FAIL", "violations": [{"rule": str, "detail": str, "value": float}]}
```
모든 하드 가드레일 검증 (고위험 20%, 단일종목 8%, 섹터 30%, 현금 하한, 밴드,
1회 변동 상한). ⑦ Risk Officer 단계 강제 실행.

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
