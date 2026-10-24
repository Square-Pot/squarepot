# SPDX-License-Identifier: AGPL-3.0-or-later
"""Backing off clients that keep sending a wrong API token.

Each client, by IP address, has a bucket of failed attempts that refills
with time. A wrong or missing token takes one; while the bucket is empty, the
client's requests are refused without the token being checked, so guessing
stops. A correct token takes nothing. The state is in memory, bounded, and
lost on restart.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field

FAILURES = 10
REFILL_SECONDS = 60.0
MAX_CLIENTS = 10_000


@dataclass
class Backoff:
    capacity: int = FAILURES
    refill_seconds: float = REFILL_SECONDS
    max_clients: int = MAX_CLIENTS
    clock: Callable[[], float] = time.monotonic
    # Client to the attempts left in its bucket and when that was counted, oldest first.
    buckets: OrderedDict[str, tuple[float, float]] = field(default_factory=OrderedDict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def left(self, client: str, now: float) -> float:
        attempts, counted = self.buckets.get(client, (self.capacity, now))
        return min(self.capacity, attempts + (now - counted) / self.refill_seconds)

    def retry_after(self, client: str) -> int | None:
        """Seconds until the client may try a token again, or None when it may now."""
        with self.lock:
            left = self.left(client, self.clock())
        return None if left >= 1 else math.ceil((1 - left) * self.refill_seconds)

    def fail(self, client: str) -> bool:
        """Count a failed attempt; True when it was the client's last one."""
        with self.lock:
            now = self.clock()
            left = self.left(client, now) - 1
            self.buckets[client] = (left, now)
            self.buckets.move_to_end(client)
            while len(self.buckets) > self.max_clients:
                self.buckets.popitem(last=False)
        return left < 1
