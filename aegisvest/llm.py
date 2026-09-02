"""DeepSeek LLM 팩토리 (CrewAI). 3a-9+ 에이전트 계층 전용.

결정론 코어(pipeline.py)는 LLM 을 안 쓴다 — 키 없어도 백테스트·모의투자 가능.
재현성: temperature 낮게, DeepSeek 는 seed 미지원이라 완전 결정성은 불가 (mock 테스트로 보완).
"""

from __future__ import annotations

import os
from functools import lru_cache

os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")  # crewai import 전
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from crewai import LLM

from aegisvest.config import get_settings


class LLMUnavailableError(RuntimeError):
    """DEEPSEEK_API_KEY 미설정 — 에이전트 크루 실행 불가."""


@lru_cache(maxsize=4)
def get_llm(*, temperature: float) -> LLM:
    s = get_settings()
    if not s.deepseek_api_key:
        raise LLMUnavailableError(
            "DEEPSEEK_API_KEY 없음 — run_crew 불가. 결정론 코어(run_pipeline)는 영향 없음."
        )
    return LLM(
        model=s.model,
        api_key=s.deepseek_api_key,
        temperature=temperature,
        top_p=0.6,  # 재현성 — 낮게
    )
