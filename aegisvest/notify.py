"""Mattermost 인커밍 웹훅 알림. 미설정 시 로그만 남긴다. 근거: report/phase-3 §6.

전용 라이브러리 없이 requests.post 만 사용. 채널 오버라이드는 payload 의 `channel`.
"""

from __future__ import annotations

import logging

import requests

from aegisvest.config import get_settings

_log = logging.getLogger("aegisvest.notify")
_TIMEOUT = 10


def post(text: str, *, username: str = "AegisVest", channel: str | None = None) -> bool:
    """웹훅으로 메시지 게시. 성공 시 True. 미설정·실패 시 False (예외 없음)."""
    url = get_settings().mattermost_webhook_url
    if not url:
        _log.info("[알림·웹훅없음] %s", text)
        return False
    payload: dict[str, str] = {"text": text, "username": username}
    if channel:
        payload["channel"] = channel
    try:
        resp = requests.post(url, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        _log.warning("Mattermost 알림 실패: %s", exc)
        return False
    return True
