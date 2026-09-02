"""판단 일기 채점 — 100% 결정론. report/phase-4 §3 (L 결정: "점수·verdict·attribution 은
100% 파이썬"). 주간 별도 cron (`python -m aegisvest.diary.evaluate`).

evaluate_after 최근 날짜가 지난 `open` 항목을 claim_type 별 정량 규칙으로 채점:
- **섀도 델타 계열** (allocation_tilt/cio_override/risk_veto/sleeve_stance): 조직-결정론
  NAV 수익률 차 — phase-3 섀도 A/B 가 이미 답하도록 설계된 질문이라 재사용.
- **초과수익 계열** (exclusion/catalyst): 종목 수익률 vs SPY 벤치마크. 정확한 "카테고리
  중앙값"은 3a-11 과 같은 이유로(시점별 스코어링 재구성 필요) 프로토타입 단계 미지원 —
  SPY 대비 초과수익으로 근사.
- **regime_call**: `state/regime_history.json` 궤적이 예측 레짐과 부호가 맞은 비율.
- **event_risk**: 예측 방향 필드가 스키마에 없어(EventRisk 에 방향 없음) SPY 변동폭이
  severity 임계 이상인지로 근사 — attribution 은 항상 low (방향 검증 못 하므로 보수적).

result 는 `{verdict, score, attribution, ...detail}` — Reviewer(4-2)가 `outcome.what_happened`
과 `post_mortem`/`lesson_card`를 덧붙인다 (LLM 서술 담당, report/phase-4 §4.1).
"""

from __future__ import annotations

import datetime as dt
import logging
import random

import pandas as pd

from aegisvest.config import get_settings
from aegisvest.diary.logger import diary_lock, load_entries, save_entries
from aegisvest.rules import Label, regime_rules
from aegisvest.schemas import DiaryEntry, NavPoint, RegimeHistoryPoint, ShadowState
from aegisvest.state import load_list, load_model
from aegisvest.tools._prices import history

_log = logging.getLogger("aegisvest.diary.evaluate")

_SHADOW_DELTA_TYPES = frozenset({"allocation_tilt", "cio_override", "risk_veto", "sleeve_stance"})
_EXCESS_RETURN_TYPES = frozenset({"exclusion", "catalyst"})
_SHADOW_DELTA_UNIT = 0.005  # 0.5%p 당 1점 (report/phase-4 §3.2 allocation_tilt 예시)
_EXCESS_RETURN_UNIT = 0.05  # ±10% → ±2점 (§3.2 exclusion 예시)
_EVENT_SEVERITY_THRESHOLD = {"low": 0.02, "medium": 0.035, "high": 0.05}
_REFLECTION_SAMPLE_RATE = 0.15  # hit 중 무작위 샘플 — RAG 가 실패만 담지 않도록 (§3.3)


def _clip(score: int, lo: int = -2, hi: int = 2) -> int:
    return max(lo, min(hi, score))


def _verdict(score: int) -> str:
    if score >= 1:
        return "hit"
    if score <= -1:
        return "miss"
    return "partial"


def _as_dict(v: object) -> dict[str, object]:
    return v if isinstance(v, dict) else {}


def _as_str_list(v: object) -> list[str]:
    return [str(x) for x in v] if isinstance(v, list) else []


# ─────────────────────── 섀도 델타 계열 ───────────────────────


def _nav_at_or_before(hist: list[NavPoint], date: str) -> float | None:
    candidates = [p.nav_usd for p in sorted(hist, key=lambda p: p.date) if p.date <= date]
    return candidates[-1] if candidates else None


