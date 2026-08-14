from __future__ import annotations

import time
from threading import Event


class ExperimentCancelled(Exception):
    """Raised when the operator cancels an active experiment."""


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()
        self._pause_event = Event()

    def cancel(self) -> None:
        self._event.set()
        self._pause_event.clear()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise ExperimentCancelled()

    def pause(self) -> None:
        self._pause_event.set()

    def resume(self) -> None:
        self._pause_event.clear()

    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def wait_until_resumed(self) -> None:
        while self.is_paused():
            self.raise_if_cancelled()
            time.sleep(0.05)
