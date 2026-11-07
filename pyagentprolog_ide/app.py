"""PyAgentProlog IDE — Gradio Blocks UI.

Dark theme, compact 3-column layout:
  1) project (drag-drop .pl, path field, Open/Create/Save buttons,
     📚 shortcut to examples), context, semantic, diagnostics;
  2) code editor + actions + KB;
  3) query, results, trace, breakpoints.

Examples are separate projects in pyagentprolog_ide/examples/<name>/kb.pl.
The "Example" dropdown has been removed.

i18n: English / Russian, switchable at runtime via PYAGENTPROLOG_IDE_LANG
(same mechanism as the Fona dashboard: TRANSLATIONS table + t()).

(c) 2026 Andrey Vorfolomeev
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
# i18n
# =====================================================================
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        # generic
        "title": "PyAgentProlog IDE",
        "language": "Language",
        "session_lost": "Session not found. Please reload the page.",
        "empty_query": "Empty query",
        "timeout_fmt": "Timeout {s}s",
        "no_solutions": "No solutions",
        "solutions_fmt": "── {n} solution(s) ──",
        "true": "true",

        # columns
        "col_project": "📁 Project",
        "col_program": "📝 Program",
        "col_query": "🔎 Query",

        # project panel
        "project_placeholder":
            "Project folder path (e.g. D:\\Projects\\my_prolog)",
        "btn_open": "📂 Open",
        "btn_new": "🆕 Create",
        "btn_save": "💾 Save",
        "btn_example": "📚",
        "project_not_selected": "Project not selected",
        "project_folder_not_found": "✗ Folder not found: {inp!r}",
        "project_ok": "✓ Project: {dir}",
        "project_kb": "  kb:            {kb}",
        "project_actions": "  my_actions.py: {st}",
        "project_actions_present": "present",
        "project_actions_absent": "—",
        "examples_hint": "📚 Examples: <code>{root}</code>",
        "file_not_selected": "✗ File not selected",
        "folder_not_selected": "✗ Folder not selected",
        "no_project_selected": "✗ Project not selected",
        "no_pl_found": "✗ No .pl file found in {dir}",
        "saved_to": "✓ Saved: {path}",
        "new_project_path_required": "✗ Specify a path for the new folder",
        "open_path_required": "✗ Path required",
        "examples_missing": "✗ Examples folder not found: {root}",
        "example_not_selected": "✗ Example not selected",
        "drop_loaded": (
            "ℹ Loaded into editor: {name}\n"
            "  ⚠ Drag-drop always copies the file to Gradio's temp dir.\n"
            "  Project folder is not detected automatically.\n"
            "  Enter the path above and click 📂 Open,\n"
            "  or drop the file into the project folder beforehand."
        ),
        "status_ready": (
            "Ready. Open a project (📂) or create a new one (🆕)."
        ),
        "status_cleared": "Cleared",

        # context accordion
        "ctx_title": "🔌 Context",
        "ctx_key_placeholder": "key (llm, db, ...)",
        "ctx_val_placeholder": "Python expression",
        "ctx_add": "➕",
        "ctx_del": "🗑️",
        "ctx_apply": "🔄 Apply",
        "ctx_list": "🔄 List",
        "ctx_key_empty": "✗ Key is empty",
        "ctx_set_ok": "✓ context['{key}'] = {type}",
        "ctx_del_ok": "✓ context['{key}'] deleted",
        "ctx_applied": "✓ context applied; keys: {n}",

        # semantic accordion
        "sem_title": "🧬 Semantic",
        "sem_badge_off": "🔴 OFF Semantic unifier is disabled",
        "sem_badge_off_err":
            "🔴 OFF Semantic unifier is disabled — "
            "<span style='color:#ff7b72'>{err}</span>",
        "sem_badge_on":
            "🟢 ON backend=<code>{backend}</code> threshold=<b>{thr}</b> "
            "soft_cos_min=<b>{cos}</b> ({kind})",
        "sem_backend": "Backend",
        "sem_model": "Model (name/ID for prefix and fallback)",
        "sem_local_path":
            "Local path (exact path to the HF model folder, optional)",
        "sem_local_only": "Local only (do not download from HF)",
        "sem_threshold": "Threshold",
        "sem_soft": "Soft cos min",
        "sem_lev_max": "Lev max",
        "sem_lev_typo": "Lev typo max",
        "sem_help": (
            "**`st`** — `pip install sentence-transformers`  \n"
            "**`ollama`** — server at `http://localhost:11434`  \n"
            "**Local path** set and the folder exists → **local only** "
            "(no network).  \n"
            "If the folder is missing → fallback to HF (unless "
            "“Local only” is enabled)."
        ),
        "sem_on": "✅ ON",
        "sem_off": "❌ OFF",
        "sem_thr": "🔧 Thr",
        "sem_test_title": "### 🔬 Compare two strings",
        "sem_test_a": "A (moskva)",
        "sem_test_b": "B (moscow)",
        "sem_test_run": "🔬",
        "sem_disabled": "Semantic is disabled — click ✅ ON",
        "sem_compare_empty": "both fields must be non-empty",
        "sem_enable_st_local": "✓ Semantic: st (local)\n  {path}",
        "sem_enable_st_local_missing":
            "✗ Local model folder not found: {path}\n"
            "  local_only=True — HF download disabled.",
        "sem_enable_st_hf":
            "✓ Semantic: st (HF fallback)\n  {model}\n"
            "  ⚠ Local folder not found: {path}",
        "sem_enable_ok": "✓ Semantic: {backend}/{model}",
        "sem_enable_import":
            "✗ {err}\n  💡 backend='st' requires: "
            "pip install sentence-transformers",
        "sem_enable_err":
            "✗ {err}\n"
            "  💡 ollama: server at http://localhost:11434\n"
            "  💡 st:     pip install sentence-transformers",
        "sem_disabled_ok": "✓ Semantic disabled",
        "sem_thr_ok": "✓ Threshold = {v}",
        "sem_thr_not_enabled": "✗ Semantic is not enabled",
        "sem_hint_lev":
            "cos={cos:.3f} is in the soft corridor, but lev={lev:.3f} > "
            "lev_max={lev_max} → increase Lev max to {suggest}",
        "sem_hint_cos":
            "lev={lev:.3f} is fine, but cos={cos:.3f} < "
            "soft_cos_min={soft} → decrease Soft cos min to {suggest}",
        "sem_hint_both":
            "both cos={cos:.3f} < {soft} and lev={lev:.3f} > {lev_max} "
            "→ decrease Soft cos min to {s1} AND increase Lev max to {s2}",
        "sem_hint_internal":
            "internal inconsistency: parameters are in range but the "
            "verdict is NONE — check _semantic_match",

        # diagnostics
        "diag_title": "🔬 Diagnostics",
        "diag_refresh": "🔄 Refresh",

        # editor
        "btn_reload": "🔄 Reload",
        "btn_check": "✓ Syntax",
        "btn_clear": "🗑️ Clear",
        "actions_title": "⚡ Registered actions",
        "kb_title": "📚 Knowledge base",
        "kb_rules": "Rules",
        "kb_index": "Index",
        "loaded_ok": (
            "✓ Loaded: {n} rule(s); actions: {a}; project: {p}"
        ),
        "syntax_ok": "✓ Syntax OK: {n} rule(s)",

        # query
        "query_placeholder": "parent(ivan, X).",
        "timeouts_title": "▶ Timeouts and execution",
        "result_title": "Result",
        "btn_run": "▶",
        "btn_first": "⏩",
        "btn_stream": "📡",
        "btn_stop": "⏹",
        "stream_label": "Stream",

        # trace
        "trace_title": "🐛 Trace",
        "bp_placeholder": "breakpoints: loop, grandparent",
        "btn_trace": "🔍",
        "btn_continue": "⏵",
        "btn_step": "⏭",
        "btn_abort": "⛔",
        "btn_reset": "↺",
        "bp_reset_ok": "Reset.",
        "trace_running": "▶ Running... Hit: {hit}",
        "trace_paused": "⏸ Paused: {info} | Hit: {hit}",
        "trace_paused_rule": "{goal} (rule: {rule})",
        "trace_done": "✓ Done. BP hit: {hit}",
        "trace_aborted": "⛔ Aborted",
        "steps_title": "**Steps** (click a row — subst)",
        "subst_title": "**subst**",
        "steps_id": "id",
        "steps_goal": "goal",
        "steps_rule": "rule",
        "steps_ok": "ok",
        "steps_kind": "kind",
        "subst_var": "var",
        "subst_before": "before",
        "subst_after": "after",
    },
    "ru": {
        # generic
        "title": "PyAgentProlog IDE",
        "language": "Язык",
        "session_lost": "Сессия не найдена. Перезагрузите страницу.",
        "empty_query": "Пустой запрос",
        "timeout_fmt": "Таймаут {s}s",
        "no_solutions": "Нет решений",
        "solutions_fmt": "── {n} решение(й) ──",
        "true": "true",

        # columns
        "col_project": "📁 Проект",
        "col_program": "📝 Программа",
        "col_query": "🔎 Запрос",

        # project panel
        "project_placeholder":
            "Путь к папке проекта (напр. D:\\Projects\\my_prolog)",
        "btn_open": "📂 Открыть",
        "btn_new": "🆕 Создать",
        "btn_save": "💾 Сохранить",
        "btn_example": "📚",
        "project_not_selected": "Проект не выбран",
        "project_folder_not_found": "✗ Папка не найдена: {inp!r}",
        "project_ok": "✓ Проект: {dir}",
        "project_kb": "  kb:            {kb}",
        "project_actions": "  my_actions.py: {st}",
        "project_actions_present": "есть",
        "project_actions_absent": "—",
        "examples_hint": "📚 Примеры: <code>{root}</code>",
        "file_not_selected": "✗ Файл не выбран",
        "folder_not_selected": "✗ Папка не выбрана",
        "no_project_selected": "✗ Проект не выбран",
        "no_pl_found": "✗ В {dir} не найден .pl",
        "saved_to": "✓ Сохранено: {path}",
        "new_project_path_required": "✗ Укажите путь к новой папке",
        "open_path_required": "✗ Укажите путь",
        "examples_missing": "✗ Папка examples не найдена: {root}",
        "example_not_selected": "✗ Пример не выбран",
        "drop_loaded": (
            "ℹ Загружено в редактор: {name}\n"
            "  ⚠ Drag-drop всегда копирует файл во временную папку Gradio.\n"
            "  Папка проекта не определена автоматически.\n"
            "  Укажите путь в поле выше и нажмите 📂 Открыть,\n"
            "  либо перетащите файл в папку-проект заранее."
        ),
        "status_ready": (
            "Готов. Откройте проект (📂) или создайте новый (🆕)."
        ),
        "status_cleared": "Очищено",

        # context accordion
        "ctx_title": "🔌 Контекст (context)",
        "ctx_key_placeholder": "ключ (llm, db, ...)",
        "ctx_val_placeholder": "Python-выражение",
        "ctx_add": "➕",
        "ctx_del": "🗑️",
        "ctx_apply": "🔄 Применить",
        "ctx_list": "🔄 Список",
        "ctx_key_empty": "✗ Ключ пустой",
        "ctx_set_ok": "✓ context['{key}'] = {type}",
        "ctx_del_ok": "✓ context['{key}'] удалён",
        "ctx_applied": "✓ context применён; ключей: {n}",

        # semantic accordion
        "sem_title": "🧬 Semantic",
        "sem_badge_off": "🔴 OFF Semantic unifier выключен",
        "sem_badge_off_err":
            "🔴 OFF Semantic unifier выключен — "
            "<span style='color:#ff7b72'>{err}</span>",
        "sem_badge_on":
            "🟢 ON backend=<code>{backend}</code> threshold=<b>{thr}</b> "
            "soft_cos_min=<b>{cos}</b> ({kind})",
        "sem_backend": "Backend",
        "sem_model": "Model (имя/ID для префикса и fallback)",
        "sem_local_path":
            "Local path (точный путь к папке HF-модели, опционально)",
        "sem_local_only": "Только локально (не скачивать с HF)",
        "sem_threshold": "Threshold",
        "sem_soft": "Soft cos min",
        "sem_lev_max": "Lev max",
        "sem_lev_typo": "Lev typo max",
        "sem_help": (
            "**`st`** — `pip install sentence-transformers`  \n"
            "**`ollama`** — сервер на `http://localhost:11434`  \n"
            "**Local path** заполнен и папка есть → **только локально** "
            "(без сети).  \n"
            "Если папки нет → fallback на HF (если не включён "
            "«Только локально»)."
        ),
        "sem_on": "✅ ON",
        "sem_off": "❌ OFF",
        "sem_thr": "🔧 Thr",
        "sem_test_title": "### 🔬 Проверка пары строк",
        "sem_test_a": "A (moskva)",
        "sem_test_b": "B (moscow)",
        "sem_test_run": "🔬",
        "sem_disabled": "semantic не включён — нажмите ✅ ON",
        "sem_compare_empty": "оба поля должны быть непустыми",
        "sem_enable_st_local": "✓ Semantic: st (local)\n  {path}",
        "sem_enable_st_local_missing":
            "✗ Локальная папка модели не найдена: {path}\n"
            "  local_only=True — загрузка с HF отключена.",
        "sem_enable_st_hf":
            "✓ Semantic: st (HF fallback)\n  {model}\n"
            "  ⚠ Локальная папка не найдена: {path}",
        "sem_enable_ok": "✓ Semantic: {backend}/{model}",
        "sem_enable_import":
            "✗ {err}\n  💡 backend='st' requires: "
            "pip install sentence-transformers",
        "sem_enable_err":
            "✗ {err}\n"
            "  💡 ollama: сервер на http://localhost:11434\n"
            "  💡 st:     pip install sentence-transformers",
        "sem_disabled_ok": "✓ Semantic отключён",
        "sem_thr_ok": "✓ Threshold = {v}",
        "sem_thr_not_enabled": "✗ Semantic не включён",
        "sem_hint_lev":
            "cos={cos:.3f} в soft-коридоре, но lev={lev:.3f} > "
            "lev_max={lev_max} → увеличьте Lev max до {suggest}",
        "sem_hint_cos":
            "lev={lev:.3f} в норме, но cos={cos:.3f} < "
            "soft_cos_min={soft} → уменьшите Soft cos min до {suggest}",
        "sem_hint_both":
            "и cos={cos:.3f} < {soft}, и lev={lev:.3f} > {lev_max} "
            "→ уменьшите Soft cos min до {s1} И увеличьте Lev max до {s2}",
        "sem_hint_internal":
            "внутреннее противоречие: параметры в норме, но вердикт NONE — "
            "проверьте _semantic_match",

        # diagnostics
        "diag_title": "🔬 Диагностика",
        "diag_refresh": "🔄 Обновить",

        # editor
        "btn_reload": "🔄 Перезагрузить",
        "btn_check": "✓ Синтаксис",
        "btn_clear": "🗑️ Очистить",
        "actions_title": "⚡ Зарегистрированные действия",
        "kb_title": "📚 База знаний",
        "kb_rules": "Правила",
        "kb_index": "Индекс",
        "loaded_ok": (
            "✓ Загружено: {n} правил(о); действий: {a}; проект: {p}"
        ),
        "syntax_ok": "✓ Синтаксис OK: {n} правил(о)",

        # query
        "query_placeholder": "parent(ivan, X).",
        "timeouts_title": "▶ Таймауты и выполнение",
        "result_title": "Результат",
        "btn_run": "▶",
        "btn_first": "⏩",
        "btn_stream": "📡",
        "btn_stop": "⏹",
        "stream_label": "Stream",

        # trace
        "trace_title": "🐛 Трассировка",
        "bp_placeholder": "breakpoints: loop, grandparent",
        "btn_trace": "🔍",
        "btn_continue": "⏵",
        "btn_step": "⏭",
        "btn_abort": "⛔",
        "btn_reset": "↺",
        "bp_reset_ok": "Сброшено.",
        "trace_running": "▶ Работает... Hit: {hit}",
        "trace_paused": "⏸ Пауза: {info} | Hit: {hit}",
        "trace_paused_rule": "{goal} (rule: {rule})",
        "trace_done": "✓ Готово. BP hit: {hit}",
        "trace_aborted": "⛔ Aborted",
        "steps_title": "**Шаги** (клик — subst)",
        "subst_title": "**subst**",
        "steps_id": "id",
        "steps_goal": "goal",
        "steps_rule": "rule",
        "steps_ok": "ok",
        "steps_kind": "kind",
        "subst_var": "var",
        "subst_before": "before",
        "subst_after": "after",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    """Look up a translated string for the given language."""
    table = TRANSLATIONS.get(lang) or TRANSLATIONS["en"]
    template = table.get(key) or TRANSLATIONS["en"].get(key, key)
    return template.format(**kwargs) if kwargs else template


def _detect_system_lang() -> str:
    """Detect system language (en/ru); overridable via env var."""
    override = os.environ.get("PYAGENTPROLOG_IDE_LANG", "").strip().lower()
    if override in ("en", "ru"):
        return override
    try:
        import locale
        loc = (locale.getlocale()[0] or "").lower()
        if loc.startswith("ru"):
            return "ru"
    except (ValueError, TypeError, AttributeError):
        pass
    for var in ("LANG", "LC_ALL", "LANGUAGE", "LC_MESSAGES"):
        if os.environ.get(var, "").lower().startswith("ru"):
            return "ru"
    if sys.platform == "win32":
        try:
            import ctypes
            if (ctypes.windll.kernel32.GetUserDefaultUILanguage()
                    & 0x3FF) == 0x19:
                return "ru"
        except Exception:
            pass
    return "en"


# =====================================================================
# Global CSS (dark + compact)
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
   gr.Dataframe — dark theme (steps, subst and any other Dataframes)
   Covers: Gradio 4/5 (HTML <table>) and Gradio 6 (role="grid").
   =================================================================== */

/* --- Containers --- */
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

/* --- Selected / focused cell --- */
.gradio-dataframe td.selected,
.gradio-dataframe [role="gridcell"][aria-selected="true"] {
    background-color: #2a313d !important;
    color: #ffffff !important;
}

/* --- Editable inputs inside cells (just in case) --- */
.gradio-dataframe input,
.gradio-dataframe textarea,
.gradio-dataframe select {
    background-color: #0f1115 !important;
    color: #e6e6e6 !important;
    border-color: #2a313d !important;
}

/* --- Scrollbar inside table --- */
.gradio-dataframe ::-webkit-scrollbar { width: 8px; height: 8px; }
.gradio-dataframe ::-webkit-scrollbar-thumb { background: #2a313d; border-radius: 5px; }
.gradio-dataframe ::-webkit-scrollbar-track { background: transparent; }
"""

