"""공유 Pydantic 스키마 — 열거형과 기본 타입.

각 빌드 단계가 자신의 모델을 여기에 추가한다 (add-tool / add-agent 스킬 참조).
숫자 필드는 항상 툴 출처를 추적할 수 있어야 한다 (Metric).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Category(StrEnum):
    """리스크 3티어."""

    LOW = "LOW"
    MID = "MID"
    HIGH = "HIGH"


class Regime(StrEnum):
    """매크로 레짐 라벨."""

    BULL = "BULL"
    NEUTRAL = "NEUTRAL"
    BEAR = "BEAR"
    CRISIS = "CRISIS"


class Verdict(StrEnum):
    """Risk Officer 판정 / 일기 채점 결과."""

    APPROVED = "APPROVED"
    CONDITIONAL = "CONDITIONAL"
    REJECTED = "REJECTED"


class ToolError(BaseModel):
    """툴 실패 반환. 툴은 예외를 raise 하지 않고 이 형태를 반환한다."""

    error: str
    field: str


class Metric(BaseModel):
    """추적 가능한 수치 — 에이전트 출력의 모든 숫자는 이 형태로 출처를 남긴다."""

    name: str
    value: float
    source_tool: str
    source_call_id: str = Field(default="", description="이번 실행의 tool_call_id")
