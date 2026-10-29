"""Совместимость с Gradio 4/5/6."""
from __future__ import annotations

from typing import Optional

import gradio as gr

try:
    _GRADIO_MAJOR = int(str(gr.__version__).split(".")[0])
except Exception:
    _GRADIO_MAJOR = 4


# ---------- gr.Code ----------
def _supported_code_languages():
    try:
        import gradio.components.code as m
    except Exception:
        return None
    for name in ("SUPPORTED_LANGUAGES", "CODE_LANGUAGES", "LANGUAGES"):
        langs = getattr(m, name, None)
        if isinstance(langs, (list, tuple, set, frozenset)):
            return set(langs)
    return None


_lang_cache: Optional[str] = None


def code_language() -> str:
    global _lang_cache
    if _lang_cache is not None:
        return _lang_cache
    if _GRADIO_MAJOR >= 6:
        _lang_cache = "python"
        return _lang_cache
    langs = _supported_code_languages()
    if langs is not None:
        _lang_cache = "prolog" if "prolog" in langs else "python"
        return _lang_cache
    try:
        gr.Code(value="", language="prolog")
        _lang_cache = "prolog"
    except Exception:
        _lang_cache = "python"
    return _lang_cache


# ---------- Тема ----------
def dark_theme():
    """Тёмная тема для gr.Blocks/launch."""
    return gr.themes.Soft(
        primary_hue="indigo",
        secondary_hue="slate",
        neutral_hue="slate",
        font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui"],
    ).set(
        body_background_fill="#0f1115",
        body_background_fill_dark="#0f1115",
        body_text_color="#e6e6e6",
        body_text_color_dark="#e6e6e6",
        background_fill_primary="#161a20",
        background_fill_primary_dark="#161a20",
        background_fill_secondary="#1c212a",
        background_fill_secondary_dark="#1c212a",
        border_color_primary="#2a313d",
        border_color_primary_dark="#2a313d",
        block_background_fill="#161a20",
        block_border_color="#2a313d",
        block_label_background_fill="#1c212a",
        block_label_text_color="#c7cbd1",
        block_title_text_color="#c7cbd1",
        input_background_fill="#0f1115",
        input_border_color="#2a313d",
        input_placeholder_color="#7a808a",
        button_primary_background_fill="#4f46e5",
        button_primary_background_fill_hover="#6366f1",
        button_primary_text_color="#ffffff",
        button_secondary_background_fill="#232936",
        button_secondary_background_fill_hover="#2a313d",
        button_secondary_text_color="#e6e6e6",
        code_background_fill="#0b0d11",
        shadow_drop="none",
    )


# ---------- Blocks / launch kwargs ----------
# В Gradio 4/5 theme и css передаются в Blocks();
# в Gradio 6 — в launch(). CSS опционален: если передан — идёт туда же,
# где и theme, в зависимости от версии.

def blocks_kwargs(css: str = "", head: str = "") -> dict:
    d = {"title": "PyAgentProlog IDE"}
    if _GRADIO_MAJOR < 6:
        d["theme"] = dark_theme()
        if css:
            d["css"] = css
        if head:
            d["head"] = head
    return d


def launch_kwargs(css: str = "", head: str = "") -> dict:
    d = {}
    if _GRADIO_MAJOR >= 6:
        d["theme"] = dark_theme()
        if css:
            d["css"] = css
        if head:
            d["head"] = head
    return d