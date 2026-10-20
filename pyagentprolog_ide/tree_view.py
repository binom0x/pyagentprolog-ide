"""Рендер дерева доказательства в HTML + хелперы для gr.Dataframe."""
from __future__ import annotations

import html
from typing import Dict, List, Tuple

from prolog.tracer import ProofStep


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _render_step(step: ProofStep) -> str:
    cls = "step-ok" if step.success else "step-fail"
    if step.builtin:
        cls += " step-builtin"

    goal = _esc(step.goal)
    rule = (
        f' <span class="rule">⇐ {_esc(step.rule_used)}</span>'
        if step.rule_used else ""
    )
    unif = ""
    if step.unification:
        pairs = ", ".join(f"{_esc(v)}={_esc(val)}" for v, val in step.unification)
        unif = f' <span class="unif">[{pairs}]</span>'

    children = ""
    if step.children:
        inner = "".join(_render_step(c) for c in step.children)
        children = f"<ul>{inner}</ul>"

    return (
        f'<li class="{cls}" data-step-id="{_esc(step.id)}">'
        f'<span class="goal">{goal}</span>{rule}{unif}'
        f'{children}</li>'
    )


_TREE_CSS = """
<style>
  .prolog-tree {
    background: #0b0d11;
    color: #e6e6e6;
    border: 1px solid #2a313d;
    border-radius: 8px;
    padding: 12px 14px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 13px;
    max-height: 420px;
    overflow: auto;
  }
  .prolog-tree ul {
    list-style: none;
    padding-left: 1.1em;
    border-left: 1px dashed #2a313d;
    margin: 2px 0;
  }
  .prolog-tree li { margin: 1px 0; }
  .prolog-tree .step-ok  > .goal { color: #7ee787; font-weight: 600; }
  .prolog-tree .step-fail > .goal { color: #ff7b72; }
  .prolog-tree .step-builtin > .goal { color: #d2a8ff; font-style: italic; }
  .prolog-tree .rule { color: #8b949e; }
  .prolog-tree .unif { color: #79c0ff; }
  .prolog-tree .goal { white-space: pre-wrap; }
</style>
"""


def render_tree_html(root_steps: List[ProofStep]) -> str:
    if not root_steps:
        return (
            '<div class="prolog-tree" style="opacity:.7;">'
            'Дерево пусто — выполните Trace.</div>'
        )
    items = "".join(_render_step(s) for s in root_steps)
    return f'{_TREE_CSS}<div class="prolog-tree"><ul>{items}</ul></div>'


# ---------- Хелперы для Dataframe ----------
def flatten_steps(root_steps: List[ProofStep]) -> List[ProofStep]:
    out: List[ProofStep] = []

    def walk(s: ProofStep):
        out.append(s)
        for c in s.children:
            walk(c)

    for r in root_steps:
        walk(r)
    return out


def build_trace_artifacts(root_steps: List[ProofStep]
                          ) -> Tuple[List[List[str]], List[Dict]]:
    flat = flatten_steps(root_steps)
    rows = [
        [
            s.id,
            str(s.goal),
            str(s.rule_used or ""),
            "✓" if s.success else "✗",
            "builtin" if s.builtin else "rule",
        ]
        for s in flat
    ]
    dicts = [s.to_dict() for s in flat]
    return rows, dicts


def subst_rows_from_dict(step_dict: Dict) -> List[List[str]]:
    before = step_dict.get("subst_before") or {}
    after = step_dict.get("subst_after") or {}
    unif = step_dict.get("unification") or []

    rows: List[List[str]] = []
    if before or after:
        for v in sorted(set(before.keys()) | set(after.keys())):
            rows.append([str(v), str(before.get(v, "")), str(after.get(v, ""))])

    seen = {r[0] for r in rows}
    for v, val in unif:
        if str(v) not in seen:
            rows.append([str(v), "", str(val)])

    return rows