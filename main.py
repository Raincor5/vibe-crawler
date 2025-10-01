import asyncio
import argparse
import random
from pathlib import Path
import os
import sys
from config import Config
from logging_utils import LoggerFactory
from tor_proxy import TorProxyManager
from tor_rotation import TorRotator
from captcha import CaptchaSolver
from models import ScrapeTask
from cleaner import DataCleaner
from storage import DataStorage
from fingerprint import Fingerprint
from backend_playwright import PlaywrightBackend
from backend_selenium import SeleniumBackend
from scraper import Scraper
from crawler import Crawler
from rate_limiter import RateLimiter


# New helper to load seed file
def _load_seed_file(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Seed file not found: {p}")
    urls: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Auto-correct accidental backslashes in scheme
        if line.startswith('http:\\') or line.startswith('https:\\'):
            line = line.replace('\\', '/')
        urls.append(line)
    return urls


def _load_urls(args) -> list[str]:
    urls = []
    if args.url:
        urls.extend(args.url)
    if args.url_file:
        p = Path(args.url_file)
        if not p.exists():
            raise FileNotFoundError(f"URL file not found: {p}")
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)
    # de-dup preserve order
    seen = set()
    deduped = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped

async def main():
    p = argparse.ArgumentParser(description="Modular scraper (Tor mandatory) with optional site crawl + concurrency + rate limiting.")
    p.add_argument("url", nargs="*", help="One or more seed URLs (optional if --url-file or --seeds-file used)")
    p.add_argument("-s", "--selector", action="append", required=True, help="CSS selector(s) to extract (repeat)")
    p.add_argument("--wait", help="Selector to wait for before extraction")
    p.add_argument("--engine", choices=["playwright", "selenium"], default="playwright")
    p.add_argument("--use-proxy", action="store_true", help="(Deprecated) always on unless SCRAPER_PROXY=0")
    p.add_argument("--no-random", action="store_true", help="Disable fingerprint randomization (deterministic)")
    p.add_argument("--url-file", help="Path to file with newline-separated URLs")
    p.add_argument("--aggregate", action="store_true", help="Save a single aggregated JSON of all results (non-crawl mode)")
    p.add_argument("--retries", type=int, default=1, help="Retries per URL on failure (non-crawl mode)")
    p.add_argument("--retry-delay", type=float, default=2.0, help="Base seconds between retries")
    p.add_argument("--jitter", type=float, default=0.5, help="Random jitter (+/-) seconds added to delay between tasks")
    p.add_argument("--stem", default="scrape", help="Base filename stem for outputs")
    # Crawling options
    p.add_argument("--crawl", action="store_true", help="Enable recursive crawl from seed URLs")
    p.add_argument("--max-pages", type=int, default=50, help="Max pages to fetch during crawl")
    p.add_argument("--max-depth", type=int, default=3, help="Max link depth during crawl")
    p.add_argument("--allow-subdomains", action="store_true", help="Allow subdomains when restricting to same domain")
    p.add_argument("--cross-domain", action="store_true", help="Allow leaving the seed domain entirely")
    p.add_argument("--include", action="append", help="Regex URL include pattern (repeatable)")
    p.add_argument("--exclude", action="append", help="Regex URL exclude pattern (repeatable)")
    p.add_argument("--seeds-file", help="File containing seed URLs (one per line)")
    # Concurrency & rate limiting
    p.add_argument("--concurrency", type=int, help="Override max concurrency (default from env or 1)")
    p.add_argument("--rate-max", type=int, help="Max requests per interval (set 0 to disable)")
    p.add_argument("--rate-interval", type=float, help="Interval seconds for --rate-max window")
    p.add_argument("--rate-min-delay", type=float, help="Minimum delay seconds between requests")
    args = p.parse_args()

    # Config (respect deterministic flag)
    if args.no_random:
        prev = os.environ.get("SCRAPER_RANDOMIZE")
        os.environ["SCRAPER_RANDOMIZE"] = "0"
        cfg = Config.from_env()
        if prev is None:
            del os.environ["SCRAPER_RANDOMIZE"]
        else:
            os.environ["SCRAPER_RANDOMIZE"] = prev
    else:
        cfg = Config.from_env()

    cfg.engine = args.engine
    if not cfg.proxy_enabled:
        print("Tor proxy disabled via SCRAPER_PROXY=0; this build expects Tor. Exiting.")
        sys.exit(1)

    # Override concurrency / rate settings if provided
    if args.concurrency is not None:
        cfg.max_concurrency = max(1, args.concurrency)
    if args.rate_max is not None:
        cfg.rate_max_per_interval = (args.rate_max if args.rate_max > 0 else None)
    if args.rate_interval is not None:
        cfg.rate_interval_seconds = args.rate_interval
    if args.rate_min_delay is not None:
        cfg.rate_min_delay_seconds = args.rate_min_delay

    logger = LoggerFactory.create()

    urls = _load_urls(args)
    # Merge seeds from file if provided
    if getattr(args, 'seeds_file', None):
        try:
            urls.extend(_load_seed_file(args.seeds_file))
        except FileNotFoundError as e:
            logger = LoggerFactory.create()
            logger.error(str(e))
            sys.exit(3)
    # Fallback to seeds.txt if still empty and file exists
    if not urls and Path('seeds.txt').exists():
        urls = _load_seed_file('seeds.txt')

    if not urls:
        logger = LoggerFactory.create()
        logger.error("No URLs provided (positional, --seeds-file, seeds.txt, or --url-file).")
        return

    # De-duplicate after aggregating all sources
    dedup = []
    seen = set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            dedup.append(u)
    urls = dedup

    Fingerprint(cfg, LoggerFactory.create()).summary()

    tor_proxy = TorProxyManager(cfg.tor_socks_host, cfg.tor_socks_port, logger)
    proxy_settings = tor_proxy.playwright_proxy_settings()
    if not proxy_settings:
        logger.error("Tor SOCKS proxy unreachable. Ensure Tor is running on host:port.")
        sys.exit(2)

    tor_rotator = TorRotator(
        host=cfg.tor_socks_host,
        control_port=cfg.tor_control_port,
        password=cfg.tor_control_password,
        min_interval_s=cfg.tor_rotation_min_interval_s,
        request_threshold=cfg.tor_request_threshold,
        logger=logger
    )

    CaptchaSolver(cfg.captcha_api_key, logger)  # placeholder retained

    if cfg.engine == "playwright":
        backend = PlaywrightBackend(cfg, logger, proxy_settings)
    else:
        if cfg.max_concurrency > 1:
            logger.warning("Selenium backend does not support >1 concurrency reliably; forcing concurrency=1.")
            cfg.max_concurrency = 1
        backend = SeleniumBackend(cfg, logger, proxy_settings)

    cleaner = DataCleaner()
    storage = DataStorage(cfg.storage_dir, logger)
    scraper = Scraper(backend, cleaner, storage, logger, tor_rotator=tor_rotator)

    rate_limiter = None
    if cfg.rate_max_per_interval or cfg.rate_min_delay_seconds > 0:
        rate_limiter = RateLimiter(
            max_per_interval=cfg.rate_max_per_interval,
            interval_seconds=cfg.rate_interval_seconds,
            min_delay_seconds=cfg.rate_min_delay_seconds,
            logger=logger,
        )

    if args.crawl:
        crawler = Crawler(scraper, logger, cfg.timeout_ms)
        logger.info(
            f"Starting crawl: seeds={len(urls)} max_pages={args.max_pages} max_depth={args.max_depth} concurrency={cfg.max_concurrency}"
        )
        aggregated = await crawler.crawl(
            seeds=urls,
            selectors=args.selector,
            wait_selector=args.wait,
            stem=args.stem,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            same_domain=not args.cross_domain,
            allow_subdomains=args.allow_subdomains,
            include_patterns=args.include,
            exclude_patterns=args.exclude,
            concurrency=cfg.max_concurrency,
            rate_limiter=rate_limiter,
        )
        out_path = storage.save_json(aggregated, stem=f"{args.stem}_crawl")
        logger.info(f"Crawl complete. Pages: {len(aggregated)} saved: {out_path}")
    else:
        # Non-crawl multi-URL mode with optional concurrency.
        aggregated = {} if args.aggregate else None
        sem = asyncio.Semaphore(cfg.max_concurrency)
        results = []
        async def process(url: str, index: int):
            async with sem:
                if rate_limiter:
                    await rate_limiter.acquire()
                logger.info(f"Processing {index}/{len(urls)}: {url}")
                task = ScrapeTask(url=url, selectors=args.selector, wait_selector=args.wait, stem=args.stem)
                attempt = 0
                last_error = None
                while attempt < args.retries:
                    attempt += 1
                    try:
                        path, cleaned, _links = await scraper.run_task(task, cfg.timeout_ms, gather_links=False)
                        if aggregated is not None:
                            aggregated[url] = cleaned
                        logger.info(f"Success {url} (attempt {attempt}) saved {path}")
                        return True
                    except Exception as e:
                        last_error = e
                        logger.warning(f"Error scraping {url} attempt {attempt}: {e}")
                        if attempt < args.retries:
                            delay = args.retry_delay + random.uniform(-args.jitter, args.jitter)
                            delay = max(0.0, delay)
                            logger.info(f"Retrying in {delay:.2f}s...")
                            await asyncio.sleep(delay)
                logger.error(f"Failed {url} after {args.retries} attempts: {last_error}")
                return False
        if cfg.max_concurrency > 1:
            tasks = [process(u, i+1) for i, u in enumerate(urls)]
            await asyncio.gather(*tasks)
        else:
            for i, u in enumerate(urls):
                await process(u, i+1)
                if i < len(urls)-1 and cfg.max_concurrency == 1 and not rate_limiter:
                    pause = args.jitter + random.uniform(0, args.jitter)
                    await asyncio.sleep(pause)
        if aggregated is not None:
            out_path = storage.save_json(aggregated, stem=f"{args.stem}_aggregate")
            logger.info(f"Aggregated output saved: {out_path}")

    try:
        await scraper.close()
    finally:
        logger.info("Done.")

if __name__ == "__main__":
    asyncio.run(main())
