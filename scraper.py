class Scraper:
    def __init__(self, backend, cleaner, storage, logger, tor_rotator=None):
        self.backend = backend
        self.cleaner = cleaner
        self.storage = storage
        self.logger = logger
        self.tor_rotator = tor_rotator

    async def run_task(self, task, timeout_ms: int):
        raw = await self.backend.grab(task, timeout_ms)
        cleaned = self.cleaner.normalize(raw)
        path = self.storage.save_json(cleaned, stem=task.stem)
        if self.tor_rotator:
            self.tor_rotator.incr()
            await self.tor_rotator.maybe_rotate()
        return path, cleaned

    async def close(self):
        await self.backend.close()
