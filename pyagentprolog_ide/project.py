"""Работа с проектом: папка + kb.pl + опциональный my_actions.py.

Проект = директория, в которой:
  * kb.pl (или любая .pl) — программа Prolog;
  * my_actions.py         — опционально, Python-модуль действий.

Функции:
  * resolve_project_dir(input)   — принимает строку/файл, возвращает
                                    абсолютный путь к папке проекта;
  * register_project_dir(dir)    — добавляет dir в sys.path (идемпотентно);
  * find_kb(dir)                 — находит kb.pl (или первую .pl);
  * actions_module_path(dir)     — путь к my_actions.py (или None);
  * actions_signature(path)      — mtime+size для детекта изменений.
"""
from __future__ import annotations

import os
import sys
from typing import Optional


ACTIONS_FILENAME = "my_actions.py"
KB_FILENAME = "kb.pl"


def resolve_project_dir(inp) -> Optional[str]:
    """Строка/файл → абсолютный путь к папке проекта.

    * файл my_actions.py → возвращаем его родительскую папку;
    * файл kb.pl         → возвращаем его родительскую папку;
    * любой другой файл  → его родительскую папку;
    * директория         → её саму;
    * строка             → abspath.
    """
    if inp is None:
        return None
    if hasattr(inp, "name"):
        path = inp.name
    else:
        path = str(inp)
    path = os.path.abspath(path.strip())
    if os.path.isfile(path):
        return os.path.dirname(path)
    if os.path.isdir(path):
        return path
    return None


def register_project_dir(dir_path: str) -> None:
    """Добавляет dir_path в начало sys.path (идемпотентно)."""
    if not dir_path:
        return
    dir_path = os.path.abspath(dir_path)
    if dir_path not in sys.path:
        sys.path.insert(0, dir_path)


def unregister_project_dir(dir_path: str) -> None:
    """Убирает dir_path из sys.path (если был добавлен)."""
    if not dir_path:
        return
    dir_path = os.path.abspath(dir_path)
    while dir_path in sys.path:
        sys.path.remove(dir_path)


def find_kb(dir_path: str) -> Optional[str]:
    """Возвращает путь к kb.pl (или первой .pl) или None."""
    if not dir_path or not os.path.isdir(dir_path):
        return None
    candidate = os.path.join(dir_path, KB_FILENAME)
    if os.path.isfile(candidate):
        return candidate
    try:
        for name in sorted(os.listdir(dir_path)):
            if name.endswith(".pl") or name.endswith(".prolog"):
                return os.path.join(dir_path, name)
    except OSError:
        return None
    return None


def actions_module_path(dir_path: str) -> Optional[str]:
    """Путь к my_actions.py, если он есть."""
    if not dir_path:
        return None
    candidate = os.path.join(dir_path, ACTIONS_FILENAME)
    return candidate if os.path.isfile(candidate) else None


def actions_signature(path: Optional[str]) -> Optional[tuple]:
    """(mtime_ns, size) или None — для детекта изменений файла."""
    if not path:
        return None
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None
        
def examples_root() -> str:
    """Путь к встроенной папке примеров (рядом с этим модулем)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "examples")