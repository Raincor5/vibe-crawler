from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from config import UA_PROFILES  # for alternative profiles
import random
import asyncio

class PlaywrightBackend:
    def __init__(self, cfg, logger, proxy_settings: dict | None, tor_rotator=None):
        self.cfg = cfg
        self.logger = logger
        self.proxy = proxy_settings
        self._pw = None
        self._browser = None
        self._browser_name = None
        self.tor_rotator = tor_rotator
        self._last_ua = cfg.user_agent

    async def _launch(self):
        if not self._pw:
            self._pw = await async_playwright().start()
        browser_name = (self.cfg.playwright_browser or "firefox").lower()
        if browser_name not in ("firefox", "chromium", "webkit"):
            self.logger.warning(f"Unknown Playwright browser '{browser_name}', defaulting to firefox")
            browser_name = "firefox"
        launcher = getattr(self._pw, browser_name)
        self._browser = await launcher.launch(headless=self.cfg.headless, proxy=self.proxy)
        self._browser_name = browser_name

    async def _ensure(self):
        if not self._browser:
            await self._launch()

    async def _relaunch_for_retry(self):
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        self._browser = None
        await self._launch()

    async def grab(self, task, timeout_ms: int, gather_links: bool = False) -> dict:
        await self._ensure()
        attempts = self.cfg.antibot_retry_limit if getattr(self.cfg, 'antibot_enable', False) else 1
        delay = getattr(self.cfg, 'antibot_backoff_seconds', 2.0)
        attempt = 0
        last_data = {}
        base_mobile_allowed = (self.cfg.device_type == "mobile") and ((self.cfg.playwright_browser or '').lower() != 'firefox')
        while attempt < attempts:
            attempt += 1
            # Fresh browser & Tor rotation on retries
            if attempt > 1:
                if self.cfg.antibot_fresh_browser:
                    self.logger.info(f"[ANTIBOT] Relaunching browser for attempt {attempt}")
                    await self._relaunch_for_retry()
                if self.cfg.antibot_force_tor and self.tor_rotator:
                    self.logger.info(f"[ANTIBOT] Forcing Tor circuit rotation before attempt {attempt}")
                    try:
                        await self.tor_rotator.force_rotate()
                        # small pause to let circuit establish
                        await asyncio.sleep(1.0)
                    except Exception:
                        pass
            # Decide profile (rerandomize if enabled & attempt > 1)
            if attempt > 1 and self.cfg.antibot_rerandomize:
                candidates = [p for p in UA_PROFILES if p.user_agent != self._last_ua]
                if candidates:
                    prof = random.choice(candidates)
                    user_agent = prof.user_agent
                    viewport_tuple = random.choice(prof.viewports)
                    locale = prof.accept_languages[0].split(',')[0]
                    timezone_id = random.choice(prof.timezones)
                    is_mobile_profile = (prof.device_type == 'mobile') and (self._browser_name != 'firefox')
                else:
                    user_agent = self.cfg.user_agent
                    viewport_tuple = self.cfg.viewport
                    locale = self.cfg.locale
                    timezone_id = self.cfg.timezone
                    is_mobile_profile = base_mobile_allowed
            else:
                user_agent = self.cfg.user_agent
                viewport_tuple = self.cfg.viewport
                locale = self.cfg.locale
                timezone_id = self.cfg.timezone
                is_mobile_profile = base_mobile_allowed
            self._last_ua = user_agent
            mobile_kwargs = {}
            if is_mobile_profile and self._browser_name != "firefox":
                mobile_kwargs = {"is_mobile": True, "has_touch": True, "device_scale_factor": 3}
            context = await self._browser.new_context(
                user_agent=user_agent,
                locale=locale,
                timezone_id=timezone_id,
                viewport={"width": viewport_tuple[0], "height": viewport_tuple[1]},
                **mobile_kwargs,
            )
            page = await context.new_page()
            page.set_default_timeout(timeout_ms)
            data = {}
            blocked = False
            html_snapshot = ""
            try:
                self.logger.info(f"[PW] goto {task.url} (attempt {attempt}/{attempts})")
                await page.goto(task.url, timeout=timeout_ms)
                if task.wait_selector:
                    await page.wait_for_selector(task.wait_selector, timeout=timeout_ms)
                try:
                    html_snapshot = await page.content()
                except Exception:
                    html_snapshot = ""
                low = html_snapshot.lower() if html_snapshot else ""
                patterns = [
                    'cf-browser-verification', 'attention required! | cloudflare', '/cdn-cgi/challenge-platform/',
                    'just a moment...', 'captcha', 'access denied', '_incapsula_resource', 'akamai bot manager',
                    'request unsuccessful. inappropriate content', 'blocked because of unusual activity'
                ]
                for pat in patterns:
                    if pat in low:
                        blocked = True
                        break
                for sel in task.selectors:
                    try:
                        els = await page.query_selector_all(sel)
                        records = []
                        for el in els:
                            try:
                                raw_text = (await el.inner_text()).strip()
                            except Exception:
                                raw_text = ""
                            try:
                                raw_html = await el.inner_html()
                            except Exception:
                                raw_html = ""
                            if raw_text or raw_html:
                                records.append({"text": " ".join(raw_text.split()) if raw_text else "", "html": raw_html})
                        data[sel] = records
                    except PlaywrightTimeoutError:
                        self.logger.warning(f"[PW] selector timeout {sel}")
                if gather_links:
                    try:
                        anchor_els = await page.query_selector_all('a')
                        links = []
                        for a in anchor_els:
                            href = await a.get_attribute('href')
                            if href:
                                links.append(href.strip())
                        data['__links__'] = links
                    except Exception as e:
                        self.logger.warning(f"[PW] link collection failed: {e}")
                data['__page_html__'] = html_snapshot
                data['__blocked__'] = blocked
                data['__attempt__'] = attempt
                data['__fingerprint__'] = {
                    'user_agent': user_agent,
                    'locale': locale,
                    'timezone': timezone_id,
                    'viewport': viewport_tuple,
                    'mobile': is_mobile_profile,
                    'browser': self._browser_name,
                }
                last_data = data
                if not blocked:
                    await context.close()
                    return data
                else:
                    self.logger.warning(f"[ANTIBOT] Block heuristic matched attempt {attempt}")
            except Exception as e:
                self.logger.warning(f"[PW] error attempt {attempt}: {e}")
                last_data = {"__error__": str(e), "__blocked__": True, "__attempt__": attempt}
            finally:
                try:
                    await context.close()
                except Exception:
                    pass
            if attempt < attempts:
                await asyncio.sleep(delay)
        return last_data

    async def close(self):
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
