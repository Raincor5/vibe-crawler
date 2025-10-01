import asyncio
import argparse
import random
from pathlib import Path
import os
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
    p = argparse.ArgumentParser(description="Modular ethical scraper with Tor rotation.")
    p.add_argument("url", nargs="*", help="One or more URLs (optional if --url-file used)")
    p.add_argument("-s", "--selector", action="append", required=True, help="CSS selector(s) to extract (repeat)")
    p.add_argument("--wait", help="Selector to wait for before extraction")
    p.add_argument("--engine", choices=["playwright", "selenium"], default="playwright")
    p.add_argument("--use-proxy", action="store_true", help="Enable Tor SOCKS proxy if reachable")
    p.add_argument("--no-random", action="store_true", help="Disable fingerprint randomization (deterministic)")
    p.add_argument("--url-file", help="Path to file with newline-separated URLs")
    p.add_argument("--aggregate", action="store_true", help="Save a single aggregated JSON of all results")
    p.add_argument("--retries", type=int, default=1, help="Retries per URL on failure")
    p.add_argument("--retry-delay", type=float, default=2.0, help="Base seconds between retries")
    p.add_argument("--jitter", type=float, default=0.5, help="Random jitter (+/-) seconds added to delay between tasks")
    p.add_argument("--stem", default="scrape", help="Base filename stem for per-URL outputs")
    args = p.parse_args()

    # Config creation (respect --no-random) by temporarily adjusting env before from_env
    if args.no_random:
        # Ensure deterministic profile usage
        # We do not mutate global env permanently; just create config then restore.
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
    if args.use_proxy:
        cfg.proxy_enabled = True

    logger = LoggerFactory.create()

    urls = _load_urls(args)
    if not urls:
        logger.error("No URLs provided. Use positional URLs or --url-file.")
        return

    Fingerprint(cfg, logger).summary()

    tor_proxy = TorProxyManager(cfg.tor_socks_host, cfg.tor_socks_port, logger)
    proxy_settings = tor_proxy.playwright_proxy_settings() if cfg.proxy_enabled else None

    tor_rotator = TorRotator(
        host=cfg.tor_socks_host,
        control_port=cfg.tor_control_port,
        password=cfg.tor_control_password,
        min_interval_s=cfg.tor_rotation_min_interval_s,
        request_threshold=cfg.tor_request_threshold,
        logger=logger
    ) if cfg.proxy_enabled else None

    CaptchaSolver(cfg.captcha_api_key, logger)  # placeholder kept

    if cfg.engine == "playwright":
        backend = PlaywrightBackend(cfg, logger, proxy_settings)
    else:
        backend = SeleniumBackend(cfg, logger, proxy_settings)

    cleaner = DataCleaner()
    storage = DataStorage(cfg.storage_dir, logger)
    scraper = Scraper(backend, cleaner, storage, logger, tor_rotator=tor_rotator)

    aggregated = {} if args.aggregate else None

    for idx, url in enumerate(urls, start=1):
        logger.info(f"Processing {idx}/{len(urls)}: {url}")
        task = ScrapeTask(url=url, selectors=args.selector, wait_selector=args.wait, stem=args.stem)
        attempt = 0
        success = False
        last_error = None
        while attempt < args.retries and not success:
            attempt += 1
            try:
                path, cleaned = await scraper.run_task(task, cfg.timeout_ms)
                success = True
                if aggregated is not None:
                    aggregated[url] = cleaned
                logger.info(f"Success {url} (attempt {attempt}) saved {path}")
            except Exception as e:  # broad catch to allow retry
                last_error = e
                logger.warning(f"Error scraping {url} attempt {attempt}: {e}")
                if attempt < args.retries:
                    delay = args.retry_delay + random.uniform(-args.jitter, args.jitter)
                    delay = max(0.0, delay)
                    logger.info(f"Retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
        if not success:
            logger.error(f"Failed {url} after {args.retries} attempts: {last_error}")
        # Inter-task pacing (jitter) if not last
        if idx < len(urls):
            pause = args.jitter + random.uniform(0, args.jitter)
            await asyncio.sleep(pause)

    if aggregated is not None:
        out_path = storage.save_json(aggregated, stem=f"{args.stem}_aggregate")
        logger.info(f"Aggregated output saved: {out_path}")

    try:
        if scraper:
            await scraper.close()
    finally:
        logger.info("Done.")

if __name__ == "__main__":
    asyncio.run(main())
