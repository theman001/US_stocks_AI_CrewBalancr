"""_io.py — TTL 캐시 동작 (TEST_GUIDE 시나리오 1: 캐시)."""

from __future__ import annotations

import time
from typing import Any

import pytest

from aegisvest.tools import _io


def test_cached_calls_producer_once() -> None:
    calls = {"n": 0}

    def producer() -> int:
        calls["n"] += 1
        return 42

    assert _io.cached("k1", 24, producer) == 42
    assert _io.cached("k1", 24, producer) == 42
    assert calls["n"] == 1  # 2번째는 캐시 히트


def test_cached_ttl_expiry() -> None:
    calls = {"n": 0}

    def producer() -> int:
        calls["n"] += 1
        return calls["n"]

    assert _io.cached("k2", 0.0, producer) == 1
    time.sleep(0.01)
    assert _io.cached("k2", 0.0, producer) == 2  # TTL 0 -> 항상 재생성


def test_cached_json_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    class FakeResp:
        def raise_for_status(self) -> None: ...
        def json(self) -> dict[str, Any]:
            return {"ok": True}

    def fake_get(*_a: Any, **_k: Any) -> FakeResp:
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(_io.requests, "get", fake_get)
    assert _io.cached_json("https://x.test/a", {"p": 1})["ok"] is True
    assert _io.cached_json("https://x.test/a", {"p": 1})["ok"] is True
    assert calls["n"] == 1


def test_clear_cache() -> None:
    _io.cached("k3", 24, lambda: 1)
    _io.clear_cache()
    calls = {"n": 0}
    _io.cached("k3", 24, lambda: calls.__setitem__("n", calls["n"] + 1) or 1)
    assert calls["n"] == 1


def test_cached_json_regenerates_on_corrupt_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    class FakeResp:
        def raise_for_status(self) -> None: ...
        def json(self) -> dict[str, Any]:
            return {"v": 1}

    def fake_get(*_a: Any, **_k: Any) -> FakeResp:
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(_io.requests, "get", fake_get)
    assert _io.cached_json("https://x.test/corrupt")["v"] == 1
    # 캐시 파일을 truncate — 다음 호출은 조용히 재생성해야 (예외 전파 금지)
    path = _io._cache_path("https://x.test/corrupt?{}", ".json")
    path.write_text("{not json", encoding="utf-8")
    assert _io.cached_json("https://x.test/corrupt")["v"] == 1
    assert calls["n"] == 2
