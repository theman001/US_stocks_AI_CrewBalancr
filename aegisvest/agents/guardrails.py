"""no_fabricated_numbers — 에이전트 출력의 숫자를 입력 페이로드와 대조. report/phase-3 §5.

CrewAI task guardrail 규약: `(bool, output_or_error)` 반환. False 면 에이전트 재시도.
3a-9 에이전트는 숫자를 거의 안 내지만(해설·판단), 방어선으로 강제. 3b PM(틸트 %) 에서 강화.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

GuardrailFn = Callable[[Any], "tuple[bool, Any]"]

# "약 15%", "대략 3.2", "~10%", "roughly 5" 등 — 헤지 표현 + 숫자.
# `~` 는 앞에 숫자가 없을 때만 (근사) — "2~4주", "-0.2~0.2" 같은 범위 표기는 헤지 아님.
_HEDGE = re.compile(
    r"(?:약|대략|얼추|추정컨대|어림잡아|roughly|approximately|around|about)\s*[-+]?\d"
    r"|(?<!\d)~\s*[-+]?\d",
    re.IGNORECASE,
)
# 정량적 주장만 검사: 퍼센트(15%) 또는 소수(1.8). 맨 정수(200일선·S&P 500)는 참조·이름이라 통과.
_NUM = re.compile(r"(?<![\w./-])[-+]?\d{1,4}(?:\.\d+)?\s?%|(?<![\w./-])[-+]?\d{1,4}\.\d+")
# 참조 상수 (이동평균 기간·지수명 + 3티어 전략 상수: 손절%·Rule of 40·배당성향) — 페이로드 밖 허용
_REFERENCE = {
    "20", "50", "100", "200", "500", "2000", "3000", "10", "30", "90", "52",
    "15", "25", "40", "65", "-15", "-20", "-25",
}  # fmt: skip


def _norm(tok: str) -> str:
    return tok.replace(" ", "").rstrip(".")


def _allowed_from(payload: dict[str, Any]) -> set[str]:
    """페이로드(중첩 dict/list) 의 모든 숫자를 문자열 토큰 집합으로. %·소수 표기 변형 포함."""
    out: set[str] = set()

    def walk(v: Any) -> None:
        if isinstance(v, bool):
            return
        if isinstance(v, int | float):
            f = float(v)
            for s in (f"{f:g}", f"{f:.0f}", f"{f:.1f}", f"{f:.2f}"):
                out.add(s)
                out.add(f"{s}%")
            for pct in (f * 100.0,):  # 소수 비중 → 퍼센트 표기도 허용
                for s in (f"{pct:g}", f"{pct:.0f}", f"{pct:.1f}"):
                    out.add(s)
                    out.add(f"{s}%")
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list | tuple):
            for x in v:
                walk(x)

    walk(payload)
    return out


def no_fabricated_numbers(
    payload: dict[str, Any], *, extra_allowed: set[str] | None = None, hedge_only: bool = False
) -> GuardrailFn:
    """숫자 조작 방지 guardrail.

    `hedge_only=True`: "약 15%" 같은 헤지 표현만 거부 (툴을 쓰는 ①②③ 용 — 툴 반환값을
    페이로드로 못 잡으므로). `False`: 추가로 정량 주장이 payload 값인지 대조 (④⑤⑧).
    """
    allowed = _allowed_from(payload) | (extra_allowed or set()) | _REFERENCE
    allowed |= {str(n) for n in range(0, 13)} | {str(y) for y in range(2024, 2031)}

    def _check(task_output):  # type: ignore[no-untyped-def]  # crewai 가 반환 어노테이션을 검증
        text = getattr(task_output, "raw", None) or str(task_output)
        if _HEDGE.search(text):
            return (
                False,
                "헤지 표현('약','대략','~')+숫자. 툴이 준 정확한 값만, 헤지 없이 인용하라.",
            )
        if hedge_only:
            return True, task_output
        for m in _NUM.finditer(text):
            tok = _norm(m.group(0))
            if not tok or tok in {"%", "-", "+"}:
                continue
            if tok not in allowed and tok.rstrip("%") not in allowed:
                return False, (
                    f"입력 페이로드에 없는 수치 '{tok}'. 상류 툴/태스크가 전달한 값만 사용하라."
                )
        return True, task_output

    return _check
