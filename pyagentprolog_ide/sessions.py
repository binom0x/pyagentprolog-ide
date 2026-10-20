"""Реестр сессий: {session_id: PrologIDE}, LRU на 100 сессий."""
from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from typing import Optional

_MAX_SESSIONS = 100
_REGISTRY: "OrderedDict[str, object]" = OrderedDict()
_LOCK = threading.RLock()


def new_session() -> str:
    from .app import PrologIDE  # локальный импорт — избегаем цикла

    sid = uuid.uuid4().hex
    with _LOCK:
        _REGISTRY[sid] = PrologIDE()
        while len(_REGISTRY) > _MAX_SESSIONS:
            _REGISTRY.popitem(last=False)
    return sid


def get_session(sid: Optional[str]):
    if not sid:
        return None
    with _LOCK:
        ide = _REGISTRY.get(sid)
        if ide is not None:
            _REGISTRY.move_to_end(sid)
        return ide


def drop_session(sid: str) -> None:
    with _LOCK:
        _REGISTRY.pop(sid, None)