"""일일 감시견 — 위기 감지 + 매크로 점수 누적. LLM 미사용. 근거: report/phase-2 §3.2.

매일:
  1. macro_data() + regime_score() 계산
  2. crisis_state / (low_confidence 아니면) regime_history persist
  3. CRISIS 이면 crisis_flag.json 기록 + Mattermost 알림
     → main.py(3a-10) 가 다음 실행 시 flag 를 읽어 크루를 즉시 실행
  4. 아니면 로그만
"""

from __future__ import annotations

import logging

from aegisvest.config import ensure_runtime_dirs, get_settings
from aegisvest.notify import post
from aegisvest.schemas import CrisisFlag, CrisisState, RegimeHistoryPoint, RegimeResult
from aegisvest.state import load_list, load_model, save_list, save_model
from aegisvest.tools.macro_data import macro_data
from aegisvest.tools.regime import regime_score

_HISTORY = "regime_history.json"
_CRISIS_STATE = "crisis_state.json"
_CRISIS_FLAG = "crisis_flag.json"
_MAX_HISTORY = 40  # EMA span 5 에 충분

_log = logging.getLogger("aegisvest.watchdog")


def _update_history(history: list[RegimeHistoryPoint], result: RegimeResult, as_of: str) -> None:
    if result.low_confidence:
        _log.info("low_confidence (%d축) — history 미기록", result.n_axes_present)
        return
    if history and history[-1].date == as_of:
        history[-1] = RegimeHistoryPoint(date=as_of, total_score=result.total_score)
    else:
        history.append(RegimeHistoryPoint(date=as_of, total_score=result.total_score))
    save_list(_HISTORY, list(history[-_MAX_HISTORY:]))


def _handle_crisis(result: RegimeResult, as_of: str) -> None:
    prior = load_model(_CRISIS_FLAG, CrisisFlag)
    if result.crisis_active:
        save_model(
            _CRISIS_FLAG, CrisisFlag(active=True, reason=result.crisis_reason, detected_at=as_of)
        )
        if not (prior and prior.active):
            post(
                f"🆘 **CRISIS 발동** ({as_of})\n{result.crisis_reason}\n"
                f"regime={result.regime.value} · score_smooth={result.score_smooth:.1f}\n"
                f"주간 크루 즉시 실행 필요",
                channel="aegis-alerts",
            )
    elif prior and prior.active:
        save_model(_CRISIS_FLAG, CrisisFlag(active=False, cleared_at=as_of))
        post(f"✅ CRISIS 해제 ({as_of}) · regime={result.regime.value}", channel="aegis-alerts")


def run() -> RegimeResult:
    ensure_runtime_dirs()
    macro = macro_data()
    history = load_list(_HISTORY, RegimeHistoryPoint)
    crisis_state = load_model(_CRISIS_STATE, CrisisState) or CrisisState()

    result = regime_score(macro, history, crisis_state)

    save_model(_CRISIS_STATE, result.crisis_state)
    _update_history(history, result, macro.as_of)
    _handle_crisis(result, macro.as_of)

    _log.info(
        "%s regime=%s total=%d smooth=%.2f n_axes=%d%s stale=%s",
        macro.as_of,
        result.regime.value,
        result.total_score,
        result.score_smooth,
        result.n_axes_present,
        " low_conf" if result.low_confidence else "",
        macro.stale_fields or "-",
    )
    return result


def main() -> None:
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    run()


if __name__ == "__main__":
    main()
