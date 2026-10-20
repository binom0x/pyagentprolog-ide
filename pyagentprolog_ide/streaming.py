"""Стриминг решений через agent.stream() с таймаутом на элемент."""
from __future__ import annotations

import queue
import threading
from typing import Any, Generator


def stream_with_timeout(agent, query: str, per_item_timeout: float = 30.0):
    q: "queue.Queue" = queue.Queue()
    error_box: dict = {}

    def worker():
        try:
            for sol in agent.stream(query):
                q.put(("item", sol))
        except BaseException as e:  # noqa: BLE001
            error_box["e"] = e
        finally:
            q.put(("done", None))

    threading.Thread(target=worker, daemon=True).start()

    while True:
        try:
            kind, value = q.get(timeout=per_item_timeout)
        except queue.Empty:
            yield {"error": f"Таймаут {per_item_timeout}s"}
            return
        if kind == "done":
            if "e" in error_box:
                yield {"error": str(error_box["e"])}
            return
        yield value