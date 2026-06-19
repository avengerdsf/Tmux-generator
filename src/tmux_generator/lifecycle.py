from __future__ import annotations

from collections.abc import Callable
import threading
import time


class PageLifecycle:
    def __init__(
        self,
        timeout_seconds: float = 30,
        now: Callable[[], float] = time.monotonic,
        on_active: Callable[[], None] | None = None,
        on_idle: Callable[[], None] | None = None,
        timer_factory=threading.Timer,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.now = now
        self.on_active = on_active
        self.on_idle = on_idle
        self.timer_factory = timer_factory
        self._pages: dict[str, float] = {}
        self._active = False
        self._lock = threading.Lock()
        self._timer = None

    def heartbeat(self, page_id: str) -> dict:
        with self._lock:
            self._pages[page_id] = self.now()
            return self._status_locked()

    def leave(self, page_id: str) -> dict:
        with self._lock:
            self._pages.pop(page_id, None)
            return self._status_locked()

    def status(self) -> dict:
        with self._lock:
            return self._status_locked()

    def _status_locked(self) -> dict:
        cutoff = self.now() - self.timeout_seconds
        self._pages = {page_id: seen for page_id, seen in self._pages.items() if seen >= cutoff}
        active = bool(self._pages)
        if active != self._active:
            self._active = active
            callback = self.on_active if active else self.on_idle
            if callback:
                callback()
        self._schedule_cleanup_locked()
        return {"active_pages": len(self._pages), "active": active}

    def _schedule_cleanup_locked(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if not self._pages:
            return
        self._timer = self.timer_factory(self.timeout_seconds, self.status)
        self._timer.daemon = True
        self._timer.start()
