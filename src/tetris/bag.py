"""7-bag randomizer: shuffle all 7 pieces, deal one at a time, repeat."""

from __future__ import annotations

import random
from collections import deque

from .pieces import ALL_KINDS


class Bag:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._queue: deque[str] = deque()
        self._refill()
        self._refill()  # keep queue long enough for a 5-piece preview

    def _refill(self) -> None:
        pieces = list(ALL_KINDS)
        self._rng.shuffle(pieces)
        self._queue.extend(pieces)

    def next(self) -> str:
        if len(self._queue) <= 7:
            self._refill()
        return self._queue.popleft()

    def preview(self, n: int = 5) -> list[str]:
        return [self._queue[i] for i in range(n)]
