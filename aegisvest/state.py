"""state/ 디렉토리 JSON persistence. 감시견·PaperBroker·일기가 공유한다.

읽기 실패(손상·스키마 불일치)는 None / [] 로 degrade — 런타임이 재생성한다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel

from aegisvest.config import get_settings


def _path(name: str) -> Path:
    d = get_settings().state_dir
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def _atomic_write(name: str, text: str) -> None:
    """temp 파일에 쓰고 os.replace — 쓰다 죽어도 기존 파일(포트폴리오 이력)이 안 깨진다."""
    p = _path(name)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)


def load_model[M: BaseModel](name: str, model: type[M]) -> M | None:
    p = _path(name)
    if not p.exists():
        return None
    try:
        return model.model_validate_json(p.read_text())
    except (ValueError, OSError):
        return None


def save_model(name: str, obj: BaseModel) -> None:
    _atomic_write(name, obj.model_dump_json(indent=2))


def load_list[M: BaseModel](name: str, model: type[M]) -> list[M]:
    p = _path(name)
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text())
        return [model.model_validate(x) for x in raw]
    except (ValueError, OSError, TypeError):
        return []


def save_list(name: str, items: list[BaseModel]) -> None:
    _atomic_write(name, json.dumps([x.model_dump() for x in items], indent=2, ensure_ascii=False))
