"""CrewAI 에이전트 조직 ①~⑨ (3a-9 이후). 규격: docs/PROMPTS.md."""

from __future__ import annotations

import os

# 자가호스팅 펀드 — CrewAI 익명 텔레메트리 전송 차단 (import 시점, crewai import 전).
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
