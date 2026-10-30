"""Session-local, immutable observations of simulated Discord activity."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    raise TypeError(f"Unsupported observation value: {type(value).__name__}")


@dataclass(frozen=True)
class Observation:
    sequence: int
    timestamp: float
    direction: str
    kind: str
    payload: Mapping[str, Any]
    action_id: Optional[int] = None
    visibility: Optional[str] = None


class Transcript:
    """Non-consuming observations and checkpoints, owned by one session."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._records: list[Observation] = []
        self._changed = asyncio.Event()

    def checkpoint(self) -> int:
        return len(self._records)

    def record(self, direction: str, kind: str, payload: Mapping[str, Any], *,
               action_id: Optional[int] = None, visibility: Optional[str] = None) -> Observation:
        observation = Observation(len(self._records) + 1, self._clock(), direction, kind,
                                  _freeze(payload), action_id, visibility)
        self._records.append(observation)
        self._changed.set()
        return observation

    def query(self, *, after: int = 0, kind: Optional[str] = None,
              action_id: Optional[int] = None, direction: Optional[str] = None,
              channel_id: Optional[int] = None, author_id: Optional[int] = None,
              message_id: Optional[int] = None, interaction_id: Optional[int] = None,
              visibility: Optional[str] = None, visible_to: Optional[int] = None) -> tuple[Observation, ...]:
        """Return history without consuming it. Omitting visibility is an administrative query."""
        if after < 0 or after > len(self._records):
            raise ValueError("checkpoint is outside this transcript")

        def matches(record: Observation) -> bool:
            payload = record.payload
            author = payload.get('author')
            author_value = author.get('id') if isinstance(author, Mapping) else payload.get('author_id')
            message_value = payload.get('message_id', payload.get('id'))
            interaction_value = payload.get('interaction_id', record.action_id)
            return ((kind is None or record.kind == kind)
                    and (action_id is None or record.action_id == action_id)
                    and (direction is None or record.direction == direction)
                    and (channel_id is None or str(payload.get('channel_id')) == str(channel_id))
                    and (author_id is None or str(author_value) == str(author_id))
                    and (message_id is None or str(message_value) == str(message_id))
                    and (interaction_id is None or str(interaction_value) == str(interaction_id))
                    and (visibility is None or record.visibility == visibility)
                    and (visible_to is None or record.visibility in ('public', f'user:{visible_to}')))
        return tuple(record for record in self._records[after:] if matches(record))

    async def _find(self, predicate: Callable[[Observation], bool], after: int) -> Observation:
        cursor = after
        while True:
            records = self.query(after=cursor)
            cursor += len(records)
            for record in records:
                if predicate(record):
                    return record
            self._changed.clear()
            await self._changed.wait()

    async def expect(self, predicate: Callable[[Observation], bool], *, after: int = 0,
                     timeout: float = 1.0) -> Observation:
        """Wait for a matching record without consuming history or waiting for idle."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")

        try:
            return await asyncio.wait_for(self._find(predicate, after), timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"No matching observation after checkpoint {after}; "
                               f"recent observations: {self._records[-5:]!r}") from exc

    async def expect_none(self, predicate: Callable[[Observation], bool], *, after: int,
                          timeout: float) -> None:
        """Assert no matching observation occurs during a bounded real-time window."""
        if timeout <= 0:
            raise ValueError('timeout must be positive')
        task = asyncio.create_task(self._find(predicate, after))
        try:
            done, _ = await asyncio.wait({task}, timeout=timeout)
            if not done:
                return
            match = task.result()
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        raise AssertionError(f'Unexpected observation after checkpoint {after}: {match!r}')
