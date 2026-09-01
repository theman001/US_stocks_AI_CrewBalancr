"""CrewAI 에이전트 조직 ①~⑨ (3a-9 이후). 규격: docs/PROMPTS.md."""

from __future__ import annotations

import logging
import os

# 자가호스팅 펀드 — CrewAI 익명 텔레메트리 전송 차단 (import 시점, crewai import 전).
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")


def quiet_crew_console() -> None:
    """CrewAI 의 rich Panel 콘솔 출력 억제 — 우리 로깅만 쓴다. main/watchdog/테스트가 호출."""
    try:
        from crewai.events.utils.console_formatter import (  # noqa: PLC0415
            set_suppress_console_output,
        )

        set_suppress_console_output(True)
    except Exception:  # 버전 차이로 심볼 없을 수 있음
        logging.getLogger("aegisvest").debug("crewai 콘솔 억제 심볼 없음")
