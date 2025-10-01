from abc import ABC, abstractmethod

class BrowserBackend(ABC):
    @abstractmethod
    async def grab(self, task, timeout_ms: int, gather_links: bool = False) -> dict:
        ...

    @abstractmethod
    async def close(self):
        ...
