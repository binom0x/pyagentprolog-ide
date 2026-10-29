"""PyAgentProlog IDE — Gradio Blocks UI.

Тёмная тема, компактная вёрстка в 3 колонки:
  1) проект (drag-drop .pl, поле пути, кнопки Открыть/Создать/Сохранить,
     shortcut 📚 к примерам), context, semantic, diag;
  2) редактор кода + действия + KB;
  3) запрос, результаты, трассировка, breakpoints.

Примеры — отдельные проекты в pyagentprolog_ide/examples/<name>/kb.pl.
Dropdown "Пример" удалён.

(с) 2026 Andrey Vorfolomeev
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import threading
import time
import traceback
from html import escape as _esc
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from prolog.agent import Agent
from prolog.parser import Parser
from prolog.tracer import ProofTracer

from ._gradio_compat import blocks_kwargs, code_language, launch_kwargs
from .actions_ctx import ContextRegistry
from .breakpoints import AbortException, BreakpointController, BreakpointTracer
from .project import (
    KB_FILENAME,
    actions_module_path,
    actions_signature,
    examples_root,
    find_kb,
    register_project_dir,
    resolve_project_dir,
    unregister_project_dir,
)
from .sessions import get_session, new_session
from .streaming import stream_with_timeout
from .tree_view import (
    build_trace_artifacts,
    render_tree_html,
    subst_rows_from_dict,
)


# =====================================================================
# Глобальный CSS (dark + compact)
# =====================================================================
_GLOBAL_CSS = """
.gradio-container { max-width: 1900px !important; padding: 6px 8px !important; }
footer { display: none !important; }

