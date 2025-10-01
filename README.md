# Web Scraping Toolkit

Modular, ethical scraping utility supporting Playwright or Selenium, Tor SOCKS proxy usage & circuit rotation, user-agent & fingerprint profile randomization, per-task data cleaning, JSON storage, retry logic, and optional aggregation of results.

## Features
- Dual backend: Playwright (async) or Selenium (Firefox/Chrome)
- UA profile system with viewport & locale/timezone alignment (desktop/mobile)
- Tor SOCKS proxy support + controlled circuit rotation via NEWNYM (stem library)
- Deterministic mode (`--no-random`) for reproducibility
- Multi-URL scraping (positional URLs or `--url-file`)
- Retry logic with jitter and pacing
- Optional aggregated output JSON
- Simple data normalization & de-duplication
- Pluggable captcha solver placeholder

## Quick Start
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
playwright install firefox  # if using Playwright backend
```

Optional: install Chrome/Firefox locally for Selenium backend.

## Tor Setup
Edit your Tor `torrc` (location varies) and add:
```
ControlPort 9051
CookieAuthentication 1
# OR (choose one auth method):
# HashedControlPassword <output of: tor --hash-password YOUR_PASS>
```
Restart Tor. Ensure SOCKS port (default 9050) is open.

## Environment Variables (see `.env.example`)
| Variable | Purpose | Default |
|----------|---------|---------|
| SCRAPER_PROXY | Enable proxy usage when set to `1` | 0 |
| TOR_SOCKS_HOST | Tor SOCKS host | 127.0.0.1 |
| TOR_SOCKS_PORT | Tor SOCKS port | 9050 |
| TOR_CONTROL_PORT | Tor control port | 9051 |
| TOR_CONTROL_PASSWORD | Control password (omit if cookie) | (none) |
| TOR_ROTATE_MIN_S | Min seconds between rotations | 10 |
| TOR_ROTATE_REQ_THRESHOLD | Requests needed before rotation | 5 |
| SCRAPER_RANDOMIZE | Toggle fingerprint randomization | 1 |
| SCRAPER_HEADLESS | Headless mode (1/0) | 1 |
| SCRAPER_TIMEOUT_MS | Per-page timeout ms | 15000 |
| SCRAPER_STORAGE | Output directory | data |
| SCRAPER_ENGINE | Default engine | playwright |

## Usage Examples
Single URL:
```bash
python main.py https://example.com -s h1 -s p
```
Multiple URLs inline with aggregation:
```bash
python main.py https://example.com https://httpbin.org/headers -s body --aggregate
```
From file:
```bash
python main.py -s h1 --url-file urls.txt --engine selenium --retries 2
```
Enable Tor + rotation (env first):
```bash
source export_env.sh
python main.py https://httpbin.org/ip -s body --use-proxy --retries 2
```
Deterministic (no random fingerprint):
```bash
python main.py https://example.com -s h1 --no-random
```

## Output
Each task creates `data/<stem>_YYYYMMDDTHHMMSSZ.json`. When `--aggregate` is used, an additional `data/<stem>_aggregate_...json` is saved.

## Extending
- Add new UA profiles: edit `config.py` `UA_PROFILES`.
- Additional extraction logic: extend backend `grab` or post-process in `DataCleaner`.
- Captcha integration: replace placeholder in `captcha.py` with real provider API calls respecting provider TOS.
- Rate limiting: add adaptive delays or token bucket in main loop.

## Testing (suggestion)
Add pytest tests under `tests/` (not included) to validate:
- UA profile conformity (viewport vs device type)
- DataCleaner normalization
- TorRotator rotation trigger logic (mock stem)

## Important Notes
Use only on sites you are authorized to scrape. Respect `robots.txt`, Terms of Service, legal and ethical considerations.

## Roadmap Ideas
- robots.txt fetch & compliance check
- Pluggable pipelines (transform/export formats: CSV, Parquet)
- Concurrency with bounded parallel contexts for Playwright
- Structured logging (JSON) and metrics hooks

---
MIT-style usage (add a LICENSE file if you plan to distribute).

