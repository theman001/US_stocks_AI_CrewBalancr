"""no_fabricated_numbers — 할루시네이션 가드 (TESTING 시나리오 7, 필수)."""

from __future__ import annotations

from dataclasses import dataclass

from aegisvest.agents.guardrails import no_fabricated_numbers


@dataclass
class _Out:
    raw: str


_PAYLOAD = {
    "targets": {"low": 0.4, "mid": 0.36, "high": 0.14},
    "score_smooth": 6.0,
    "scores": [90.0, 88.5, 71.0],
}


def test_hedge_word_plus_number_rejected() -> None:
    check = no_fabricated_numbers(_PAYLOAD)
    ok, msg = check(_Out(raw="고위험을 약 15% 수준으로 방어한다"))
    assert ok is False
    assert "헤지" in msg


def test_number_not_in_payload_rejected() -> None:
    check = no_fabricated_numbers(_PAYLOAD)
    ok, msg = check(_Out(raw="배분 목표는 저위험 55%로 본다"))  # 55 는 페이로드에 없음
    assert ok is False
    assert "55" in msg


def test_payload_numbers_pass() -> None:
    check = no_fabricated_numbers(_PAYLOAD)
    # 40%(=0.4), score_smooth 6, 점수 90 — 전부 페이로드 유래
    ok, out = check(_Out(raw="저위험 목표 40%, 레짐 스코어 6, 1등 종목 점수 90"))
    assert ok is True
    assert isinstance(out, _Out)


def test_pure_qualitative_passes() -> None:
    check = no_fabricated_numbers(_PAYLOAD)
    ok, _ = check(_Out(raw="변동성은 안정적이나 시장 폭이 약하다. 금리 재상승 리스크에 유의."))
    assert ok is True


def test_year_allowed() -> None:
    check = no_fabricated_numbers(_PAYLOAD)
    ok, _ = check(_Out(raw="2026년 4분기 FOMC 이벤트 리스크"))
    assert ok is True


def test_hedge_only_allows_tool_numbers_but_catches_hedge() -> None:
    check = no_fabricated_numbers(_PAYLOAD, hedge_only=True)
    # 툴이 준 값 (페이로드엔 없지만 fundamentals 툴 반환) — 통과
    ok, _ = check(_Out(raw="PEG 1.85, ROE 31%로 우량 (fundamentals 툴)"))
    assert ok is True
    # 헤지는 여전히 거부
    bad, _ = check(_Out(raw="대략 20% 성장 예상"))
    assert bad is False
