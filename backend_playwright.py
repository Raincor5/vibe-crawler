from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

class PlaywrightBackend:
    def __init__(self, cfg, logger, proxy_settings: dict | None):
        self.cfg = cfg
        self.logger = logger
        self.proxy = proxy_settings
        self._pw = None
        self._browser = None

    async def _ensure(self):
        if self._browser:
            return
        self._pw = await async_playwright().start()
        browser_name = (self.cfg.playwright_browser or "firefox").lower()
        if browser_name not in ("firefox", "chromium", "webkit"):
            self.logger.warning(f"Unknown Playwright browser '{browser_name}', defaulting to firefox")
            browser_name = "firefox"
        launcher = getattr(self._pw, browser_name)
        self._browser = await launcher.launch(
            headless=self.cfg.headless,
            proxy=self.proxy,
        )
        self._browser_name = browser_name

    async def grab(self, task, timeout_ms: int, gather_links: bool = False) -> dict:
        await self._ensure()
        is_mobile_profile = self.cfg.device_type == "mobile"
        # Firefox does not support isMobile/hasTouch flags in new_context
        mobile_kwargs = {}
        if is_mobile_profile and self._browser_name != "firefox":
            mobile_kwargs = {
                "is_mobile": True,
                "has_touch": True,
                "device_scale_factor": 3,
            }
        context = await self._browser.new_context(
            user_agent=self.cfg.user_agent,
            locale=self.cfg.locale,
            timezone_id=self.cfg.timezone,
            viewport={"width": self.cfg.viewport[0], "height": self.cfg.viewport[1]},
            **mobile_kwargs,
        )
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)
        data = {}
        try:
            self.logger.info(f"[PW] goto {task.url}")
            await page.goto(task.url, timeout=timeout_ms)
            if task.wait_selector:
                await page.wait_for_selector(task.wait_selector, timeout=timeout_ms)
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
                            records.append({
                                "text": " ".join(raw_text.split()) if raw_text else "",
                                "html": raw_html
                            })
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
                except Exception as e:  # noqa
                    self.logger.warning(f"[PW] link collection failed: {e}")
        finally:
            await context.close()
        return data

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