# =====================================================================
# Additional CSS injected via <head> — fallback for gr.Dataframe.
# Injected into <head> separately from launch(css=...).
# =====================================================================
_HEAD_DARK = """
<style>
/* ---- Gradio CSS variables that the table reacts to ---- */
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

/* ---- Aggressive blanket across all Dataframes ---- */
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

/* ---- Headers (override the blanket above) ---- */
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

/* ---- Cells ---- */
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

/* ---- Inputs inside cells (for interactive mode) ---- */
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
# Utilities
# =====================================================================
def _run_with_timeout(fn, timeout: float):
    box, err = {}, {}

    def w():
        try:
            box["v"] = fn()
        except BaseException as e:  # noqa: BLE001
            err["e"] = e

    th = threading.Thread(target=w, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        raise TimeoutError(f"Timeout {timeout}s")
    if "e" in err:
        raise err["e"]
    return box.get("v")


def _to_timeout(v, default: float = 30.0) -> float:
    """Safely convert user input to timeout seconds.

    Empty / None / non-numeric / <=0 → default.
    """
    try:
        x = float(v)
        return x if x > 0 else default
    except (TypeError, ValueError):
        return default


def _status_html(s: str) -> str:
    return f'<pre class="status-box">{_esc(str(s))}</pre>'


def _get_ide(sid: Optional[str], lang: str = "en"):
    ide = get_session(sid)
    if ide is None:
        raise gr.Error(t(lang, "session_lost"))
    return ide


def _pick_folder(initial: str = "",
                 title: str = "Select project folder") -> Optional[str]:
    """Native folder picker via tkinter."""
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
                  title: str = "Open project — select a .pl file"
                  ) -> Optional[str]:
    """File picker for .pl files. Returns the path or None."""
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
    """Return a favicon path.

    Looks for favicon.{png,ico,svg} in the package root or in assets/.
    If nothing exists, generates a default SVG in the package root so
    we don't depend on external resources.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for subdir in ("", "assets"):
        for name in ("favicon.png", "favicon.ico", "favicon.svg"):
            path = os.path.join(here, subdir, name) if subdir \
                else os.path.join(here, name)
            if os.path.isfile(path):
                return path
    # nothing found — create a default SVG
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
                mod = (importlib.reload(sys.modules[name])
                       if sig != self._actions_sig
                       else sys.modules[name])
            else:
                mod = importlib.import_module(name)
            self.agent.register_action_module(mod)
            self._actions_sig = sig
        except Exception as e:  # noqa: BLE001
            print(f"[actions import] {mod_path}: {e}")

    # ------------------------------------------------------------------
    # Project
    # ------------------------------------------------------------------
    def set_project(self, inp, lang: str = "en") -> str:
        raw = inp.name if hasattr(inp, "name") else str(inp or "").strip()
        new_dir = resolve_project_dir(inp)
        if not new_dir or not os.path.isdir(new_dir):
            return t(lang, "project_folder_not_found", inp=inp)

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
        lines = [t(lang, "project_ok", dir=new_dir)]
        lines.append(t(lang, "project_kb",
                       kb=os.path.basename(kb) if kb else "—"))
        lines.append(t(lang, "project_actions",
                       st=t(lang, "project_actions_present") if mod
                          else t(lang, "project_actions_absent")))
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

    def load_kb_from_project(self, lang: str = "en") -> Tuple[str, str]:
        if not self.project_dir:
            return "", f"✗ {t(lang, 'no_project_selected')}"
        kb = self._kb_file_hint
        if not kb or not os.path.isfile(kb):
            kb = find_kb(self.project_dir)
        if not kb:
            return "", t(lang, "no_pl_found", dir=self.project_dir)
        try:
            with open(kb, encoding="utf-8") as f:
                text = f.read()
            return text, self.load_program(text, lang)
        except Exception as e:  # noqa: BLE001
            return "", f"✗ {e}\n{traceback.format_exc()}"

    def save_project(self, text: str, lang: str = "en") -> str:
        if not self.project_dir:
            return f"✗ {t(lang, 'no_project_selected')}"
        kb = (find_kb(self.project_dir)
              or os.path.join(self.project_dir, KB_FILENAME))
        try:
            with open(kb, "w", encoding="utf-8") as f:
                f.write(text or "")
            return t(lang, "saved_to", path=kb)
        except Exception as e:  # noqa: BLE001
            return f"✗ {e}"

    def new_project(self, path: str, lang: str = "en") -> Tuple[str, str]:
        path = (path or "").strip()
        if not path:
            return "", f"✗ {t(lang, 'new_project_path_required')}"
        path = os.path.abspath(path)
        try:
            os.makedirs(path, exist_ok=True)
            kb = os.path.join(path, KB_FILENAME)
            if not os.path.isfile(kb):
                template = (
                    "% New PyAgentProlog project.\n"
                    "% my_actions.py next to kb.pl will be loaded automatically.\n\n"
                    "start :-\n"
                    "    write('Hello, PyAgentProlog!'), nl.\n"
                )
                with open(kb, "w", encoding="utf-8") as f:
                    f.write(template)
            self.set_project(path, lang)
            text, msg = self.load_kb_from_project(lang)
            return (text if text else gr.update()), msg
        except Exception as e:  # noqa: BLE001
            return gr.update(), f"✗ {e}\n{traceback.format_exc()}"

    # ------------------------------------------------------------------
    # Program
    # ------------------------------------------------------------------
    def load_program(self, text: str, lang: str = "en") -> str:
        try:
            self.agent = None
            self._signature = None
            self._actions_sig = None
            agent = self._ensure_agent(text)
            n = len(agent.solver.database.rules)
            acts = len(self.get_actions())
            return t(lang, "loaded_ok", n=n, a=acts,
                     p=self.project_dir or "—")
        except Exception as e:  # noqa: BLE001
            return f"✗ {e}\n{traceback.format_exc()}"

    def check_program(self, text: str, lang: str = "en") -> str:
        try:
            rules = Parser(text).parse_rules()
            return t(lang, "syntax_ok", n=len(rules))
        except Exception as e:  # noqa: BLE001
            return f"✗ {e}"

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def run_query(self, text: str, query: str, timeout: float,
                  lang: str = "en") -> Tuple[Dict, str]:
        try:
            if not query.strip():
                return {}, f"✗ {t(lang, 'empty_query')}"
            agent = self._ensure_agent(text)
            res = _run_with_timeout(lambda: agent.query(query), timeout)
            out = res.get("output", "") if isinstance(res, dict) else str(res)
            n = res.get("count", 1) if isinstance(res, dict) else 1
            self.history.append({"q": query, "ok": True})
            return res, f"{out}\n{t(lang, 'solutions_fmt', n=n)}"
        except TimeoutError as e:
            return {"error": str(e)}, f"⏱ {e}"
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}, f"✗ {e}"

    def run_first(self, text: str, query: str, timeout: float,
                  lang: str = "en") -> Tuple[Dict, str]:
        try:
            if not query.strip():
                return {}, f"✗ {t(lang, 'empty_query')}"
            agent = self._ensure_agent(text)
            res = _run_with_timeout(lambda: agent.query_one(query), timeout)
            if res is None:
                return {"solution": None}, f"✗ {t(lang, 'no_solutions')}"
            if isinstance(res, dict) and res.get("__success__"):
                return {"success": True}, f"✓ {t(lang, 'true')}"
            return res, f"✓ {json.dumps(res, ensure_ascii=False, default=str)}"
        except TimeoutError as e:
            return {"error": str(e)}, f"⏱ {e}"
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}, f"✗ {e}"

    def run_stream(self, text: str, query: str,
                   per_item_timeout: float = 30.0, lang: str = "en"):
        if not query.strip():
            yield f"✗ {t(lang, 'empty_query')}"
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
            yield f"✗ {t(lang, 'no_solutions')}"

    # ------------------------------------------------------------------
    # Trace + breakpoints
    # ------------------------------------------------------------------
    def run_traced(self, text: str, query: str, timeout: float,
                   bp_string: str, lang: str = "en"):
        predicates = [p.strip() for p in (bp_string or "").split(",")
                      if p.strip()]
        self.controller.set_breakpoints(predicates)
        self.controller.reset()

        if not query.strip():
            yield self._final_state(
                f"✗ {t(lang, 'empty_query')}", {},
                f"✗ {t(lang, 'empty_query')}", lang)
            return
        try:
            agent = self._ensure_agent(text)
        except Exception as e:  # noqa: BLE001
            yield self._final_state(f"✗ {e}", {"error": str(e)},
                                    f"✗ {e}", lang)
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

        th = threading.Thread(target=worker, daemon=True)
        th.start()
        yield self._running_state(lang)

        last_paused = False
        start = time.time()
        try:
            while not stop.is_set():
                paused = self.controller.paused
                if paused != last_paused:
                    last_paused = paused
                    if paused:
                        yield self._paused_state(
                            self.controller.current_step, lang)
                    else:
                        yield self._running_state(lang)
                if time.time() - start > timeout:
                    self.controller.resume("abort")
                    error_box["e"] = TimeoutError(
                        t(lang, "timeout_fmt", s=timeout))
                    break
                time.sleep(0.05)
        finally:
            agent.solver.database.tracer = original_tracer

        if result_box.get("aborted"):
            yield self._final_state(
                t(lang, "trace_aborted"), {},
                t(lang, "trace_aborted"), lang)
            return
        if "e" in error_box:
            err = error_box["e"]
            tb = "".join(traceback.format_exception(
                type(err), err, err.__traceback__))
            yield self._final_state(f"✗ {err}",
                                    {"error": str(err), "traceback": tb},
                                    f"✗ {err}\n{tb}", lang)
            return

        result, explanation = result_box["v"]
        out = (result.get("output", "")
               if isinstance(result, dict) else str(result))
        n = result.get("count", 1) if isinstance(result, dict) else 1
        root_steps = explanation.root_steps if explanation else []
        tree_html = render_tree_html(root_steps)
        rows, dicts = build_trace_artifacts(root_steps)

        yield (
            t(lang, "trace_done", hit=self.controller.hit_count),
            gr.update(interactive=False),
            gr.update(interactive=False),
            gr.update(interactive=False),
            result,
            f"{out}\n{t(lang, 'solutions_fmt', n=n)}",
            tree_html,
            rows,
            dicts,
        )

    def _running_state(self, lang: str = "en"):
        return (
            t(lang, "trace_running", hit=self.controller.hit_count),
            gr.update(interactive=False),
            gr.update(interactive=False),
            gr.update(interactive=False),
            gr.update(), gr.update(), "", [], [],
        )

    def _paused_state(self, step: Optional[Any], lang: str = "en"):
        if step and step.rule_used:
            info = t(lang, "trace_paused_rule",
                     goal=step.goal, rule=step.rule_used)
        else:
            info = step.goal if step else "?"
        return (
            t(lang, "trace_paused", info=info,
              hit=self.controller.hit_count),
            gr.update(interactive=True),
            gr.update(interactive=True),
            gr.update(interactive=True),
            gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
        )

    def _final_state(self, status: str, result_json, result_text: str,
                     lang: str = "en"):
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
                for (name, arity), entry
                in agent.solver.database.rule_index.items()
            }
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def get_actions(self) -> List[Dict]:
        return self.agent.list_actions() if self.agent else []

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------
    def context_set(self, key: str, value_repr: str,
                    lang: str = "en") -> str:
        try:
            key = (key or "").strip()
            if not key:
                return f"✗ {t(lang, 'ctx_key_empty')}"
            value = eval(value_repr,
                         {"__builtins__": __builtins__}, {})  # noqa: S307
            self.context.set(key, value)
            if self.agent is not None:
                self.agent.context[key] = value
            return t(lang, "ctx_set_ok", key=key,
                     type=type(value).__name__)
        except Exception as e:  # noqa: BLE001
            return f"✗ {e}\n{traceback.format_exc()}"

    def context_delete(self, key: str, lang: str = "en") -> str:
        key = (key or "").strip()
        if not key:
            return f"✗ {t(lang, 'ctx_key_empty')}"
        self.context.values.pop(key, None)
        if self.agent is not None:
            self.agent.context.pop(key, None)
        return t(lang, "ctx_del_ok", key=key)

    def context_list(self) -> List[Dict]:
        return [
            {"key": k, "type": type(v).__name__, "repr": repr(v)[:120]}
            for k, v in self.context.values.items()
        ]

    def context_apply(self, text: str, lang: str = "en") -> str:
        try:
            new_ctx = self.context.apply()
            self.agent = None
            self._signature = None
            self._ensure_agent(text)
            return t(lang, "ctx_applied", n=len(new_ctx))
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
                        local_path: str = "", local_only: bool = False,
                        lang: str = "en",
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
                        threshold=threshold, backend=backend,
                        model=local_path,
                        soft_cos_min=soft, lev_max=lev_max,
                        lev_typo_max=lev_typo,
                        text_prefix=prefix,
                        st_local_files_only=True,
                    )
                    return (t(lang, "sem_enable_st_local",
                              path=local_path), semantic_status())

                if local_only:
                    return (
                        t(lang, "sem_enable_st_local_missing",
                          path=local_path),
                        {"enabled": False,
                         "error": f"local path not found: {local_path}"},
                    )

                semantic_on(
                    threshold=threshold, backend=backend, model=model,
                    soft_cos_min=soft, lev_max=lev_max,
                    lev_typo_max=lev_typo,
                )
                return (t(lang, "sem_enable_st_hf",
                          model=model, path=local_path),
                        semantic_status())

            semantic_on(
                threshold=threshold, backend=backend, model=model,
                soft_cos_min=soft, lev_max=lev_max,
                lev_typo_max=lev_typo,
                st_local_files_only=(local_only if backend == "st"
                                     else False),
            )
            return (t(lang, "sem_enable_ok",
                      backend=backend, model=model),
                    semantic_status())

        except ImportError as e:
            return (t(lang, "sem_enable_import", err=e),
                    {"enabled": False, "error": str(e)})
        except Exception as e:  # noqa: BLE001
            return (t(lang, "sem_enable_err", err=e),
                    {"enabled": False, "error": str(e)})

    def semantic_disable(self,
                         lang: str = "en") -> Tuple[str, Dict[str, Any]]:
        try:
            from prolog.embedding_unify import semantic_off, semantic_status
            semantic_off()
            return t(lang, "sem_disabled_ok"), semantic_status()
        except Exception as e:  # noqa: BLE001
            return f"✗ {e}", {"enabled": False, "error": str(e)}

    def semantic_set_threshold(self, value: float, lang: str = "en"
                               ) -> Tuple[str, Dict[str, Any]]:
        try:
            from prolog.embedding_unify import (
                semantic_get_unifier,
                semantic_set_threshold,
                semantic_status,
            )
            if semantic_get_unifier() is None:
                return t(lang, "sem_thr_not_enabled"), semantic_status()
            semantic_set_threshold(value)
            return t(lang, "sem_thr_ok", v=value), semantic_status()
        except Exception as e:  # noqa: BLE001
            return f"✗ {e}", {"enabled": False, "error": str(e)}

    def semantic_compare(self, a: str, b: str,
                         lang: str = "en") -> Dict[str, Any]:
        """Diagnose a pair of strings through the active semantic unifier."""
        from prolog.embedding_unify import (
            _lev_ratio,
            _normalize_text,
            semantic_get_unifier,
        )
        u = semantic_get_unifier()
        if u is None:
            return {"error": t(lang, "sem_disabled")}

        s1 = _normalize_text(a or "")
        s2 = _normalize_text(b or "")
        if not s1 or not s2:
            return {"error": t(lang, "sem_compare_empty")}

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
            if (cos >= u.soft_cos_min and cos < u.threshold
                    and lev > u.lev_max):
                hints.append(t(
                    lang, "sem_hint_lev",
                    cos=cos, lev=lev, lev_max=u.lev_max,
                    suggest=round(lev + 0.05, 2)))
            if cos < u.soft_cos_min and lev <= u.lev_max:
                hints.append(t(
                    lang, "sem_hint_cos",
                    cos=cos, lev=lev, soft=u.soft_cos_min,
                    suggest=max(0.0, round(cos - 0.05, 2))))
            if cos < u.soft_cos_min and lev > u.lev_max:
                hints.append(t(
                    lang, "sem_hint_both",
                    cos=cos, lev=lev,
                    soft=u.soft_cos_min, lev_max=u.lev_max,
                    s1=max(0.0, round(cos - 0.05, 2)),
                    s2=round(lev + 0.05, 2)))
            if cos >= u.soft_cos_min and lev <= u.lev_max:
                hints.append(t(lang, "sem_hint_internal"))
            result["hints"] = hints

        return result

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def diagnostics(self) -> Dict:
        d: Dict[str, Any] = {
            "agent": {
                "rules": (len(self.agent.solver.database.rules)
                          if self.agent else 0),
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
def _project_info_html(info: Dict[str, Any], lang: str = "en") -> str:
    if not info or not info.get("project_dir"):
        return (f'<div class="proj-info">'
                f'{t(lang, "project_not_selected")}</div>')
    lines = [
        f"<b>{_esc(t(lang, 'project_ok', dir='').strip().rstrip(':').strip())}:</b> "
        f"{_esc(info['project_dir'])}",
        f"kb.pl: {_esc(os.path.basename(info.get('kb') or '—'))}",
        f"my_actions.py: "
        f"{(t(lang, 'project_actions_present') if info.get('my_actions') else t(lang, 'project_actions_absent'))}",
    ]
    return f'<div class="proj-info">{"<br>".join(lines)}</div>'


def _sem_badge_html(status: Dict[str, Any], lang: str = "en") -> str:
    """Visual badge: 🟢 ON / 🔴 OFF + brief info."""
    if not status or not status.get("enabled"):
        err = (status or {}).get("error")
        if err:
            return (
                f'<div class="proj-info">'
                f'{t(lang, "sem_badge_off_err", err=_esc(err))}</div>'
            )
        return f'<div class="proj-info">{t(lang, "sem_badge_off")}</div>'
    return (
        f'<div class="proj-info">'
        + t(lang, "sem_badge_on",
            backend=_esc(str(status.get("backend", "?"))),
            thr=status.get("threshold"),
            cos=status.get("soft_cos_min"),
            kind=("custom" if status.get("has_custom_embed_fn")
                  else "builtin"))
        + '</div>'
    )


def handle_sem_status_html(sid, lang):
    return _sem_badge_html(_get_ide(sid, lang).semantic_status(), lang)


# --- Open ----------------------------------------------------------
def handle_open_project(sid, path: str, lang: str):
    """Open a project. Empty path → file picker (.pl files shown)."""
    ide = _get_ide(sid, lang)
    path = (path or "").strip()
    if not path:
        picked = _pick_pl_file(
            initial=(examples_root()
                     if os.path.isdir(examples_root()) else ""),
            title="Open project — select a .pl file from the project folder",
        )
        if not picked:
            return (gr.update(), gr.update(),
                    _project_info_html(ide.get_project_info(), lang),
                    _status_html(f"✗ {t(lang, 'file_not_selected')}"))
        path = picked
    msg = ide.set_project(path, lang)
    if msg.startswith("✗"):
        return (gr.update(), path,
                _project_info_html(ide.get_project_info(), lang),
                _status_html(msg))
    text, load_msg = ide.load_kb_from_project(lang)
    return (
        text if text else gr.update(),
        path,
        _project_info_html(ide.get_project_info(), lang),
        _status_html(load_msg),
    )


# --- Create --------------------------------------------------------
def handle_new_project(sid, path: str, lang: str):
    """Always opens the folder picker / creation dialog."""
    ide = _get_ide(sid, lang)
    path = (path or "").strip()
    picked = _pick_folder(
        initial=path or os.path.expanduser("~"),
        title="Select a folder for the new project (can be created)",
    )
    if not picked:
        return (gr.update(), gr.update(),
                _project_info_html(ide.get_project_info(), lang),
                _status_html(f"✗ {t(lang, 'folder_not_selected')}"))
    text, msg = ide.new_project(picked, lang)
    return (
        text if text else gr.update(),
        picked,
        _project_info_html(ide.get_project_info(), lang),
        _status_html(msg),
    )


# --- Save ----------------------------------------------------------
def handle_save_project(sid, text: str, path: str, lang: str):
    """Save into the folder from the field. Empty → into current project."""
    ide = _get_ide(sid, lang)
    path = (path or "").strip()
    if path:
        path_abs = os.path.abspath(path)
        if (not ide.project_dir) or path_abs != ide.project_dir:
            m = ide.set_project(path, lang)
            if m.startswith("✗"):
                return _status_html(m)
    if not ide.project_dir:
        return _status_html(f"✗ {t(lang, 'no_project_selected')}")
    return _status_html(ide.save_project(text, lang))


# --- Open example (shortcut) ---------------------------------------
def handle_open_example(sid, lang: str):
    """Opens a .pl picker rooted in examples/."""
    ide = _get_ide(sid, lang)
    root = examples_root()
    if not os.path.isdir(root):
        return (gr.update(), gr.update(),
                _project_info_html(ide.get_project_info(), lang),
                _status_html(t(lang, "examples_missing", root=root)))
    picked = _pick_pl_file(
        initial=root,
        title="Select an example — open kb.pl from the example folder",
    )
    if not picked:
        return (gr.update(), gr.update(),
                _project_info_html(ide.get_project_info(), lang),
                _status_html(f"✗ {t(lang, 'example_not_selected')}"))
    msg = ide.set_project(picked, lang)
    if msg.startswith("✗"):
        return (gr.update(), picked,
                _project_info_html(ide.get_project_info(), lang),
                _status_html(msg))
    text, load_msg = ide.load_kb_from_project(lang)
    return (
        text if text else gr.update(),
        picked,
        _project_info_html(ide.get_project_info(), lang),
        _status_html(load_msg),
    )


# --- Drag-drop .pl into editor (does not change the project) -------
def handle_drop_pl(sid, f, lang: str):
    """Drop .pl → load its content into the editor."""
    if f is None:
        return gr.update(), _status_html(f"✗ {t(lang, 'file_not_selected')}")
    try:
        path = f.name if hasattr(f, "name") else str(f)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        return (
            text,
            _status_html(t(lang, "drop_loaded",
                           name=os.path.basename(path))),
        )
    except Exception as e:  # noqa: BLE001
        return gr.update(), _status_html(f"✗ {e}")


# --- Misc ----------------------------------------------------------
def handle_project_info(sid, lang):
    return _project_info_html(_get_ide(sid, lang).get_project_info(), lang)


def handle_reload(sid, text, lang):
    return _status_html(_get_ide(sid, lang).load_program(text, lang))


def handle_check(sid, text, lang):
    return _status_html(_get_ide(sid, lang).check_program(text, lang))


def handle_run(sid, text, query, timeout, lang):
    return _get_ide(sid, lang).run_query(
        text, query, _to_timeout(timeout), lang)


def handle_first(sid, text, query, timeout, lang):
    return _get_ide(sid, lang).run_first(
        text, query, _to_timeout(timeout), lang)


def handle_stream(sid, text, query, timeout, lang):
    yield from _get_ide(sid, lang).run_stream(
        text, query, _to_timeout(timeout), lang)


def handle_trace(sid, text, query, timeout, bp_string, lang):
    yield from _get_ide(sid, lang).run_traced(
        text, query, _to_timeout(timeout), bp_string, lang,
    )


def handle_bp_resume(sid, action):
    get_session(sid).controller.resume(action)
    return gr.update()


def handle_bp_reset(sid, lang):
    _get_ide(sid, lang).controller.reset()
    return t(lang, "bp_reset_ok")


def handle_step_select(evt: gr.SelectData, steps_state):
    try:
        idx = (evt.index[0]
               if isinstance(evt.index, (tuple, list)) else evt.index)
        if 0 <= int(idx) < len(steps_state):
            return subst_rows_from_dict(steps_state[int(idx)])
    except Exception:  # noqa: BLE001
        pass
    return []


def handle_kb(sid, text, lang):
    ide = _get_ide(sid, lang)
    return ide.get_kb(text), ide.get_index(text)


def handle_actions(sid, lang):
    return _get_ide(sid, lang).get_actions()


def handle_ctx_set(sid, key, value_repr, lang):
    return _get_ide(sid, lang).context_set(key, value_repr, lang)


def handle_ctx_delete(sid, key, lang):
    return _get_ide(sid, lang).context_delete(key, lang)


def handle_ctx_list(sid, lang):
    return _get_ide(sid, lang).context_list()


def handle_ctx_apply(sid, text, lang):
    return _get_ide(sid, lang).context_apply(text, lang)


def handle_sem_status(sid, lang):
    return _get_ide(sid, lang).semantic_status()


def handle_sem_enable(sid, backend, model, threshold, soft, lev_max,
                      lev_typo, local_path, local_only, lang):
    return _get_ide(sid, lang).semantic_enable(
        backend, model,
        float(threshold), float(soft),
        float(lev_max), float(lev_typo),
        local_path=local_path or "",
        local_only=bool(local_only),
        lang=lang,
    )


def handle_sem_disable(sid, lang):
    return _get_ide(sid, lang).semantic_disable(lang)


def handle_sem_threshold(sid, value, lang):
    return _get_ide(sid, lang).semantic_set_threshold(float(value), lang)


def handle_sem_compare(sid, a, b, lang):
    return _get_ide(sid, lang).semantic_compare(a, b, lang)


def handle_diag(sid, lang):
    return _get_ide(sid, lang).diagnostics()


# =====================================================================
# UI
# =====================================================================
def build_ui() -> gr.Blocks:
    lang = _detect_system_lang()
    print(f"[pyagentprolog-ide] language: {lang} "
          f"(override: PYAGENTPROLOG_IDE_LANG=en|ru)",
          file=sys.stderr, flush=True)

    with gr.Blocks(**blocks_kwargs(_GLOBAL_CSS, _HEAD_DARK)) as ui:
        session_state = gr.State(None)
        steps_state = gr.State([])
        lang_state = gr.State(lang)

        ui.load(fn=new_session, outputs=[session_state])

        with gr.Row(equal_height=False):
            # ============================================================
            # COLUMN 1: project and settings
            # ============================================================
            with gr.Column(scale=2, min_width=300):
                gr.HTML(
                    f'<div class="col-head">{t(lang, "col_project")}</div>')

                pl_input = gr.File(
                    show_label=False,
                    file_types=[".pl", ".prolog", ".txt"],
                    file_count="single",
                )
                project_path = gr.Textbox(
                    placeholder=t(lang, "project_placeholder"),
                    show_label=False,
                    elem_classes=["compact-tb"],
                )
                with gr.Row(equal_height=True):
                    open_btn = gr.Button(
                        t(lang, "btn_open"), size="sm", scale=2,
                        elem_classes=["compact-btn"])
                    new_btn = gr.Button(
                        t(lang, "btn_new"), size="sm", scale=2,
                        elem_classes=["compact-btn"])
                    save_btn = gr.Button(
                        t(lang, "btn_save"), size="sm", scale=2,
                        elem_classes=["compact-btn"])
                    example_btn = gr.Button(
                        t(lang, "btn_example"), size="sm", scale=1,
                        elem_classes=["compact-btn"])

                project_status = gr.HTML(
                    value=_project_info_html({"project_dir": None}, lang),
                )
                examples_hint = gr.HTML(
                    value=t(lang, "examples_hint",
                            root=_esc(examples_root())),
                )

                with gr.Accordion(t(lang, "ctx_title"), open=False):
                    with gr.Row(equal_height=True):
                        ctx_key = gr.Textbox(
                            placeholder=t(lang, "ctx_key_placeholder"),
                            show_label=False, scale=2,
                            elem_classes=["compact-tb"],
                        )
                    ctx_val = gr.Textbox(
                        placeholder=t(lang, "ctx_val_placeholder"),
                        lines=2,
                        elem_classes=["compact-tb"],
                    )
                    with gr.Row(equal_height=True):
                        ctx_set_btn = gr.Button(
                            t(lang, "ctx_add"), size="sm",
                            elem_classes=["compact-btn"])
                        ctx_del_btn = gr.Button(
                            t(lang, "ctx_del"), size="sm",
                            elem_classes=["compact-btn"])
                        ctx_apply_btn = gr.Button(
                            t(lang, "ctx_apply"), size="sm",
                            elem_classes=["compact-btn"])
                    ctx_status = gr.Textbox(
                        label="", show_label=False, lines=1,
                        interactive=False, elem_classes=["compact-tb"],
                    )
                    with gr.Row(equal_height=True):
                        refresh_ctx = gr.Button(
                            t(lang, "ctx_list"), size="sm",
                            elem_classes=["compact-btn"])
                    ctx_json = gr.JSON(label="", show_label=False, value=[])

                with gr.Accordion(t(lang, "sem_title"), open=False):
                    sem_badge = gr.HTML(
                        value=_sem_badge_html({"enabled": False}, lang),
                    )
                    with gr.Row(equal_height=True):
                        sem_status_json = gr.JSON(
                            label="", show_label=False)
                        refresh_sem = gr.Button(
                            "🔄", size="sm",
                            elem_classes=["compact-btn"])

                    sem_backend = gr.Dropdown(
                        choices=["st", "ollama"], value="st",
                        label=t(lang, "sem_backend"),
                        elem_classes=["compact-lbl"],
                    )
                    sem_model = gr.Textbox(
                        label=t(lang, "sem_model"),
                        value="paraphrase-multilingual-mpnet",
                        elem_classes=["compact-tb", "compact-lbl"],
                    )
                    sem_local_path = gr.Textbox(
                        label=t(lang, "sem_local_path"),
                        value=(r"D:\hf_embedding"
                               r"\paraphrase-multilingual-mpnet"),
                        placeholder=(r"D:\hf_embedding"
                                     r"\paraphrase-multilingual-mpnet"),
                        elem_classes=["compact-tb", "compact-lbl"],
                    )
                    sem_local_only = gr.Checkbox(
                        label=t(lang, "sem_local_only"),
                        value=False,
                        elem_classes=["compact-lbl"],
                    )

                    sem_threshold = gr.Slider(
                        0.0, 1.0, 0.82, 0.01,
                        label=t(lang, "sem_threshold"))
                    sem_soft = gr.Slider(
                        0.0, 1.0, 0.55, 0.01,
                        label=t(lang, "sem_soft"))
                    sem_lev_max = gr.Slider(
                        0.0, 1.0, 0.55, 0.01,
                        label=t(lang, "sem_lev_max"))
                    sem_lev_typo = gr.Slider(
                        0.0, 1.0, 0.20, 0.01,
                        label=t(lang, "sem_lev_typo"))

                    gr.Markdown(t(lang, "sem_help"))

                    with gr.Row(equal_height=True):
                        sem_on_btn = gr.Button(
                            t(lang, "sem_on"), size="sm",
                            elem_classes=["compact-btn"])
                        sem_off_btn = gr.Button(
                            t(lang, "sem_off"), size="sm",
                            elem_classes=["compact-btn"])
                        sem_set_btn = gr.Button(
                            t(lang, "sem_thr"), size="sm",
                            elem_classes=["compact-btn"])
                    sem_msg = gr.Textbox(
                        label="", show_label=False, interactive=False,
                        lines=3, elem_classes=["compact-tb"],
                    )

                    gr.Markdown(t(lang, "sem_test_title"))
                    with gr.Row(equal_height=True):
                        sem_test_a = gr.Textbox(
                            placeholder=t(lang, "sem_test_a"),
                            show_label=False, scale=1,
                            elem_classes=["compact-tb"],
                        )
                        sem_test_b = gr.Textbox(
                            placeholder=t(lang, "sem_test_b"),
                            show_label=False, scale=1,
                            elem_classes=["compact-tb"],
                        )
                        sem_test_btn = gr.Button(
                            t(lang, "sem_test_run"), size="sm",
                            elem_classes=["compact-btn"])
                    sem_test_json = gr.JSON(label="", show_label=False)

                with gr.Accordion(t(lang, "diag_title"), open=False):
                    diag_btn = gr.Button(
                        t(lang, "diag_refresh"), size="sm",
                        elem_classes=["compact-btn"])
                    diag_json = gr.JSON(label="", show_label=False)

            # ============================================================
            # COLUMN 2: code editor
            # ============================================================
            with gr.Column(scale=5, min_width=500):
                gr.HTML(
                    f'<div class="col-head">{t(lang, "col_program")}</div>')

                editor = gr.Code(
                    language=code_language(),
                    lines=28,
                    value="",
                    show_label=False,
                )
                with gr.Row(equal_height=True):
                    reload_btn = gr.Button(
                        t(lang, "btn_reload"), size="sm",
                        elem_classes=["compact-btn"])
                    check_btn = gr.Button(
                        t(lang, "btn_check"), size="sm",
                        elem_classes=["compact-btn"])
                    clear_btn = gr.Button(
                        t(lang, "btn_clear"), size="sm",
                        elem_classes=["compact-btn"])
                editor_status = gr.HTML(
                    value=_status_html(t(lang, "status_ready")),
                )

                with gr.Accordion(t(lang, "actions_title"),
                                  open=False) as actions_acc:
                    actions_json = gr.JSON(
                        label="", show_label=False, value=[])
                actions_acc.expand(
                    handle_actions,
                    [session_state, lang_state],
                    [actions_json],
                )

                with gr.Accordion(t(lang, "kb_title"),
                                  open=False) as kb_acc:
                    with gr.Row():
                        kb_json = gr.JSON(label=t(lang, "kb_rules"))
                        index_json = gr.JSON(label=t(lang, "kb_index"))
                kb_acc.expand(
                    handle_kb,
                    [session_state, editor, lang_state],
                    [kb_json, index_json],
                )

            # ============================================================
            # COLUMN 3: query and trace
            # ============================================================
            with gr.Column(scale=4, min_width=420):
                gr.HTML(
                    f'<div class="col-head">{t(lang, "col_query")}</div>')

                query_input = gr.Textbox(
                    placeholder=t(lang, "query_placeholder"),
                    lines=2, show_label=False,
                    elem_classes=["compact-tb"],
                )

                gr.HTML(
                    f'<div class="col-head">'
                    f'{t(lang, "timeouts_title")}</div>')

                with gr.Row(equal_height=True, elem_classes=["tiny-row"]):
                    timeout_input = gr.Number(
                        value=30.0,
                        minimum=0.5,
                        maximum=600.0,
                        show_label=False,
                        elem_classes=["compact-lbl"],
                    )
                    run_btn = gr.Button(
                        t(lang, "btn_run"), size="sm", variant="primary",
                        scale=1, min_width=0,
                        elem_classes=["tiny-btn"])
                    first_btn = gr.Button(
                        t(lang, "btn_first"), size="sm",
                        scale=1, min_width=0,
                        elem_classes=["tiny-btn"])
                    stream_btn = gr.Button(
                        t(lang, "btn_stream"), size="sm",
                        scale=1, min_width=0,
                        elem_classes=["tiny-btn"])
                    stop_btn = gr.Button(
                        t(lang, "btn_stop"), size="sm",
                        scale=1, min_width=0,
                        elem_classes=["tiny-btn"])

                with gr.Accordion(t(lang, "result_title"), open=True):
                    results_out = gr.Textbox(
                        label="", show_label=False, lines=8,
                        interactive=False,
                    )
                    results_json = gr.JSON(label="", show_label=False)

                stream_out = gr.Textbox(
                    label=t(lang, "stream_label"), lines=4,
                    interactive=False, elem_classes=["compact-tb"],
                )

                gr.HTML(
                    f'<div class="col-head">'
                    f'{t(lang, "trace_title")}</div>')

                with gr.Row(equal_height=True, elem_classes=["tiny-row"]):
                    bp_predicates = gr.Textbox(
                        placeholder=t(lang, "bp_placeholder"),
                        show_label=False,
                        elem_classes=["compact-tb"],
                    )
                    trace_btn = gr.Button(
                        t(lang, "btn_trace"), size="sm", variant="primary",
                        scale=1, min_width=0,
                        elem_classes=["tiny-btn"])
                    bp_continue = gr.Button(
                        t(lang, "btn_continue"), size="sm",
                        interactive=False, scale=1, min_width=0,
                        elem_classes=["tiny-btn"])
                    bp_step = gr.Button(
                        t(lang, "btn_step"), size="sm",
                        interactive=False, scale=1, min_width=0,
                        elem_classes=["tiny-btn"])
                    bp_abort = gr.Button(
                        t(lang, "btn_abort"), size="sm",
                        interactive=False, scale=1, min_width=0,
                        elem_classes=["tiny-btn"])
                    bp_reset = gr.Button(
                        t(lang, "btn_reset"), size="sm",
                        scale=1, min_width=0,
                        elem_classes=["tiny-btn"])

                bp_status = gr.Textbox(
                    label="", show_label=False, interactive=False,
                    lines=1, elem_classes=["compact-tb"],
                )

                trace_html = gr.HTML()
                gr.Markdown(t(lang, "steps_title"))
                steps_df = gr.Dataframe(
                    headers=[t(lang, "steps_id"), t(lang, "steps_goal"),
                             t(lang, "steps_rule"), t(lang, "steps_ok"),
                             t(lang, "steps_kind")],
                    datatype=["str"] * 5,
                    type="array",
                    interactive=False,
                    wrap=True,
                    label="",
                    elem_id="steps_df",
                )
                gr.Markdown(t(lang, "subst_title"))
                subst_df = gr.Dataframe(
                    headers=[t(lang, "subst_var"),
                             t(lang, "subst_before"),
                             t(lang, "subst_after")],
                    datatype=["str"] * 3,
                    type="array",
                    interactive=False,
                    wrap=True,
                    label="",
                    elem_id="subst_df",
                )

        # ================ Wiring ================
        # --- Project ---
        pl_input.change(
            handle_drop_pl,
            [session_state, pl_input, lang_state],
            [editor, editor_status],
        )
        open_btn.click(
            handle_open_project,
            [session_state, project_path, lang_state],
            [editor, project_path, project_status, editor_status],
        )
        new_btn.click(
            handle_new_project,
            [session_state, project_path, lang_state],
            [editor, project_path, project_status, editor_status],
        )
        save_btn.click(
            handle_save_project,
            [session_state, editor, project_path, lang_state],
            [editor_status],
        )
        example_btn.click(
            handle_open_example,
            [session_state, lang_state],
            [editor, project_path, project_status, editor_status],
        )

        # --- Context ---
        ctx_set_btn.click(
            handle_ctx_set,
            [session_state, ctx_key, ctx_val, lang_state],
            [ctx_status],
        )
        ctx_del_btn.click(
            handle_ctx_delete,
            [session_state, ctx_key, lang_state],
            [ctx_status],
        )
        ctx_apply_btn.click(
            handle_ctx_apply,
            [session_state, editor, lang_state],
            [ctx_status],
        )
        refresh_ctx.click(
            handle_ctx_list,
            [session_state, lang_state],
            [ctx_json],
        )

        # --- Semantic ---
        refresh_sem.click(
            handle_sem_status,
            [session_state, lang_state],
            [sem_status_json],
        ).then(
            handle_sem_status_html,
            [session_state, lang_state],
            [sem_badge],
        )

        sem_on_btn.click(
            handle_sem_enable,
            [session_state, sem_backend, sem_model,
             sem_threshold, sem_soft, sem_lev_max, sem_lev_typo,
             sem_local_path, sem_local_only, lang_state],
            [sem_msg, sem_status_json],
        ).then(
            handle_sem_status_html,
            [session_state, lang_state],
            [sem_badge],
        )

        sem_off_btn.click(
            handle_sem_disable,
            [session_state, lang_state],
            [sem_msg, sem_status_json],
        ).then(
            handle_sem_status_html,
            [session_state, lang_state],
            [sem_badge],
        )

        sem_set_btn.click(
            handle_sem_threshold,
            [session_state, sem_threshold, lang_state],
            [sem_msg, sem_status_json],
        ).then(
            handle_sem_status_html,
            [session_state, lang_state],
            [sem_badge],
        )

        sem_test_btn.click(
            handle_sem_compare,
            [session_state, sem_test_a, sem_test_b, lang_state],
            [sem_test_json],
        )

        # --- Diagnostics ---
        diag_btn.click(
            handle_diag,
            [session_state, lang_state],
            [diag_json],
        )

        # --- Editor ---
        reload_btn.click(
            handle_reload,
            [session_state, editor, lang_state],
            [editor_status],
        )
        check_btn.click(
            handle_check,
            [session_state, editor, lang_state],
            [editor_status],
        )
        clear_btn.click(
            lambda lang_code: (
                "",
                _status_html(t(lang_code, "status_cleared")),
            ),
            [lang_state],
            [editor, editor_status],
        )

        # --- Query / Stream ---
        run_btn.click(
            handle_run,
            [session_state, editor, query_input, timeout_input, lang_state],
            [results_json, results_out],
        )
        first_btn.click(
            handle_first,
            [session_state, editor, query_input, timeout_input, lang_state],
            [results_json, results_out],
        )
        stream_event = stream_btn.click(
            handle_stream,
            [session_state, editor, query_input, timeout_input, lang_state],
            [stream_out],
        )
        stop_btn.click(fn=lambda: None, cancels=[stream_event])

        # --- Trace ---
        trace_btn.click(
            handle_trace,
            [session_state, editor, query_input, timeout_input,
             bp_predicates, lang_state],
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
        bp_reset.click(
            handle_bp_reset,
            [session_state, lang_state],
            [bp_status],
        )
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