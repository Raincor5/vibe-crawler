import re
from collections import deque
from urllib.parse import urljoin, urldefrag, urlparse
from models import ScrapeTask
import asyncio
from typing import Optional

class Crawler:
    def __init__(self, scraper, logger, timeout_ms: int):
        self.scraper = scraper
        self.logger = logger
        self.timeout_ms = timeout_ms

    async def crawl(
        self,
        seeds: list[str],
        selectors: list[str],
        wait_selector: str | None,
        stem: str,
        max_pages: int,
        max_depth: int,
        same_domain: bool,
        allow_subdomains: bool,
        include_patterns: list[str] | None,
        exclude_patterns: list[str] | None,
        concurrency: int = 1,
        rate_limiter: Optional[object] = None,
    ) -> dict:
        if not seeds:
            return {}
        start_netloc = urlparse(seeds[0]).netloc.lower()
        root_domain = start_netloc.split(':')[0]
        # Very naive root for subdomain matching (split first label off if >2 parts)
        parts = root_domain.split('.')
        if len(parts) > 2:
            root_suffix = '.'.join(parts[-2:])
        else:
            root_suffix = root_domain

        inc_res = [re.compile(p) for p in (include_patterns or [])]
        exc_res = [re.compile(p) for p in (exclude_patterns or [])]

        def allowed(url: str) -> bool:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            netloc = parsed.netloc.lower()
            if exc_res and any(r.search(url) for r in exc_res):
                return False
            if inc_res and not any(r.search(url) for r in inc_res):
                return False
            if not same_domain:
                return True
            if allow_subdomains:
                return netloc.endswith(root_suffix)
            return netloc == start_netloc

        visited: set[str] = set()
        aggregated: dict = {}
        q = deque([(seed, 0) for seed in seeds])

        async def fetch(url: str, depth: int):
            norm = self._normalize(url)
            if norm in visited or not allowed(norm):
                return []
            visited.add(norm)
            self.logger.info(f"[CRAWL] Depth {depth} ({len(visited)}/{max_pages}): {norm}")
            if rate_limiter:
                await rate_limiter.acquire()
            task = ScrapeTask(url=norm, selectors=selectors, wait_selector=wait_selector, stem=stem)
            try:
                _path, cleaned, links = await self.scraper.run_task(task, self.timeout_ms, gather_links=True)
                aggregated[norm] = cleaned
                new_links = []
                if depth < max_depth:
                    for link in links:
                        full = self._resolve(norm, link)
                        if full and full not in visited and allowed(full):
                            new_links.append((full, depth + 1))
                return new_links
            except Exception as e:  # noqa
                self.logger.warning(f"[CRAWL] Error {norm}: {e}")
                return []

        while q and len(visited) < max_pages:
            batch = []
            while q and len(batch) < concurrency and len(visited) + len(batch) < max_pages:
                batch.append(q.popleft())
            if not batch:
                break
            if concurrency == 1:
                # Sequential
                for (url, depth) in batch:
                    new_links = await fetch(url, depth)
                    for item in new_links:
                        if len(visited) < max_pages:
                            q.append(item)
            else:
                tasks = [fetch(url, depth) for (url, depth) in batch]
                results = await asyncio.gather(*tasks)
                for new_links in results:
                    for item in new_links:
                        if len(visited) < max_pages:
                            q.append(item)
        return aggregated

    def _normalize(self, url: str) -> str:
        url, _frag = urldefrag(url)
        # Remove trailing slash (except root)
        if url.endswith('/') and len(url) > len('https://x.xx/'):
            url = url.rstrip('/')
        return url

    def _resolve(self, base: str, link: str) -> str | None:
        if not link:
            return None
        if link.startswith('javascript:') or link.startswith('mailto:') or link.startswith('#'):
            return None
        try:
            return self._normalize(urljoin(base, link))
        except Exception:  # noqa
            return None
