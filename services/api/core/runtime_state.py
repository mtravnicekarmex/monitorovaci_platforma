from __future__ import annotations

from threading import Lock


class ApiReadinessState:
    def __init__(self) -> None:
        self._lock = Lock()
        self._ready = False

    def mark_ready(self) -> None:
        with self._lock:
            self._ready = True

    def mark_not_ready(self) -> None:
        with self._lock:
            self._ready = False

    def is_ready(self) -> bool:
        with self._lock:
            return self._ready


api_readiness = ApiReadinessState()
