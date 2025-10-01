import asyncio
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FxOptions
from selenium.webdriver.chrome.options import Options as ChOptions

class SeleniumBackend:
    def __init__(self, cfg, logger, proxy_settings: dict | None):
        self.cfg = cfg
        self.logger = logger
        self.proxy = proxy_settings
        self.driver = None

    async def _ensure(self):
        if self.driver:
            return
        ua = self.cfg.user_agent.lower()
        # Firefox branch
        if "firefox" in ua and "chrome" not in ua:
            opts = FxOptions()
            if self.cfg.headless:
                opts.add_argument("-headless")
            profile = webdriver.FirefoxProfile()
            profile.set_preference("intl.accept_languages", self.cfg.accept_language)
            if self.proxy:
                host_port = self.proxy["server"].replace("socks5://", "")
                host, port = host_port.split(":")
                profile.set_preference("network.proxy.type", 1)
                profile.set_preference("network.proxy.socks", host)
                profile.set_preference("network.proxy.socks_port", int(port))
                profile.set_preference("network.proxy.socks_remote_dns", True)
            profile.update_preferences()
            opts.set_preference("general.useragent.override", self.cfg.user_agent)
            self.driver = webdriver.Firefox(options=opts, firefox_profile=profile)
        else:
            opts = ChOptions()
            if self.cfg.headless:
                opts.add_argument("--headless=new")
            opts.add_argument(f"--user-agent={self.cfg.user_agent}")
            opts.add_argument(f"--lang={self.cfg.locale}")
            if self.proxy:
                opts.add_argument(f"--proxy-server={self.proxy['server']}")
            # Basic mobile emulation hook (only if mobile UA)
            if self.cfg.device_type == "mobile":
                w, h = self.cfg.viewport
                opts.add_experimental_option("mobileEmulation", {
                    "userAgent": self.cfg.user_agent,
                    "deviceMetrics": {"width": w, "height": h, "pixelRatio": 3}
                })
            self.driver = webdriver.Chrome(options=opts)

        w, h = self.cfg.viewport
        if self.cfg.device_type == "desktop":
            self.driver.set_window_size(w, h)

    async def grab(self, task, timeout_ms: int) -> dict:
        await self._ensure()
        self.logger.info(f"[SE] get {task.url}")
        self.driver.set_page_load_timeout(timeout_ms / 1000)
        self.driver.get(task.url)
        if task.wait_selector:
            await self._wait_css(task.wait_selector, timeout_ms)
        data = {}
        for sel in task.selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                vals = []
                for el in elements:
                    txt = el.text.strip()
                    if txt:
                        vals.append(" ".join(txt.split()))
                data[sel] = vals
            except Exception as e:
                self.logger.warning(f"[SE] selector fail {sel}: {e}")
        return data

    async def _wait_css(self, selector: str, timeout_ms: int):
        end = asyncio.get_event_loop().time() + (timeout_ms / 1000)
        while asyncio.get_event_loop().time() < end:
            if self.driver.find_elements(By.CSS_SELECTOR, selector):
                return
            await asyncio.sleep(0.1)
        self.logger.warning(f"[SE] wait timeout {selector}")

    async def close(self):
        if self.driver:
            self.driver.quit()
