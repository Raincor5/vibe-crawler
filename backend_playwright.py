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
        self._browser = await self._pw.firefox.launch(
            headless=self.cfg.headless,
            proxy=self.proxy,
        )

    async def grab(self, task, timeout_ms: int) -> dict:
        await self._ensure()
        is_mobile = self.cfg.device_type == "mobile"
        context = await self._browser.new_context(
            user_agent=self.cfg.user_agent,
            locale=self.cfg.locale,
            timezone_id=self.cfg.timezone,
            viewport={"width": self.cfg.viewport[0], "height": self.cfg.viewport[1]},
            is_mobile=is_mobile,
            has_touch=is_mobile,
            device_scale_factor=3 if is_mobile else 1,
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
                    vals = []
                    for el in els:
                        txt = (await el.inner_text()).strip()
                        if txt:
                            vals.append(" ".join(txt.split()))
                    data[sel] = vals
                except PlaywrightTimeoutError:
                    self.logger.warning(f"[PW] selector timeout {sel}")
        finally:
            await context.close()
        return data

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
