"""Хелперы для контекста действий (Способ 4).

PrologIDE хранит:
  * ide.context         — общий dict внешних ресурсов (llm/db/api_key/...)
  * ide._context_builders — список callable, восстанавливающих context
                             после перезагрузки Agent (например, заново
                             создать клиента, если он одноразовый)

Все значения доступны внутри действий через `context=...`:
    @simple_action('ask_llm', 2, output_arg=1)
    def ask_llm(prompt, context):
        return context['llm'].invoke(prompt).content
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List


ContextDict = Dict[str, Any]
ContextBuilder = Callable[[ContextDict], None]


class ContextRegistry:
    """Реестр внешних ресурсов + их конструкторов для перезагрузки."""

    __slots__ = ("values", "builders")

    def __init__(self) -> None:
        self.values: ContextDict = {}
        self.builders: List[ContextBuilder] = []

    # --- прямое заполнение (статичные ресурсы) ---
    def set(self, key: str, value: Any) -> None:
        self.values[key] = value

    def update(self, mapping: ContextDict) -> None:
        self.values.update(mapping)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    # --- конструкторы (восстановление после перезагрузки) ---
    def add_builder(self, fn: ContextBuilder) -> None:
        """fn(ctx) — мутирует ctx. Вызывается при apply()."""
        self.builders.append(fn)

    def apply(self) -> ContextDict:
        """Строит новый dict: статичные значения + все builders."""
        ctx: ContextDict = dict(self.values)
        for fn in self.builders:
            try:
                fn(ctx)
            except Exception as e:  # noqa: BLE001
                ctx[f"__builder_error__{id(fn)}"] = str(e)
        return ctx

    def clear(self) -> None:
        self.values.clear()
        self.builders.clear()