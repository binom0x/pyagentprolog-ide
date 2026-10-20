"""Точки останова через подмену ProofTracer.end_goal.

Синхронная модель: solver-поток блокируется на `_resume_event`,
UI пробуждает через `resume(action)`.
"""
from __future__ import annotations

import threading
from typing import Iterable, Optional, Set

from prolog.tracer import ProofStep, ProofTracer


class AbortException(Exception):
    """Пользователь нажал Abort на точке останова."""


class BreakpointController:
    def __init__(self):
        self.breakpoints: Set[str] = set()
        self._paused = threading.Event()
        self._resume = threading.Event()
        self._lock = threading.RLock()
        self._action = "continue"
        self.current_step: Optional[ProofStep] = None
        self._hits = 0

    # --- предикаты ---
    @staticmethod
    def _pred_of(goal_str: str) -> str:
        s = goal_str.strip()
        for sep in ("(", " ", ",", ")", ";"):
            i = s.find(sep)
            if i > 0:
                return s[:i]
        return s

    def should_pause(self, step: ProofStep) -> bool:
        return self._pred_of(step.goal) in self.breakpoints

    # --- solver thread ---
    def on_end_goal(self, step: ProofStep) -> None:
        if not self.should_pause(step):
            return
        with self._lock:
            self.current_step = step
            self._action = "continue"
            self._hits += 1
            self._paused.set()
        self._resume.wait()
        self._resume.clear()
        with self._lock:
            action = self._action
            self.current_step = None
            self._paused.clear()
        if action == "abort":
            raise AbortException()

    # --- UI ---
    def resume(self, action: str = "continue") -> None:
        with self._lock:
            if not self._paused.is_set():
                return
            self._action = action
        self._resume.set()

    def reset(self) -> None:
        with self._lock:
            self._paused.clear()
            self._resume.clear()
            self.current_step = None
            self._hits = 0
            self._action = "continue"

    def set_breakpoints(self, predicates: Iterable[str]) -> None:
        with self._lock:
            self.breakpoints = {p.strip() for p in predicates if p.strip()}

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def hit_count(self) -> int:
        return self._hits


class BreakpointTracer(ProofTracer):
    """ProofTracer, который дёргает controller.on_end_goal после каждого шага."""

    def __init__(self, controller: BreakpointController):
        super().__init__()
        self.controller = controller

    def end_goal(self, success: bool = True):
        step = self.step_stack[-1] if self.step_stack else None
        super().end_goal(success)
        if step is not None:
            self.controller.on_end_goal(step)  # может бросить AbortException