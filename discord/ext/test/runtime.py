"""Explicit ownership of asynchronous work started by a test session."""
from __future__ import annotations

import asyncio
from typing import Any, Coroutine, Optional, Set


class Runtime:
    """Track only registered work; never inspect or cancel unrelated tasks."""

    def __init__(self) -> None:
        self._tasks: Set[asyncio.Task[Any]] = set()
        self.errors: list[BaseException] = []
        self._closing = False

    def track(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        if self._closing:
            raise RuntimeError("runtime is closing")
        if task in self._tasks:
            return task
        self._tasks.add(task)
        task.add_done_callback(self._finished)
        return task

    def create_task(self, coroutine: Coroutine[Any, Any, Any], *,
                    name: Optional[str] = None) -> asyncio.Task[Any]:
        if self._closing:
            coroutine.close()
            raise RuntimeError("runtime is closing")
        return self.track(asyncio.create_task(coroutine, name=name))

    def _finished(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                self.errors.append(error)

    @property
    def pending(self) -> tuple[asyncio.Task[Any], ...]:
        return tuple(task for task in self._tasks if not task.done())

    async def close(self, timeout: float = 1.0) -> None:
        """Cancel owned work and bound the time spent waiting for cancellation."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._closing = True
        tasks = self.pending
        for task in tasks:
            task.cancel()
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=timeout)
            if pending:
                raise TimeoutError(f"{len(pending)} owned task(s) did not stop")
