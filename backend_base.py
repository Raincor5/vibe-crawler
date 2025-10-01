from abc import ABC, abstractmethod

class BrowserBackend(ABC):
    @abstractmethod
    async def grab(self, task, timeout_ms: int) -> dict:
        ...

    @abstractmethod
    async def close(self):
        ...