def _score_shadow_delta(entry: DiaryEntry, shadow: ShadowState) -> dict[str, object] | None:
    start, end = entry.run_id[:10], entry.evaluate_after[-1]
    det_s = _nav_at_or_before(shadow.deterministic.history, start)
    det_e = _nav_at_or_before(shadow.deterministic.history, end)
    org_s = _nav_at_or_before(shadow.organization.history, start)
    org_e = _nav_at_or_before(shadow.organization.history, end)
    if not (det_s and det_e and org_s and org_e) or det_s <= 0 or org_s <= 0:
        return None
    delta = (org_e / org_s - 1.0) - (det_e / det_s - 1.0)
    score = _clip(round(delta / _SHADOW_DELTA_UNIT))
    return {
        "verdict": _verdict(score),
        "score": score,
        "attribution": "high" if abs(delta) > _SHADOW_DELTA_UNIT else "low",
        "org_minus_det_pct": round(delta, 4),
    }


# ─────────────────────── 초과수익 계열 (exclusion/catalyst) ───────────────────────


def _price_on_or_before(df: pd.DataFrame, date_str: str) -> float | None:
    if df.empty or "Close" not in df.columns:
        return None
    dates = pd.DatetimeIndex(df.index).strftime("%Y-%m-%d")
    mask = dates <= date_str
    if not mask.any():
        return None
    return float(df["Close"].iloc[mask.nonzero()[0][-1]])


def _return_between(ticker: str, start: str, end: str, ttl_hours: float) -> float | None:
    try:
        df = history(ticker, ttl_hours)
    except Exception:  # 상폐·오류 → 채점 불가로 처리
        return None
    px_start, px_end = _price_on_or_before(df, start), _price_on_or_before(df, end)
    if px_start is None or px_end is None or px_start <= 0:
        return None
    return px_end / px_start - 1.0


def _score_excess_return(entry: DiaryEntry) -> dict[str, object] | None:
    decision = _as_dict(entry.decision)
    if entry.claim_type == "exclusion":
        tickers, invert = _as_str_list(decision.get("excluded")), True
    else:  # catalyst
        cats = decision.get("catalysts")
        tickers = (
            [str(c["ticker"]) for c in cats if isinstance(c, dict) and c.get("ticker")]
            if isinstance(cats, list)
            else []
        )
        invert = False
    if not tickers:
        return None
    start, end = entry.run_id[:10], entry.evaluate_after[-1]
    ttl = float(get_settings().cache_ttl_hours)
    rets = [r for t in tickers if (r := _return_between(t, start, end, ttl)) is not None]
    bench = _return_between("SPY", start, end, ttl)
    if not rets or bench is None:
        return None
    excess = sum(rets) / len(rets) - bench
    signed = -excess if invert else excess
    score = _clip(round(signed / _EXCESS_RETURN_UNIT))
    return {
        "verdict": _verdict(score),
        "score": score,
        "attribution": "high" if abs(signed) > _EXCESS_RETURN_UNIT else "low",
        "excess_vs_spy_pct": round(signed, 4),
        "n_tickers": len(rets),
    }


# ─────────────────────── event_risk ───────────────────────


def _score_event_risk(entry: DiaryEntry) -> dict[str, object] | None:
    events = _as_dict(entry.decision).get("events")
    if not isinstance(events, list) or not events:
        return None
    severities = [e.get("severity", "medium") for e in events if isinstance(e, dict)]
    rank = {"low": 0, "medium": 1, "high": 2}
    worst = max(severities, key=lambda s: rank.get(str(s), 1), default="medium")
    threshold = _EVENT_SEVERITY_THRESHOLD.get(str(worst), 0.035)
    start, end = entry.run_id[:10], entry.evaluate_after[-1]
    move = _return_between("SPY", start, end, float(get_settings().cache_ttl_hours))
    if move is None:
        return None
    occurred = abs(move) >= threshold
    score = 1 if occurred else -1  # 발생 증거 있음(+1) / 무산·무영향(늑대소년, -1)
    return {
        "verdict": _verdict(score),
        "score": score,
        "attribution": "low",  # 예측 방향 필드 없어 hit 여부만, 확신도는 항상 low
        "market_move_pct": round(move, 4),
        "occurred_proxy": occurred,
    }


# ─────────────────────── regime_call ───────────────────────


