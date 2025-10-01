from dataclasses import dataclass
from typing import List

@dataclass
class ScrapeTask:
    url: str
    selectors: List[str]
    wait_selector: str | None = None
    stem: str = "scrape"