button.compact-btn, .compact-btn button {
    min-height: 26px !important;
    padding: 2px 8px !important;
    font-size: 12px !important;
    line-height: 1.2 !important;
}
.compact-tb input, .compact-tb textarea {
    padding: 3px 7px !important;
    font-size: 12px !important;
    min-height: 26px !important;
}
.compact-lbl label {
    font-size: 11px !important;
    margin-bottom: 1px !important;
    color: #8b949e !important;
}
pre.status-box {
    margin: 0 !important;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 11px;
    line-height: 1.35;
    padding: 4px 8px;
    background: #0b0d11;
    border: 1px solid #2a313d;
    border-radius: 4px;
    color: #c7cbd1;
    white-space: pre-wrap;
    max-height: 100px;
    overflow: auto;
}
.proj-info {
    font-size: 11px;
    line-height: 1.35;
    color: #8b949e;
    padding: 4px 8px;
    background: #0b0d11;
    border: 1px solid #2a313d;
    border-radius: 4px;
    word-break: break-all;
}
.proj-info b { color: #c7cbd1; }
.proj-info code { color: #79c0ff; background: transparent !important; }

.col-head { font-size: 14px !important; font-weight: 600; margin: 2px 0 6px 0 !important; color: #c7cbd1; }

*::-webkit-scrollbar { width: 8px; height: 8px; }
*::-webkit-scrollbar-track { background: transparent; }
*::-webkit-scrollbar-thumb { background: #2a313d; border-radius: 5px; }
*::-webkit-scrollbar-thumb:hover { background: #3a4250; }

.md code, .prose code { background: #1c212a !important; color: #e6e6e6 !important; }

.cm-editor { background: #0b0d11 !important; color: #e6e6e6 !important; }
.cm-editor .cm-gutters { background: #0f1115 !important; color: #6e7681 !important; border-right: 1px solid #2a313d; }
.cm-editor .cm-activeLineGutter { background: #161a20 !important; }
.cm-editor .cm-activeLine { background: #161a20 !important; }
.cm-editor .cm-selectionBackground { background: #2a313d !important; }

/* Tiny icon-only buttons */
button.tiny-btn, .tiny-btn button {
    min-height: 22px !important;
    height: 22px !important;
    min-width: 24px !important;
    padding: 0 4px !important;
    font-size: 11px !important;
    line-height: 1 !important;
    flex: 0 0 auto !important;
}
.tiny-row {
    gap: 2px !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
}
.tiny-row > * { min-width: 0 !important; }

/* ===================================================================
   gr.Dataframe — тёмная тема (шаги, subst и любые другие Dataframes)
   Покрывает: Gradio 4/5 (HTML <table>) и Gradio 6 (role="grid").
   =================================================================== */

/* --- Контейнеры --- */
.gradio-dataframe,
.gradio-dataframe > div,
.gradio-dataframe .table-wrap,
.gradio-dataframe .wrap {
    background-color: #0b0d11 !important;
    color: #e6e6e6 !important;
    border-color: #2a313d !important;
}

/* --- HTML <table> (Gradio 4/5) --- */
.gradio-dataframe table {
    background-color: #0b0d11 !important;
    color: #e6e6e6 !important;
    border-collapse: collapse !important;
    border-color: #2a313d !important;
}
.gradio-dataframe thead,
.gradio-dataframe thead tr {
    background-color: #1c212a !important;
}
.gradio-dataframe th {
    background-color: #1c212a !important;
    color: #c7cbd1 !important;
    border-color: #2a313d !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    padding: 3px 6px !important;
}
.gradio-dataframe tbody,
.gradio-dataframe tbody tr {
    background-color: #0b0d11 !important;
}
.gradio-dataframe td {
    background-color: #0b0d11 !important;
    color: #e6e6e6 !important;
    border-color: #2a313d !important;
    font-size: 11px !important;
    padding: 3px 6px !important;
}
.gradio-dataframe tbody tr:hover td,
.gradio-dataframe tbody tr:hover {
    background-color: #161a20 !important;
}

/* --- ARIA-grid (Gradio 6) --- */
.gradio-dataframe [role="grid"],
.gradio-dataframe [role="row"],
.gradio-dataframe [role="rowgroup"],
.gradio-dataframe [role="gridcell"] {
    background-color: #0b0d11 !important;
    color: #e6e6e6 !important;
    border-color: #2a313d !important;
}
.gradio-dataframe [role="columnheader"] {
    background-color: #1c212a !important;
    color: #c7cbd1 !important;
    border-color: #2a313d !important;
    font-size: 11px !important;
    font-weight: 600 !important;
}
.gradio-dataframe [role="gridcell"] {
    font-size: 11px !important;
    padding: 3px 6px !important;
}
.gradio-dataframe [role="row"]:hover [role="gridcell"] {
    background-color: #161a20 !important;
}

/* --- Выделенная / сфокусированная ячейка --- */
.gradio-dataframe td.selected,
.gradio-dataframe [role="gridcell"][aria-selected="true"] {
    background-color: #2a313d !important;
    color: #ffffff !important;
}

/* --- Редактируемые input/textarea внутри ячеек (на всякий случай) --- */
.gradio-dataframe input,
.gradio-dataframe textarea,
.gradio-dataframe select {
    background-color: #0f1115 !important;
    color: #e6e6e6 !important;
    border-color: #2a313d !important;
}

/* --- Скроллбар внутри таблицы --- */
.gradio-dataframe ::-webkit-scrollbar { width: 8px; height: 8px; }
.gradio-dataframe ::-webkit-scrollbar-thumb { background: #2a313d; border-radius: 5px; }
.gradio-dataframe ::-webkit-scrollbar-track { background: transparent; }
"""

# =====================================================================
# Дополнительный CSS через <head> — страховка для gr.Dataframe.
# Инжектируется в <head> страницы отдельно от launch(css=...).
# =====================================================================
_HEAD_DARK = """
<style>
/* ---- CSS-переменные Gradio, на которые реагирует таблица ---- */
:root, body, .gradio-container {
    --table-odd-background-fill: #0b0d11;
    --table-even-background-fill: #0b0d11;
    --table-row-focus: #161a20;
    --table-border-color: #2a313d;
    --table-radius: 4px;
    --color-accent-soft: #2a313d;
    --block-background-fill: #161a20;
    --background-fill-primary: #0b0d11;
    --background-fill-secondary: #0b0d11;
    --border-color-primary: #2a313d;
    --body-text-color: #e6e6e6;
}

/* ---- Агрессивный бланкет по всему Dataframe ---- */
.gradio-dataframe,
.gradio-dataframe *,
.gradio-dataframe *::before,
.gradio-dataframe *::after,
[class*="dataframe"],
[class*="dataframe"] *,
[class*="dataframe"] *::before,
[class*="dataframe"] *::after,
[data-testid="dataframe"],
[data-testid="dataframe"] * {
    background: #0b0d11 !important;
    background-color: #0b0d11 !important;
    background-image: none !important;
    color: #e6e6e6 !important;
    border-color: #2a313d !important;
}

/* ---- Заголовки (перекрываем бланкет выше) ---- */
.gradio-dataframe thead,
.gradio-dataframe thead *,
.gradio-dataframe thead *::before,
.gradio-dataframe thead *::after,
.gradio-dataframe th,
.gradio-dataframe [role="columnheader"],
.gradio-dataframe [role="columnheader"] *,
.gradio-dataframe [role="rowgroup"]:first-child,
.gradio-dataframe [role="rowgroup"]:first-child *,
[class*="dataframe"] thead,
[class*="dataframe"] thead *,
[class*="dataframe"] th,
[class*="dataframe"] [role="columnheader"],
[class*="dataframe"] [role="columnheader"] *,
[data-testid="dataframe"] thead *,
[data-testid="dataframe"] [role="columnheader"] {
    background: #1c212a !important;
    background-color: #1c212a !important;
    color: #c7cbd1 !important;
    font-size: 11px !important;
    font-weight: 600 !important;
}

/* ---- Ячейки ---- */
.gradio-dataframe td,
.gradio-dataframe [role="cell"],
.gradio-dataframe [role="gridcell"],
[class*="dataframe"] td,
[class*="dataframe"] [role="cell"],
[class*="dataframe"] [role="gridcell"] {
    font-size: 11px !important;
    padding: 3px 6px !important;
}

/* ---- Hover ---- */
.gradio-dataframe [role="row"]:hover,
.gradio-dataframe [role="row"]:hover *,
.gradio-dataframe tr:hover,
.gradio-dataframe tr:hover *,
[class*="dataframe"] [role="row"]:hover *,
[class*="dataframe"] tr:hover * {
    background: #161a20 !important;
    background-color: #161a20 !important;
}

/* ---- Selected ---- */
.gradio-dataframe td.selected,
.gradio-dataframe [role="cell"][aria-selected="true"],
.gradio-dataframe [role="gridcell"][aria-selected="true"],
[class*="dataframe"] td.selected,
[class*="dataframe"] [aria-selected="true"] {
    background: #2a313d !important;
    color: #ffffff !important;
}

/* ---- Input внутри ячеек (на случай interactive) ---- */
.gradio-dataframe input,
.gradio-dataframe textarea,
[class*="dataframe"] input,
[class*="dataframe"] textarea {
    background: #0f1115 !important;
    color: #e6e6e6 !important;
    border-color: #2a313d !important;
}

#steps_df,
#steps_df *,
#subst_df,
#subst_df * {
    background: #0b0d11 !important;
    background-color: #0b0d11 !important;
    color: #e6e6e6 !important;
    border-color: #2a313d !important;
}
#steps_df thead,
#steps_df thead *,
#steps_df [role="columnheader"],
#subst_df thead,
#subst_df thead *,
#subst_df [role="columnheader"] {
    background: #1c212a !important;
    background-color: #1c212a !important;
    color: #c7cbd1 !important;
}
</style>
"""

# =====================================================================
# Утилиты
# =====================================================================
def _run_with_timeout(fn, timeout: float):
    box, err = {}, {}

    def w():
        try:
            box["v"] = fn()
        except BaseException as e:  # noqa: BLE001
            err["e"] = e

    t = threading.Thread(target=w, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"Таймаут {timeout}s")
    if "e" in err:
        raise err["e"]
    return box.get("v")


def _to_timeout(v, default: float = 30.0) -> float:
    """Безопасно превращает ввод пользователя в timeout-секунды.

    Пусто / None / нечисло / <=0 → default.
    """
    try:
        x = float(v)
        return x if x > 0 else default
    except (TypeError, ValueError):
        return default


def _status_html(s: str) -> str:
    return f'<pre class="status-box">{_esc(str(s))}</pre>'


def _get_ide(sid: Optional[str]):
    ide = get_session(sid)
    if ide is None:
        raise gr.Error("Сессия не найдена. Перезагрузите страницу.")
    return ide


def _pick_folder(initial: str = "",
                 title: str = "Выберите папку проекта") -> Optional[str]:
    """Нативный диалог выбора папки через tkinter."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as e:  # noqa: BLE001
        print(f"[_pick_folder] tkinter unavailable: {e}")
        return None
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        path = filedialog.askdirectory(
            initialdir=initial or os.path.expanduser("~"),
            title=title,
            mustexist=False,
        )
        root.destroy()
        return path or None
    except Exception as e:  # noqa: BLE001
        print(f"[_pick_folder] {e}")
        return None


def _pick_pl_file(initial: str = "",
                  title: str = "Открыть проект — выберите .pl файл"
                  ) -> Optional[str]:
    """Диалог выбора .pl файла. Возвращает путь к файлу или None."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as e:  # noqa: BLE001
        print(f"[_pick_pl_file] tkinter unavailable: {e}")
        return None
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        init = initial if (initial and os.path.isdir(initial)) \
            else os.path.expanduser("~")
        path = filedialog.askopenfilename(
            initialdir=init,
            title=title,
            filetypes=[
                ("Prolog (*.pl)", "*.pl"),
                ("Prolog (*.prolog)", "*.prolog"),
                ("All files", "*.*"),
            ],
        )
        root.destroy()
        return path or None
    except Exception as e:  # noqa: BLE001
        print(f"[_pick_pl_file] {e}")
        return None

_DEFAULT_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="12" fill="#4f46e5"/>'
    '<text x="32" y="46" font-family="ui-sans-serif,system-ui,sans-serif" '
    'font-size="40" font-weight="700" fill="#ffffff" '
    'text-anchor="middle" dominant-baseline="middle">P</text>'
    '</svg>'
)


def _ensure_favicon() -> Optional[str]:
    """Возвращает путь к favicon.

    Ищет favicon.{png,ico,svg} в корне пакета или в подпапке assets/.
    Если файла нет — генерирует дефолтный SVG в корне пакета,
    чтобы не зависеть от внешних ресурсов.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for subdir in ("", "assets"):
        for name in ("favicon.png", "favicon.ico", "favicon.svg"):
            path = os.path.join(here, subdir, name) if subdir \
                else os.path.join(here, name)
            if os.path.isfile(path):
                return path
    # ничего нет — создаём дефолтный SVG
    try:
        path = os.path.join(here, "favicon.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(_DEFAULT_FAVICON_SVG)
        return path
    except OSError as e:
        print(f"[favicon] cannot write default: {e}")
        return None

# =====================================================================
# PrologIDE
# =====================================================================
class PrologIDE:
    def __init__(self):
        self.agent: Optional[Agent] = None
        self._signature: Optional[str] = None
        self.controller = BreakpointController()
        self.history: List[Dict] = []

        self.project_dir: Optional[str] = None
        self._actions_module_name: str = "my_actions"
        self._actions_sig: Optional[Tuple[int, int]] = None
        self._kb_file_hint: Optional[str] = None

        self.context = ContextRegistry()

    # ------------------------------------------------------------------
    # Agent
    # ------------------------------------------------------------------
    def _ensure_agent(self, text: str) -> Agent:
        if self.agent is None or self._signature != text:
            ctx = self.context.apply()
            self.agent = Agent(text, context=ctx)
            self._signature = text
            self._load_project_actions()
        return self.agent

    def _load_project_actions(self) -> None:
        if self.agent is None or not self.project_dir:
            return
        mod_path = actions_module_path(self.project_dir)
        if not mod_path:
            return
        sig = actions_signature(mod_path)
        if sig is None:
            return
        register_project_dir(self.project_dir)
        name = self._actions_module_name
        try:
            if name in sys.modules:
                mod = importlib.reload(sys.modules[name]) if sig != self._actions_sig \
                    else sys.modules[name]
            else:
                mod = importlib.import_module(name)
            self.agent.register_action_module(mod)
            self._actions_sig = sig
        except Exception as e:  # noqa: BLE001
            print(f"[actions import] {mod_path}: {e}")

    # ------------------------------------------------------------------
    # Проект
    # ------------------------------------------------------------------
    def set_project(self, inp) -> str:
        raw = inp.name if hasattr(inp, "name") else str(inp or "").strip()
        new_dir = resolve_project_dir(inp)
        if not new_dir or not os.path.isdir(new_dir):
            return f"✗ Папка не найдена: {inp!r}"

        hint = None
        if raw and os.path.isfile(raw) and \
                (raw.endswith(".pl") or raw.endswith(".prolog")):
            hint = os.path.abspath(raw)

        if self.project_dir and self.project_dir != new_dir:
            unregister_project_dir(self.project_dir)
        self.project_dir = new_dir
        self._kb_file_hint = hint
        register_project_dir(new_dir)

        self.agent = None
        self._signature = None
        self._actions_sig = None

        kb = hint or find_kb(new_dir)
        mod = actions_module_path(new_dir)
        lines = [f"✓ Проект: {new_dir}"]
        lines.append(f"  kb:            "
                     f"{os.path.basename(kb) if kb else '—'}")
        lines.append(f"  my_actions.py: {'есть' if mod else '—'}")
        return "\n".join(lines)

    def get_project_info(self) -> Dict[str, Any]:
        if not self.project_dir:
            return {"project_dir": None}
        kb = self._kb_file_hint
        if not kb or not os.path.isfile(kb):
            kb = find_kb(self.project_dir)
        return {
            "project_dir": self.project_dir,
            "kb": kb,
            "my_actions": actions_module_path(self.project_dir),
            "actions_loaded": self._actions_sig is not None,
            "sys_path_has_project": self.project_dir in sys.path,
        }

    def load_kb_from_project(self) -> Tuple[str, str]:
        if not self.project_dir:
            return "", "✗ Проект не выбран"
        kb = self._kb_file_hint
        if not kb or not os.path.isfile(kb):
            kb = find_kb(self.project_dir)
        if not kb:
            return "", f"✗ В {self.project_dir} не найден .pl"
        try:
            with open(kb, encoding="utf-8") as f:
                text = f.read()
            return text, self.load_program(text)
        except Exception as e:  # noqa: BLE001
            return "", f"✗ {e}\n{traceback.format_exc()}"

    def save_project(self, text: str) -> str:
        if not self.project_dir:
            return "✗ Проект не выбран"
        kb = find_kb(self.project_dir) or os.path.join(self.project_dir, KB_FILENAME)
        try:
            with open(kb, "w", encoding="utf-8") as f:
                f.write(text or "")
            return f"✓ Сохранено: {kb}"
        except Exception as e:  # noqa: BLE001
            return f"✗ {e}"

    def new_project(self, path: str) -> Tuple[str, str]:
        path = (path or "").strip()
        if not path:
            return "", "✗ Укажите путь к новой папке"
        path = os.path.abspath(path)
        try:
            os.makedirs(path, exist_ok=True)
            kb = os.path.join(path, KB_FILENAME)
            if not os.path.isfile(kb):
                template = (
                    "% Новый проект PyAgentProlog.\n"
                    "% my_actions.py рядом с kb.pl будет загружен автоматически.\n\n"
                    "start :-\n"
                    "    write('Hello, PyAgentProlog!'), nl.\n"
                )
                with open(kb, "w", encoding="utf-8") as f:
                    f.write(template)
            self.set_project(path)
            text, msg = self.load_kb_from_project()
            return (text if text else gr.update()), msg
        except Exception as e:  # noqa: BLE001
            return gr.update(), f"✗ {e}\n{traceback.format_exc()}"

    # ------------------------------------------------------------------
    # Программа
    # ------------------------------------------------------------------
    def load_program(self, text: str) -> str:
        try:
            self.agent = None
            self._signature = None
            self._actions_sig = None
            agent = self._ensure_agent(text)
            n = len(agent.solver.database.rules)
            acts = len(self.get_actions())
            return (f"✓ Загружено: {n} правил(о); действий: {acts}; "
                    f"проект: {self.project_dir or '—'}")
        except Exception as e:  # noqa: BLE001
            return f"✗ {e}\n{traceback.format_exc()}"

    def check_program(self, text: str) -> str:
        try:
            rules = Parser(text).parse_rules()
            return f"✓ Синтаксис OK: {len(rules)} правил(о)"
        except Exception as e:  # noqa: BLE001
            return f"✗ {e}"

    # ------------------------------------------------------------------
    # Запросы
    # ------------------------------------------------------------------
    def run_query(self, text: str, query: str, timeout: float
                  ) -> Tuple[Dict, str]:
        try:
            if not query.strip():
                return {}, "✗ Пустой запрос"
            agent = self._ensure_agent(text)
            res = _run_with_timeout(lambda: agent.query(query), timeout)
            out = res.get("output", "") if isinstance(res, dict) else str(res)
            n = res.get("count", 1) if isinstance(res, dict) else 1
            self.history.append({"q": query, "ok": True})
            return res, f"{out}\n── {n} решение(й) ──"
        except TimeoutError as e:
            return {"error": str(e)}, f"⏱ {e}"
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}, f"✗ {e}"

    def run_first(self, text: str, query: str, timeout: float
                  ) -> Tuple[Dict, str]:
        try:
            if not query.strip():
                return {}, "✗ Пустой запрос"
            agent = self._ensure_agent(text)
            res = _run_with_timeout(lambda: agent.query_one(query), timeout)
            if res is None:
                return {"solution": None}, "✗ Нет решений"
            if isinstance(res, dict) and res.get("__success__"):
                return {"success": True}, "✓ true"
            return res, f"✓ {json.dumps(res, ensure_ascii=False, default=str)}"
        except TimeoutError as e:
            return {"error": str(e)}, f"⏱ {e}"
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}, f"✗ {e}"

    def run_stream(self, text: str, query: str,
                   per_item_timeout: float = 30.0):
        if not query.strip():
            yield "✗ Пустой запрос"
            return
        try:
            agent = self._ensure_agent(text)
        except Exception as e:  # noqa: BLE001
            yield f"✗ {e}"
            return
        lines: List[str] = []
        yielded = False
        for sol in stream_with_timeout(agent, query, per_item_timeout):
            if isinstance(sol, dict) and "error" in sol:
                yield f"✗ {sol['error']}"
                return
            if sol is False:
                continue
            lines.append(json.dumps(sol, ensure_ascii=False, default=str))
            yielded = True
            yield "\n".join(lines)
        if not yielded:
            yield "Нет решений"

    # ------------------------------------------------------------------
    # Трассировка + breakpoints
    # ------------------------------------------------------------------
    def run_traced(self, text: str, query: str, timeout: float,
                   bp_string: str):
        predicates = [p.strip() for p in (bp_string or "").split(",") if p.strip()]
        self.controller.set_breakpoints(predicates)
        self.controller.reset()

        if not query.strip():
            yield self._final_state("✗ Пустой запрос", {}, "✗ Пустой запрос")
            return
        try:
            agent = self._ensure_agent(text)
        except Exception as e:  # noqa: BLE001
            yield self._final_state(f"✗ {e}", {"error": str(e)}, f"✗ {e}")
            return

        original_tracer = agent.solver.database.tracer
        agent.solver.database.tracer = BreakpointTracer(self.controller)

        result_box: Dict[str, Any] = {}
        error_box: Dict[str, Any] = {}
        stop = threading.Event()

        def worker():
            try:
                result_box["v"] = agent.query(query, with_explanation=True)
            except AbortException:
                result_box["aborted"] = True
            except BaseException as e:  # noqa: BLE001
                error_box["e"] = e
            finally:
                stop.set()

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        yield self._running_state()

        last_paused = False
        start = time.time()
        try:
            while not stop.is_set():
                paused = self.controller.paused
                if paused != last_paused:
                    last_paused = paused
                    if paused:
                        yield self._paused_state(self.controller.current_step)
                    else:
                        yield self._running_state()
                if time.time() - start > timeout:
                    self.controller.resume("abort")
                    error_box["e"] = TimeoutError(f"Таймаут {timeout}s")
                    break
                time.sleep(0.05)
        finally:
            agent.solver.database.tracer = original_tracer

        if result_box.get("aborted"):
            yield self._final_state("⛔ Aborted", {}, "Aborted")
            return
        if "e" in error_box:
            err = error_box["e"]
            tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
            yield self._final_state(f"✗ {err}",
                                    {"error": str(err), "traceback": tb},
                                    f"✗ {err}\n{tb}")
            return

        result, explanation = result_box["v"]
        out = result.get("output", "") if isinstance(result, dict) else str(result)
        n = result.get("count", 1) if isinstance(result, dict) else 1
        root_steps = explanation.root_steps if explanation else []
        tree_html = render_tree_html(root_steps)
        rows, dicts = build_trace_artifacts(root_steps)

        yield (
            f"✓ Готово. BP hit: {self.controller.hit_count}",
            gr.update(interactive=False),
            gr.update(interactive=False),
            gr.update(interactive=False),
            result,
            f"{out}\n── {n} решение(й) ──",
            tree_html,
            rows,
            dicts,
        )

    def _running_state(self):
        return (
            f"▶ Работает... Hit: {self.controller.hit_count}",
            gr.update(interactive=False),
            gr.update(interactive=False),
            gr.update(interactive=False),
            gr.update(), gr.update(), "", [], [],
        )

    def _paused_state(self, step: Optional[Any]):
        info = step.goal if step else "?"
        if step and step.rule_used:
            info += f" (rule: {step.rule_used})"
        return (
            f"⏸ Пауза: {info} | Hit: {self.controller.hit_count}",
            gr.update(interactive=True),
            gr.update(interactive=True),
            gr.update(interactive=True),
            gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
        )

    def _final_state(self, status: str, result_json, result_text: str):
        return (
            status,
            gr.update(interactive=False),
            gr.update(interactive=False),
            gr.update(interactive=False),
            result_json, result_text, "", [], [],
        )

    # ------------------------------------------------------------------
    # KB / Actions
    # ------------------------------------------------------------------
    def get_kb(self, text: str) -> List[Dict]:
        try:
            agent = self._ensure_agent(text)
            return [
                {
                    "index": i,
                    "head": str(r.head),
                    "body": "" if str(r.body) == "true" else str(r.body),
                    "rule": str(r),
                }
                for i, r in enumerate(agent.solver.database.rules)
            ]
        except Exception as e:  # noqa: BLE001
            return [{"error": str(e)}]

    def get_index(self, text: str) -> Dict:
        try:
            agent = self._ensure_agent(text)
            return {
                f"{name}/{arity}": {
                    "rules": len(entry["all"]),
                    "const_keys": [str(k) for k in entry["const"]],
                }
                for (name, arity), entry in agent.solver.database.rule_index.items()
            }
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def get_actions(self) -> List[Dict]:
        return self.agent.list_actions() if self.agent else []

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------
    def context_set(self, key: str, value_repr: str) -> str:
        try:
            key = (key or "").strip()
            if not key:
                return "✗ Ключ пустой"
            value = eval(value_repr, {"__builtins__": __builtins__}, {})  # noqa: S307
            self.context.set(key, value)
            if self.agent is not None:
                self.agent.context[key] = value
            return f"✓ context['{key}'] = {type(value).__name__}"
        except Exception as e:  # noqa: BLE001
            return f"✗ {e}\n{traceback.format_exc()}"

    def context_delete(self, key: str) -> str:
        key = (key or "").strip()
        if not key:
            return "✗ Ключ пустой"
        self.context.values.pop(key, None)
        if self.agent is not None:
            self.agent.context.pop(key, None)
        return f"✓ context['{key}'] удалён"

    def context_list(self) -> List[Dict]:
        return [
            {"key": k, "type": type(v).__name__, "repr": repr(v)[:120]}
            for k, v in self.context.values.items()
        ]

    def context_apply(self, text: str) -> str:
        try:
            new_ctx = self.context.apply()
            self.agent = None
            self._signature = None
            self._ensure_agent(text)
            return f"✓ context применён; ключей: {len(new_ctx)}"
        except Exception as e:  # noqa: BLE001
            return f"✗ {e}\n{traceback.format_exc()}"

    # ------------------------------------------------------------------
    # Semantic
    # ------------------------------------------------------------------
    def semantic_status(self) -> Dict:
        try:
            from prolog.embedding_unify import semantic_status
            return semantic_status()
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def semantic_enable(self, backend: str, model: str, threshold: float,
                        soft: float, lev_max: float, lev_typo: float,
                        local_path: str = "", local_only: bool = False
                        ) -> Tuple[str, Dict[str, Any]]:
        try:
            from prolog.embedding_unify import (
                detect_text_prefix,
                resolve_model_id,
                semantic_on,
                semantic_status,
            )

            local_path = (local_path or "").strip()

            if backend == "st" and local_path:
                if os.path.isdir(local_path):
                    prefix = detect_text_prefix(resolve_model_id(model))
                    semantic_on(
                        threshold=threshold, backend=backend, model=local_path,
                        soft_cos_min=soft, lev_max=lev_max,
                        lev_typo_max=lev_typo,
                        text_prefix=prefix,
                        st_local_files_only=True,
                    )
                    return (
                        f"✓ Semantic: st (local)\n  {local_path}",
                        semantic_status(),
                    )

                if local_only:
                    return (
                        f"✗ Локальная папка модели не найдена: {local_path}\n"
                        f"  local_only=True — загрузка с HF отключена.",
                        {"enabled": False,
                         "error": f"local path not found: {local_path}"},
                    )

                semantic_on(
                    threshold=threshold, backend=backend, model=model,
                    soft_cos_min=soft, lev_max=lev_max,
                    lev_typo_max=lev_typo,
                )
                return (
                    f"✓ Semantic: st (HF fallback)\n  {model}\n"
                    f"  ⚠ Локальная папка не найдена: {local_path}",
                    semantic_status(),
                )

            semantic_on(
                threshold=threshold, backend=backend, model=model,
                soft_cos_min=soft, lev_max=lev_max,
                lev_typo_max=lev_typo,
                st_local_files_only=(local_only if backend == "st" else False),
            )
            return f"✓ Semantic: {backend}/{model}", semantic_status()

        except ImportError as e:
            msg = (f"✗ {e}\n"
                   f"  💡 backend='st' requires: pip install sentence-transformers")
            return msg, {"enabled": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001
            msg = (f"✗ {e}\n"
                   f"  💡 ollama: сервер на http://localhost:11434\n"
                   f"  💡 st:     pip install sentence-transformers")
            return msg, {"enabled": False, "error": str(e)}

    def semantic_disable(self) -> Tuple[str, Dict[str, Any]]:
        try:
            from prolog.embedding_unify import semantic_off, semantic_status
            semantic_off()
            return "✓ Semantic отключён", semantic_status()
        except Exception as e:  # noqa: BLE001
            return f"✗ {e}", {"enabled": False, "error": str(e)}

    def semantic_set_threshold(self, value: float
                               ) -> Tuple[str, Dict[str, Any]]:
        try:
            from prolog.embedding_unify import (
                semantic_get_unifier, semantic_set_threshold, semantic_status,
            )
            if semantic_get_unifier() is None:
                return "✗ Semantic не включён", semantic_status()
            semantic_set_threshold(value)
            return f"✓ Threshold = {value}", semantic_status()
        except Exception as e:  # noqa: BLE001
            return f"✗ {e}", {"enabled": False, "error": str(e)}

    def semantic_compare(self, a: str, b: str) -> Dict[str, Any]:
        """Диагностика пары строк через активный semantic unifier."""
        from prolog.embedding_unify import (
            _lev_ratio, _normalize_text, semantic_get_unifier,
        )
        u = semantic_get_unifier()
        if u is None:
            return {"error": "semantic не включён — нажмите ✅ ON"}

        s1 = _normalize_text(a or "")
        s2 = _normalize_text(b or "")
        if not s1 or not s2:
            return {"error": "оба поля должны быть непустыми"}

        lev = _lev_ratio(s1, s2)
        try:
            v1 = u._embed(s1)
            v2 = u._embed(s2)
            cos = u._cosine(v1, v2)
        except Exception as e:  # noqa: BLE001
            return {"error": f"embed failed: {e}"}

        if s1 == s2:
            verdict = "exact"
        elif lev <= u.lev_typo_max:
            verdict = "typo"
        elif cos >= u.threshold:
            verdict = "hard"
        elif cos >= u.soft_cos_min and lev <= u.lev_max:
            verdict = "soft"
        else:
            verdict = "NONE"

        result: Dict[str, Any] = {
            "a": s1, "b": s2,
            "cos": round(cos, 4),
            "lev": round(lev, 4),
            "verdict": verdict,
            "threshold": u.threshold,
            "soft_cos_min": u.soft_cos_min,
            "lev_max": u.lev_max,
            "lev_typo_max": u.lev_typo_max,
        }

        if verdict == "NONE":
            hints: List[str] = []
            if cos >= u.soft_cos_min and cos < u.threshold and lev > u.lev_max:
                hints.append(
                    f"cos={cos:.3f} в soft-коридоре, но lev={lev:.3f} > "
                    f"lev_max={u.lev_max} → увеличьте Lev max до "
                    f"{round(lev + 0.05, 2)}"
                )
            if cos < u.soft_cos_min and lev <= u.lev_max:
                hints.append(
                    f"lev={lev:.3f} в норме, но cos={cos:.3f} < "
                    f"soft_cos_min={u.soft_cos_min} → уменьшите Soft cos min до "
                    f"{max(0.0, round(cos - 0.05, 2))}"
                )
            if cos < u.soft_cos_min and lev > u.lev_max:
                hints.append(
                    f"и cos={cos:.3f} < {u.soft_cos_min}, и lev={lev:.3f} > "
                    f"{u.lev_max} → уменьшите Soft cos min до "
                    f"{max(0.0, round(cos - 0.05, 2))} И увеличьте Lev max до "
                    f"{round(lev + 0.05, 2)}"
                )
            if cos >= u.soft_cos_min and lev <= u.lev_max:
                hints.append(
                    "внутреннее противоречие: параметры в норме, но вердикт NONE — "
                    "проверьте _semantic_match"
                )
            result["hints"] = hints

        return result

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def diagnostics(self) -> Dict:
        d: Dict[str, Any] = {
            "agent": {
                "rules": len(self.agent.solver.database.rules) if self.agent else 0,
                "actions": len(self.get_actions()),
            },
            "project": self.get_project_info(),
            "context": self.context_list(),
            "semantic": self.semantic_status(),
            "history": self.history[-10:],
        }
        try:
            from prolog.predicates import arith_numba_status
            d["numba"] = arith_numba_status()
        except Exception:  # noqa: BLE001
            d["numba"] = {"available": False}
        return d


# =====================================================================
# UI handlers
# =====================================================================
def _project_info_html(info: Dict[str, Any]) -> str:
    if not info or not info.get("project_dir"):
        return '<div class="proj-info">Проект не выбран</div>'
    lines = [
        f"<b>Проект:</b> {_esc(info['project_dir'])}",
        f"kb.pl: {_esc(os.path.basename(info.get('kb') or '—'))}",
        f"my_actions.py: {'есть' if info.get('my_actions') else '—'}",
    ]
    return f'<div class="proj-info">{"<br>".join(lines)}</div>'


def _sem_badge_html(status: Dict[str, Any]) -> str:
    """Визуальный бейдж: 🟢 ON / 🔴 OFF + краткая информация."""
    if not status or not status.get("enabled"):
        err = (status or {}).get("error")
        suffix = f" — <span style='color:#ff7b72'>{_esc(err)}</span>" if err else ""
        return (
            '<div class="proj-info">'
            '<b style="color:#ff7b72">🔴 OFF</b>'
            f' Semantic unifier выключен{suffix}'
            '</div>'
        )
    backend = status.get("backend", "?")
    thr = status.get("threshold")
    cos = status.get("soft_cos_min")
    custom = "custom" if status.get("has_custom_embed_fn") else "builtin"
    return (
        '<div class="proj-info">'
        '<b style="color:#7ee787">🟢 ON</b>'
        f' backend=<code>{_esc(str(backend))}</code>'
        f' threshold=<b>{thr}</b>'
        f' soft_cos_min=<b>{cos}</b>'
        f' ({_esc(custom)})'
        '</div>'
    )


def handle_sem_status_html(sid):
    return _sem_badge_html(_get_ide(sid).semantic_status())


# --- Открыть -------------------------------------------------------
def handle_open_project(sid, path: str):
    """Открыть проект. Пусто → диалог выбора .pl (файлы видны)."""
    ide = _get_ide(sid)
    path = (path or "").strip()
    if not path:
        picked = _pick_pl_file(
            initial=examples_root() if os.path.isdir(examples_root()) else "",
            title="Открыть проект — выберите .pl файл из папки проекта",
        )
        if not picked:
            return (gr.update(), gr.update(),
                    _project_info_html(ide.get_project_info()),
                    _status_html("✗ Файл не выбран"))
        path = picked
    msg = ide.set_project(path)
    if msg.startswith("✗"):
        return (gr.update(), path,
                _project_info_html(ide.get_project_info()),
                _status_html(msg))
    text, load_msg = ide.load_kb_from_project()
    return (
        text if text else gr.update(),
        path,
        _project_info_html(ide.get_project_info()),
        _status_html(load_msg),
    )


# --- Создать -------------------------------------------------------
def handle_new_project(sid, path: str):
    """Всегда открывает диалог выбора/создания папки."""
    ide = _get_ide(sid)
    path = (path or "").strip()
    picked = _pick_folder(
        initial=path or os.path.expanduser("~"),
        title="Выберите папку для нового проекта (можно создать)",
    )
    if not picked:
        return (gr.update(), gr.update(),
                _project_info_html(ide.get_project_info()),
                _status_html("✗ Папка не выбрана"))
    text, msg = ide.new_project(picked)
    return (
        text if text else gr.update(),
        picked,
        _project_info_html(ide.get_project_info()),
        _status_html(msg),
    )


# --- Сохранить -----------------------------------------------------
def handle_save_project(sid, text: str, path: str):
    """Сохранить в папку из поля. Пусто → в текущий проект."""
    ide = _get_ide(sid)
    path = (path or "").strip()
    if path:
        path_abs = os.path.abspath(path)
        if (not ide.project_dir) or path_abs != ide.project_dir:
            m = ide.set_project(path)
            if m.startswith("✗"):
                return _status_html(m)
    if not ide.project_dir:
        return _status_html("✗ Проект не выбран")
    return _status_html(ide.save_project(text))


# --- Открыть пример (shortcut) -------------------------------------
def handle_open_example(sid):
    """Открывает диалог выбора .pl в папке examples/."""
    ide = _get_ide(sid)
    root = examples_root()
    if not os.path.isdir(root):
        return (gr.update(), gr.update(),
                _project_info_html(ide.get_project_info()),
                _status_html(f"✗ Папка examples не найдена: {root}"))
    picked = _pick_pl_file(
        initial=root,
        title="Выберите пример — откройте kb.pl из папки примера",
    )
    if not picked:
        return (gr.update(), gr.update(),
                _project_info_html(ide.get_project_info()),
                _status_html("✗ Пример не выбран"))
    msg = ide.set_project(picked)
    if msg.startswith("✗"):
        return (gr.update(), picked,
                _project_info_html(ide.get_project_info()),
                _status_html(msg))
    text, load_msg = ide.load_kb_from_project()
    return (
        text if text else gr.update(),
        picked,
        _project_info_html(ide.get_project_info()),
        _status_html(load_msg),
    )


# --- Drag-drop .pl в редактор (не меняет проект) -------------------
def handle_drop_pl(sid, f):
    """Drop .pl → загрузить содержимое в редактор."""
    if f is None:
        return gr.update(), _status_html("✗ Файл не выбран")
    try:
        path = f.name if hasattr(f, "name") else str(f)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        return (
            text,
            _status_html(
                f"ℹ Загружено в редактор: {os.path.basename(path)}\n"
                "  ⚠ Drag-drop всегда копирует файл во временную папку Gradio.\n"
                "  Папка проекта не определена автоматически.\n"
                "  Укажите путь в поле выше и нажмите 📂 Открыть,\n"
                "  либо перетащите файл в папку-проект заранее."
            ),
        )
    except Exception as e:  # noqa: BLE001
        return gr.update(), _status_html(f"✗ {e}")


# --- Прочее --------------------------------------------------------
def handle_project_info(sid):
    return _project_info_html(_get_ide(sid).get_project_info())


def handle_reload(sid, text):
    return _status_html(_get_ide(sid).load_program(text))


def handle_check(sid, text):
    return _status_html(_get_ide(sid).check_program(text))


def handle_run(sid, text, query, timeout):
    return _get_ide(sid).run_query(text, query, _to_timeout(timeout))


def handle_first(sid, text, query, timeout):
    return _get_ide(sid).run_first(text, query, _to_timeout(timeout))


def handle_stream(sid, text, query, timeout):
    yield from _get_ide(sid).run_stream(text, query, _to_timeout(timeout))


def handle_trace(sid, text, query, timeout, bp_string):
    yield from _get_ide(sid).run_traced(
        text, query, _to_timeout(timeout), bp_string,
    )


def handle_bp_resume(sid, action):
    _get_ide(sid).controller.resume(action)
    return gr.update()


def handle_bp_reset(sid):
    _get_ide(sid).controller.reset()
    return "Сброшено."


def handle_step_select(evt: gr.SelectData, steps_state):
    try:
        idx = evt.index[0] if isinstance(evt.index, (tuple, list)) else evt.index
        if 0 <= int(idx) < len(steps_state):
            return subst_rows_from_dict(steps_state[int(idx)])
    except Exception:  # noqa: BLE001
        pass
    return []


def handle_kb(sid, text):
    ide = _get_ide(sid)
    return ide.get_kb(text), ide.get_index(text)


def handle_actions(sid):
    return _get_ide(sid).get_actions()


def handle_ctx_set(sid, key, value_repr):
    return _get_ide(sid).context_set(key, value_repr)


def handle_ctx_delete(sid, key):
    return _get_ide(sid).context_delete(key)


def handle_ctx_list(sid):
    return _get_ide(sid).context_list()


def handle_ctx_apply(sid, text):
    return _get_ide(sid).context_apply(text)


def handle_sem_status(sid):
    return _get_ide(sid).semantic_status()


def handle_sem_enable(sid, backend, model, threshold, soft, lev_max,
                      lev_typo, local_path, local_only):
    return _get_ide(sid).semantic_enable(
        backend, model,
        float(threshold), float(soft),
        float(lev_max), float(lev_typo),
        local_path=local_path or "",
        local_only=bool(local_only),
    )


def handle_sem_disable(sid):
    return _get_ide(sid).semantic_disable()


def handle_sem_threshold(sid, value):
    return _get_ide(sid).semantic_set_threshold(float(value))


def handle_sem_compare(sid, a, b):
    return _get_ide(sid).semantic_compare(a, b)


def handle_diag(sid):
    return _get_ide(sid).diagnostics()


# =====================================================================
# UI
# =====================================================================
def build_ui() -> gr.Blocks:
    with gr.Blocks(**blocks_kwargs(_GLOBAL_CSS, _HEAD_DARK)) as ui:
        session_state = gr.State(None)
        steps_state = gr.State([])

        ui.load(fn=new_session, outputs=[session_state])

        with gr.Row(equal_height=False):
            # ============================================================
            # COLUMN 1: Проект и настройки
            # ============================================================
            with gr.Column(scale=2, min_width=300):
                gr.HTML('<div class="col-head">📁 Проект</div>')

                pl_input = gr.File(
                    show_label=False,
                    file_types=[".pl", ".prolog", ".txt"],
                    file_count="single",
                )
                project_path = gr.Textbox(
                    placeholder="Путь к папке проекта "
                                "(напр. D:\\Projects\\my_prolog)",
                    show_label=False,
                    elem_classes=["compact-tb"],
                )
                with gr.Row(equal_height=True):
                    open_btn = gr.Button("📂 Открыть", size="sm", scale=2,
                                         elem_classes=["compact-btn"])
                    new_btn = gr.Button("🆕 Создать", size="sm", scale=2,
                                        elem_classes=["compact-btn"])
                    save_btn = gr.Button("💾 Сохранить", size="sm", scale=2,
                                         elem_classes=["compact-btn"])
                    example_btn = gr.Button("📚", size="sm", scale=1,
                                            elem_classes=["compact-btn"])

                project_status = gr.HTML(
                    value='<div class="proj-info">Проект не выбран</div>',
                )
                examples_hint = gr.HTML(
                    value=(
                        '<div class="proj-info">📚 Примеры: '
                        f'<code>{_esc(examples_root())}</code></div>'
                    ),
                )

                with gr.Accordion("🔌 Контекст (context)", open=False):
                    with gr.Row(equal_height=True):
                        ctx_key = gr.Textbox(
                            placeholder="ключ (llm, db, ...)",
                            show_label=False, scale=2,
                            elem_classes=["compact-tb"],
                        )
                    ctx_val = gr.Textbox(
                        placeholder="Python-выражение",
                        lines=2,
                        elem_classes=["compact-tb"],
                    )
                    with gr.Row(equal_height=True):
                        ctx_set_btn = gr.Button("➕", size="sm",
                                                elem_classes=["compact-btn"])
                        ctx_del_btn = gr.Button("🗑️", size="sm",
                                                elem_classes=["compact-btn"])
                        ctx_apply_btn = gr.Button("🔄 Применить", size="sm",
                                                  elem_classes=["compact-btn"])
                    ctx_status = gr.Textbox(
                        label="", show_label=False, lines=1,
                        interactive=False, elem_classes=["compact-tb"],
                    )
                    with gr.Row(equal_height=True):
                        refresh_ctx = gr.Button("🔄 Список", size="sm",
                                                elem_classes=["compact-btn"])
                    ctx_json = gr.JSON(label="", show_label=False, value=[])

                with gr.Accordion("🧬 Semantic", open=False):
                    sem_badge = gr.HTML(
                        value='<div class="proj-info">🔴 OFF Semantic unifier выключен</div>'
                    )
                    with gr.Row(equal_height=True):
                        sem_status_json = gr.JSON(label="", show_label=False)
                        refresh_sem = gr.Button("🔄", size="sm",
                                                elem_classes=["compact-btn"])

                    sem_backend = gr.Dropdown(
                        choices=["st", "ollama"], value="st",
                        label="Backend", elem_classes=["compact-lbl"],
                    )
                    sem_model = gr.Textbox(
                        label="Model (имя/ID для префикса и fallback)",
                        value="paraphrase-multilingual-mpnet",
                        elem_classes=["compact-tb", "compact-lbl"],
                    )
                    sem_local_path = gr.Textbox(
                        label="Local path (точный путь к папке HF-модели, опционально)",
                        value=r"D:\hf_embedding\paraphrase-multilingual-mpnet",
                        placeholder=r"D:\hf_embedding\paraphrase-multilingual-mpnet",
                        elem_classes=["compact-tb", "compact-lbl"],
                    )
                    sem_local_only = gr.Checkbox(
                        label="Только локально (не скачивать с HF)",
                        value=False,
                        elem_classes=["compact-lbl"],
                    )

                    sem_threshold = gr.Slider(0.0, 1.0, 0.82, 0.01,
                                              label="Threshold")
                    sem_soft = gr.Slider(0.0, 1.0, 0.55, 0.01,
                                         label="Soft cos min")
                    sem_lev_max = gr.Slider(0.0, 1.0, 0.55, 0.01,
                                            label="Lev max")
                    sem_lev_typo = gr.Slider(0.0, 1.0, 0.20, 0.01,
                                             label="Lev typo max")

                    gr.Markdown(
                        "**`st`** — `pip install sentence-transformers`  \n"
                        "**`ollama`** — сервер на `http://localhost:11434`  \n"
                        "**Local path** заполнен и папка есть → **только локально** "
                        "(без сети).  \n"
                        "Если папки нет → fallback на HF (если не включён "
                        "«Только локально»).",
                    )
                    with gr.Row(equal_height=True):
                        sem_on_btn = gr.Button("✅ ON", size="sm",
                                               elem_classes=["compact-btn"])
                        sem_off_btn = gr.Button("❌ OFF", size="sm",
                                                elem_classes=["compact-btn"])
                        sem_set_btn = gr.Button("🔧 Thr", size="sm",
                                                elem_classes=["compact-btn"])
                    sem_msg = gr.Textbox(label="", show_label=False,
                                         interactive=False, lines=3,
                                         elem_classes=["compact-tb"])

                    gr.Markdown("### 🔬 Проверка пары строк")
                    with gr.Row(equal_height=True):
                        sem_test_a = gr.Textbox(
                            placeholder="A (moskva)", show_label=False, scale=1,
                            elem_classes=["compact-tb"],
                        )
                        sem_test_b = gr.Textbox(
                            placeholder="B (moscow)", show_label=False, scale=1,
                            elem_classes=["compact-tb"],
                        )
                        sem_test_btn = gr.Button("🔬", size="sm",
                                                 elem_classes=["compact-btn"])
                    sem_test_json = gr.JSON(label="", show_label=False)

                with gr.Accordion("🔬 Диагностика", open=False):
                    diag_btn = gr.Button("🔄 Обновить", size="sm",
                                         elem_classes=["compact-btn"])
                    diag_json = gr.JSON(label="", show_label=False)

            # ============================================================
            # COLUMN 2: Редактор кода
            # ============================================================
            with gr.Column(scale=5, min_width=500):
                gr.HTML('<div class="col-head">📝 Программа</div>')

                editor = gr.Code(
                    language=code_language(),
                    lines=28,
                    value="",
                    show_label=False,
                )
                with gr.Row(equal_height=True):
                    reload_btn = gr.Button("🔄 Перезагрузить", size="sm",
                                           elem_classes=["compact-btn"])
                    check_btn = gr.Button("✓ Синтаксис", size="sm",
                                          elem_classes=["compact-btn"])
                    clear_btn = gr.Button("🗑️ Очистить", size="sm",
                                          elem_classes=["compact-btn"])
                editor_status = gr.HTML(
                    value=(
                        '<pre class="status-box">'
                        'Готов. Откройте проект (📂) или создайте новый (🆕).'
                        '</pre>'
                    ),
                )

                with gr.Accordion("⚡ Зарегистрированные действия",
                                  open=False) as actions_acc:
                    actions_json = gr.JSON(label="", show_label=False, value=[])
                actions_acc.expand(handle_actions, [session_state], [actions_json])

                with gr.Accordion("📚 База знаний", open=False) as kb_acc:
                    with gr.Row():
                        kb_json = gr.JSON(label="Правила")
                        index_json = gr.JSON(label="Индекс")
                kb_acc.expand(handle_kb, [session_state, editor],
                              [kb_json, index_json])

            # ============================================================
            # COLUMN 3: Запрос и отладка
            # ============================================================
            with gr.Column(scale=4, min_width=420):
                gr.HTML('<div class="col-head">🔎 Запрос</div>')

                query_input = gr.Textbox(
                    placeholder="parent(ivan, X).",
                    lines=2, show_label=False,
                    elem_classes=["compact-tb"],
                )

                gr.HTML('<div class="col-head">▶ Таймауты и выполнение</div>')

                # --- Timeout, Кнопки Run/First/Stream/Stop: отдельный ряд под Timeout ---
                with gr.Row(equal_height=True, elem_classes=["tiny-row"]):
                    ## --- Timeout: одно поле в своём ряду ---
                    timeout_input = gr.Number(
                        value=30.0,
                        minimum=0.5,
                        maximum=600.0,
                        #scale=1,
                        show_label=False,
                        elem_classes=["compact-lbl"],
                    )
                    run_btn = gr.Button("▶", size="sm", variant="primary", scale=1,
                                        min_width=0, elem_classes=["tiny-btn"])
                    first_btn = gr.Button("⏩", size="sm", scale=1,
                                          min_width=0, elem_classes=["tiny-btn"])
                    stream_btn = gr.Button("📡", size="sm", scale=1,
                                           min_width=0, elem_classes=["tiny-btn"])
                    stop_btn = gr.Button("⏹", size="sm", scale=1,
                                         min_width=0, elem_classes=["tiny-btn"])

                with gr.Accordion("Результат", open=True):
                    results_out = gr.Textbox(
                        label="", show_label=False, lines=8,
                        interactive=False,
                    )
                    results_json = gr.JSON(label="", show_label=False)

                stream_out = gr.Textbox(
                    label="Stream", lines=4, interactive=False,
                    elem_classes=["compact-tb"],
                )

                gr.HTML('<div class="col-head">🐛 Трассировка</div>')

                # --- Trace-кнопки: отдельный ряд под bp_predicates ---
                with gr.Row(equal_height=True, elem_classes=["tiny-row"]):
                    # --- Breakpoints:  ---
                    bp_predicates = gr.Textbox(
                        placeholder="breakpoints: loop, grandparent",
                        show_label=False,
                        elem_classes=["compact-tb"],
                    )
                    trace_btn = gr.Button("🔍", size="sm", variant="primary", scale=1,
                                          min_width=0, elem_classes=["tiny-btn"])
                    bp_continue = gr.Button("⏵", size="sm", interactive=False, scale=1,
                                            min_width=0, elem_classes=["tiny-btn"])
                    bp_step = gr.Button("⏭", size="sm", interactive=False, scale=1,
                                        min_width=0, elem_classes=["tiny-btn"])
                    bp_abort = gr.Button("⛔", size="sm", interactive=False, scale=1,
                                         min_width=0, elem_classes=["tiny-btn"])
                    bp_reset = gr.Button("↺", size="sm", scale=1,
                                         min_width=0, elem_classes=["tiny-btn"])

                bp_status = gr.Textbox(
                    label="", show_label=False, interactive=False, lines=1,
                    elem_classes=["compact-tb"],
                )

                trace_html = gr.HTML()
                gr.Markdown("**Шаги** (клик — subst)")
                steps_df = gr.Dataframe(
                    headers=["id", "goal", "rule", "ok", "kind"],
                    datatype=["str"] * 5,
                    type="array",
                    interactive=False,
                    wrap=True,
                    label="",
                    elem_id="steps_df",
                )
                gr.Markdown("**subst**")
                subst_df = gr.Dataframe(
                    headers=["var", "before", "after"],
                    datatype=["str"] * 3,
                    type="array",
                    interactive=False,
                    wrap=True,
                    label="",
                    elem_id="subst_df",
                )

        # ================ Wiring ================
        # --- Проект ---
        pl_input.change(
            handle_drop_pl, [session_state, pl_input],
            [editor, editor_status],
        )
        open_btn.click(
            handle_open_project, [session_state, project_path],
            [editor, project_path, project_status, editor_status],
        )
        new_btn.click(
            handle_new_project, [session_state, project_path],
            [editor, project_path, project_status, editor_status],
        )
        save_btn.click(
            handle_save_project, [session_state, editor, project_path],
            [editor_status],
        )
        example_btn.click(
            handle_open_example, [session_state],
            [editor, project_path, project_status, editor_status],
        )

        # --- Context ---
        ctx_set_btn.click(
            handle_ctx_set, [session_state, ctx_key, ctx_val], [ctx_status],
        )
        ctx_del_btn.click(
            handle_ctx_delete, [session_state, ctx_key], [ctx_status],
        )
        ctx_apply_btn.click(
            handle_ctx_apply, [session_state, editor], [ctx_status],
        )
        refresh_ctx.click(handle_ctx_list, [session_state], [ctx_json])

        # --- Semantic ---
        refresh_sem.click(
            handle_sem_status,
            [session_state],
            [sem_status_json],
        ).then(
            handle_sem_status_html, [session_state], [sem_badge],
        )

        sem_on_btn.click(
            handle_sem_enable,
            [session_state, sem_backend, sem_model,
             sem_threshold, sem_soft, sem_lev_max, sem_lev_typo,
             sem_local_path, sem_local_only],
            [sem_msg, sem_status_json],
        ).then(
            handle_sem_status_html, [session_state], [sem_badge],
        )

        sem_off_btn.click(
            handle_sem_disable,
            [session_state],
            [sem_msg, sem_status_json],
        ).then(
            handle_sem_status_html, [session_state], [sem_badge],
        )

        sem_set_btn.click(
            handle_sem_threshold,
            [session_state, sem_threshold],
            [sem_msg, sem_status_json],
        ).then(
            handle_sem_status_html, [session_state], [sem_badge],
        )

        sem_test_btn.click(
            handle_sem_compare,
            [session_state, sem_test_a, sem_test_b],
            [sem_test_json],
        )

        # --- Diagnostics ---
        diag_btn.click(handle_diag, [session_state], [diag_json])

        # --- Editor ---
        reload_btn.click(handle_reload, [session_state, editor],
                         [editor_status])
        check_btn.click(handle_check, [session_state, editor],
                        [editor_status])
        clear_btn.click(
            lambda: ("", _status_html("Очищено")),
            [], [editor, editor_status],
        )

        # --- Query / Stream ---
        run_btn.click(
            handle_run,
            [session_state, editor, query_input, timeout_input],
            [results_json, results_out],
        )
        first_btn.click(
            handle_first,
            [session_state, editor, query_input, timeout_input],
            [results_json, results_out],
        )
        stream_event = stream_btn.click(
            handle_stream,
            [session_state, editor, query_input, timeout_input],
            [stream_out],
        )
        stop_btn.click(fn=lambda: None, cancels=[stream_event])

        # --- Trace ---
        trace_btn.click(
            handle_trace,
            [session_state, editor, query_input, timeout_input, bp_predicates],
            [
                bp_status, bp_continue, bp_step, bp_abort,
                results_json, results_out, trace_html,
                steps_df, steps_state,
            ],
        )
        bp_continue.click(
            lambda sid: handle_bp_resume(sid, "continue"),
            [session_state], [bp_status],
        )
        bp_step.click(
            lambda sid: handle_bp_resume(sid, "step"),
            [session_state], [bp_status],
        )
        bp_abort.click(
            lambda sid: handle_bp_resume(sid, "abort"),
            [session_state], [bp_status],
        )
        bp_reset.click(handle_bp_reset, [session_state], [bp_status])
        steps_df.select(handle_step_select, [steps_state], [subst_df])

        return ui


# =====================================================================
# launch
# =====================================================================
def launch(share: bool = False, host: str = "127.0.0.1",
           port: int = 7860, **kwargs) -> None:
    ui = build_ui()

    kw = dict(
        share=share,
        server_name=host,
        server_port=port,
        inbrowser=True,
    )

    favicon = _ensure_favicon()
    if favicon:
        kw["favicon_path"] = favicon

    kw.update(launch_kwargs(_GLOBAL_CSS, _HEAD_DARK))
    kw.update(kwargs)

    ui.launch(**kw)