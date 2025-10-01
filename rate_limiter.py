import asyncio
import time
from collections import deque
from typing import Deque

class RateLimiter:
    """Asynchronous rate limiter.

    Modes:
    - max_per_interval: limit N acquisitions per rolling interval_seconds window.
    - min_delay_seconds: enforce at least this delay between consecutive acquisitions.
    Both can be combined.
    """
    def __init__(self, *, max_per_interval: int | None, interval_seconds: float, min_delay_seconds: float, logger=None):
        self.max_per_interval = max_per_interval
        self.interval_seconds = interval_seconds
        self.min_delay_seconds = min_delay_seconds
        self.logger = logger
        self._events: Deque[float] = deque()
        self._last_acquire: float | None = None
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            # Enforce min delay
            if self._last_acquire is not None and self.min_delay_seconds > 0:
                delta = now - self._last_acquire
                if delta < self.min_delay_seconds:
                    wait_time = self.min_delay_seconds - delta
                    if self.logger:
                        self.logger.debug(f"[RateLimiter] Sleeping {wait_time:.3f}s for min delay")
                    await asyncio.sleep(wait_time)
                    now = time.monotonic()
            # Enforce rolling window count
            if self.max_per_interval:
                window_start = now - self.interval_seconds
                while self._events and self._events[0] < window_start:
                    self._events.popleft()
                if len(self._events) >= self.max_per_interval:
                    # Need to wait until earliest leaves window
                    earliest = self._events[0]
                    wait_time = (earliest + self.interval_seconds) - now
                    if wait_time > 0:
                        if self.logger:
                            self.logger.debug(f"[RateLimiter] Window full; sleeping {wait_time:.3f}s")
                        await asyncio.sleep(wait_time)
                        now = time.monotonic()
                        # Cleanup again after sleep
                        window_start = now - self.interval_seconds
                        while self._events and self._events[0] < window_start:
                            self._events.popleft()
                self._events.append(now)
            self._last_acquire = time.monotonic()

