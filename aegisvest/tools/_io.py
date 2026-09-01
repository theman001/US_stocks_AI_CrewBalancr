"""파일 기반 TTL 캐시 헬퍼 — 모든 툴의 네트워크 호출이 경유한다.

`cached_json`: HTTP GET -> JSON (FRED/FMP).
`cached_text`: HTTP GET -> 본문 텍스트 (RSS/XML).
`cached`: 임의 객체 pickle 캐시 (yfinance DataFrame 등).
실패는 예외로 전파된다 -- 호출 툴이 try/except 로 잡아 ToolError 를 반환한다.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import pickle
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import requests

from aegisvest.config import get_settings

_TIMEOUT = 15


def _cache_path(key: str, suffix: str) -> Path:
    cache_dir = get_settings().cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(key.encode()).hexdigest()[:32]
    return cache_dir / f"{digest}{suffix}"


def _fresh(path: Path, ttl_hours: float) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < ttl_hours * 3600


def _ttl(explicit: float | None) -> float:
    return explicit if explicit is not None else float(get_settings().cache_ttl_hours)


def cached[T](key: str, ttl_hours: float, producer: Callable[[], T]) -> T:
    """임의 객체를 pickle 로 TTL 캐시. 캐시 히트 시 producer 미호출."""
    path = _cache_path(key, ".pkl")
    if _fresh(path, ttl_hours):
        # 캐시 읽기 실패(손상·라이브러리 버전 변경)는 조용히 재생성한다
        with contextlib.suppress(
            pickle.UnpicklingError, EOFError, ValueError, AttributeError, ImportError
        ):
            return cast(T, pickle.loads(path.read_bytes()))
    value = producer()
    with contextlib.suppress(OSError):
        path.write_bytes(pickle.dumps(value))
    return value


def cached_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    ttl_hours: float | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """HTTP GET -> 파싱된 JSON, TTL 캐시. 네트워크/HTTP 오류는 예외로 전파."""
    key = url + "?" + json.dumps(params or {}, sort_keys=True)
    path = _cache_path(key, ".json")
    if _fresh(path, _ttl(ttl_hours)):
        return json.loads(path.read_text())
    resp = requests.get(url, params=params, headers=headers, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    with contextlib.suppress(OSError, TypeError):
        path.write_text(json.dumps(data))
    return data


def cached_text(
    url: str,
    *,
    ttl_hours: float | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    """HTTP GET -> 본문 텍스트 (RSS/XML), TTL 캐시."""
    path = _cache_path(url, ".txt")
    if _fresh(path, _ttl(ttl_hours)):
        return path.read_text()
    resp = requests.get(url, headers=headers, timeout=_TIMEOUT)
    resp.raise_for_status()
    text: str = resp.text
    with contextlib.suppress(OSError):
        path.write_text(text)
    return text


def clear_cache() -> None:
    """캐시 디렉토리의 캐시 파일 제거 (테스트용)."""
    cache_dir = get_settings().cache_dir
    if cache_dir.exists():
        for f in cache_dir.iterdir():
            if f.suffix in {".json", ".pkl", ".txt"}:
                f.unlink()
