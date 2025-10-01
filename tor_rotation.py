import asyncio
import time
from contextlib import suppress

try:
    from stem import Signal
    from stem.control import Controller
except ImportError:
    Signal = None
    Controller = None

class TorRotator:
    def __init__(self, host, control_port, password, min_interval_s, request_threshold, logger):
        self.host = host
        self.control_port = control_port
        self.password = password
        self.min_interval_s = min_interval_s
        self.request_threshold = request_threshold
        self.logger = logger
        self._last = 0.0
        self._count = 0
        self._lock = asyncio.Lock()

    def _can_rotate(self):
        return (time.time() - self._last) >= self.min_interval_s and self._count >= self.request_threshold

    def incr(self):
        self._count += 1

    async def maybe_rotate(self):
        async with self._lock:
            if not self._can_rotate():
                return False
            if not (Controller and Signal):
                self.logger.warning("stem not available; skip Tor rotation.")
                return False
            try:
                with Controller.from_port(address=self.host, port=self.control_port) as c:
                    if self.password:
                        c.authenticate(password=self.password)
                    else:
                        with suppress(Exception):
                            c.authenticate()
                    c.signal(Signal.NEWNYM)
                    self._last = time.time()
                    self._count = 0
                    self.logger.info("Tor NEWNYM requested.")
                    return True
            except Exception as e:
                self.logger.warning(f"Tor rotation failed: {e}")
                return False