def _normalize_regime(predicted: str) -> str | None:
    """LLM 자유서술(예: 'cautiously bullish') → CRISIS/BEAR/BULL/NEUTRAL. 불명확하면 None."""
    p = predicted.upper()
    for key in ("CRISIS", "BEAR", "BULL", "NEUTRAL"):  # CRISIS·BEAR 우선 (보수적)
        if key in p:
            return key
    return None


def _label_matches(predicted: str, total_score: int, label: Label) -> bool:
    if predicted == "CRISIS":
        return total_score <= label.bear_max  # 위기 래치는 히스토리에 없음 — 약세권 이상으로 근사
    if predicted == "BULL":
        return total_score >= label.bull_min
    if predicted == "BEAR":
        return total_score <= label.bear_max
    return label.bear_max < total_score < label.bull_min  # NEUTRAL


def _score_regime_call(
    entry: DiaryEntry, hist: list[RegimeHistoryPoint]
) -> dict[str, object] | None:
    raw = _as_dict(entry.decision).get("regime")
    if not isinstance(raw, str) or not raw:
        return None
    predicted = _normalize_regime(raw)
    if predicted is None:  # 파싱 불가 → 오채점 대신 expired
        return None
    start, end = entry.run_id[:10], entry.evaluate_after[-1]
    window = [h for h in hist if start <= h.date <= end]
    if not window:
        return None
    label = regime_rules().label
    matches = sum(1 for h in window if _label_matches(predicted, h.total_score, label))
    ratio = matches / len(window)
    score = _clip(round((ratio - 0.5) * 4))
    return {
        "verdict": _verdict(score),
        "score": score,
        "attribution": "high" if ratio >= 0.7 or ratio <= 0.3 else "low",
        "days_matching_ratio": round(ratio, 3),
    }


def _score_entry(
    entry: DiaryEntry, shadow: ShadowState, regime_history: list[RegimeHistoryPoint]
) -> dict[str, object] | None:
    if entry.claim_type == "regime_call":
        return _score_regime_call(entry, regime_history)
    if entry.claim_type in _SHADOW_DELTA_TYPES:
        return _score_shadow_delta(entry, shadow)
    if entry.claim_type in _EXCESS_RETURN_TYPES:
        return _score_excess_return(entry)
    if entry.claim_type == "event_risk":
        return _score_event_risk(entry)
    return None


def needs_reflection(entry: DiaryEntry) -> bool:
    """Reviewer 큐 진입 조건 (§3.3): miss/partial 또는 attribution low, hit 는 15% 표본."""
    outcome = entry.outcome or {}
    if outcome.get("verdict") in {"miss", "partial"} or outcome.get("attribution") == "low":
        return True
    return random.Random(entry.id).random() < _REFLECTION_SAMPLE_RATE  # 게이트 샘플링, 보안 무관


def run(*, today: str | None = None) -> dict[str, int]:
    """`evaluate_after` 도래한 open 항목 채점. 반환은 카운트 요약 (호출자·CLI 공용)."""
    today = today or dt.date.today().isoformat()
    shadow = load_model("shadow.json", ShadowState) or ShadowState()
    regime_history = load_list("regime_history.json", RegimeHistoryPoint)

    counts = {"evaluated": 0, "expired": 0, "not_due": 0, "queued_for_reflection": 0}
    with diary_lock():
        entries = load_entries()
        for entry in entries:
            if entry.status != "open":
                continue
            if not entry.evaluate_after:  # 손상된 항목 — 채점 불가
                entry.status = "expired"
                counts["expired"] += 1
                continue
            if entry.evaluate_after[-1] > today:
                counts["not_due"] += 1
                continue
            result = _score_entry(entry, shadow, regime_history)
            if result is None:
                entry.status = "expired"
                counts["expired"] += 1
                continue
            entry.outcome = {"evaluated_at": today, **result}
            entry.status = "evaluated"
            counts["evaluated"] += 1
            if needs_reflection(entry):
                counts["queued_for_reflection"] += 1

        save_entries(entries)
    return counts


def main() -> None:
    logging.basicConfig(
        level=get_settings().log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    counts = run()
    _log.info("일기 채점 완료: %s", counts)


if __name__ == "__main__":
    main()
