"""스크립트 LLM — DeepSeek 없이 크루를 태운다 (TESTING 시나리오 6)."""

from __future__ import annotations

from typing import Any

import pytest
from crewai.llm import BaseLLM
from pydantic import Field

from aegisvest.schemas import PipelineResult
from tests.fixtures.pipeline import make_pipeline_result

__all__ = ["ScriptedLLM", "make_pipeline_result"]


class ScriptedLLM(BaseLLM):
    """response_model 이름 또는 태스크 expected_output 마커로 canned JSON 반환."""

    responses: dict[str, str] = Field(default_factory=dict)

    def __init__(self, responses: dict[str, str], **kw: Any) -> None:
        super().__init__(model="scripted/test", responses=responses, **kw)

    def call(self, messages: Any, *args: Any, **kwargs: Any) -> str:
        rm = kwargs.get("response_model")
        if rm is not None and rm.__name__ in self.responses:
            return self.responses[rm.__name__]
        ft = kwargs.get("from_task")
        hay = f"{ft.name or ''} {ft.expected_output or ''}" if ft is not None else ""
        for marker, payload in self.responses.items():
            if marker in hay:
                return payload
        return next(iter(self.responses.values()))

    def supports_function_calling(self) -> bool:
        return False

    def supports_stop_words(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return 16000


@pytest.fixture
def pipeline_result() -> PipelineResult:
    return make_pipeline_result()
