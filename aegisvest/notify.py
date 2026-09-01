"""Mattermost 인커밍 웹훅 알림. 미설정 시 로그만. 근거: report/phase-3 §6.

기본 웹훅은 **채널 고정** (payload `channel` 오버라이드 불가 — 2026-09 확인, 404 반환).
따라서: 채널별 웹훅(`MM_WEBHOOK_RESEARCH/DECISIONS/ALERTS`)이 있으면 그리로, 없으면
기본 `MATTERMOST_WEBHOOK_URL` + 텍스트에 `[채널]` 태그. 전용 라이브러리 없이 requests.post.
"""

from __future__ import annotations

import logging

import requests

from aegisvest.config import get_settings

_log = logging.getLogger("aegisvest.notify")
_TIMEOUT = 10


def _route(channel: str | None) -> tuple[str | None, str]:
    """채널 → (사용할 웹훅 URL, 텍스트 접두). 채널별 웹훅 있으면 접두 없이."""
    s = get_settings()
    per_channel = {
        "aegis-research": s.mattermost_webhook_research,
        "aegis-decisions": s.mattermost_webhook_decisions,
        "aegis-alerts": s.mattermost_webhook_alerts,
    }
    if channel and per_channel.get(channel):
        return per_channel[channel], ""
    prefix = f"[{channel}] " if channel else ""
    return s.mattermost_webhook_url, prefix


def post(text: str, *, username: str = "AegisVest", channel: str | None = None) -> bool:
    """웹훅으로 메시지 게시. 성공 시 True. 미설정·실패 시 False (예외 없음)."""
    url, prefix = _route(channel)
    if not url:
        _log.info("[알림·웹훅없음] %s%s", prefix, text)
        return False
    try:
        resp = requests.post(
            url, json={"text": prefix + text, "username": username}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        _log.warning("Mattermost 알림 실패: %s", exc)
        return False
    return True


def post_agent_note(
    agent: str, emoji: str, summary: str, detail: str = "", *, channel: str = "aegis-research"
) -> bool:
    """에이전트 노트 1건 게시 — `에이전트 · 이모지 · 요약` + 상세 접기. report/phase-3 §6."""
    body = f"{emoji} **{agent}** · {summary}"
    if detail:
        body += f"\n<details><summary>상세</summary>\n\n{detail}\n</details>"
    return post(body, username="AegisVest 조직", channel=channel)
