import os
import random
from dataclasses import dataclass, field

@dataclass(frozen=True)
class UAProfile:
    user_agent: str
    device_type: str  # "desktop" or "mobile"
    viewports: tuple[tuple[int, int], ...]
    accept_languages: tuple[str, ...]
    timezones: tuple[str, ...]

UA_PROFILES: list[UAProfile] = [
    UAProfile(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        device_type="desktop",
        viewports=(
            (1920,1080),(1536,864),(1440,900),(1366,768),(1280,800),(2560,1440)
        ),
        accept_languages=("en-US,en;q=0.9","de-DE,de,en;q=0.8","fr-FR,fr,en;q=0.8"),
        timezones=("UTC","Europe/Berlin","America/New_York","Asia/Singapore")
    ),
    UAProfile(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        device_type="desktop",
        viewports=((1920,1080),(1728,1117),(1512,982),(1440,900),(1280,800)),
        accept_languages=("en-US,en;q=0.9","fr-FR,fr,en;q=0.8"),
        timezones=("UTC","Europe/Paris","America/New_York")
    ),
    UAProfile(
        user_agent="Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        device_type="desktop",
        viewports=((1920,1080),(1680,1050),(1600,900),(1366,768),(1440,900)),
        accept_languages=("en-US,en;q=0.9","de-DE,de,en;q=0.8"),
        timezones=("UTC","Europe/Berlin","America/Chicago")
    ),
    UAProfile(
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        device_type="mobile",
        viewports=((375,812),(390,844),(414,896)),
        accept_languages=("en-US,en;q=0.9",),
        timezones=("UTC","America/Los_Angeles","Europe/London")
    ),
]

@dataclass
class Config:
    tor_control_port: int = 9051
    tor_control_password: str | None = None
    tor_rotation_min_interval_s: int = 10
    tor_request_threshold: int = 5
    headless: bool = True
    timeout_ms: int = 15000
    storage_dir: str = "data"
    engine: str = "playwright"
    proxy_enabled: bool = False
    tor_socks_host: str = "127.0.0.1"
    tor_socks_port: int = 9050
    captcha_api_key: str | None = None
    randomize: bool = True
    user_agent: str = ""
    accept_language: str = ""
    locale: str = ""
    timezone: str = ""
    viewport: tuple[int, int] = field(default_factory=lambda: (1920, 1080))
    device_type: str = "desktop"

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls(
            headless=os.getenv("SCRAPER_HEADLESS", "1") == "1",
            timeout_ms=int(os.getenv("SCRAPER_TIMEOUT_MS", "15000")),
            storage_dir=os.getenv("SCRAPER_STORAGE", "data"),
            engine=os.getenv("SCRAPER_ENGINE", "playwright"),
            proxy_enabled=os.getenv("SCRAPER_PROXY", "0") == "1",
            tor_socks_host=os.getenv("TOR_SOCKS_HOST", "127.0.0.1"),
            tor_socks_port=int(os.getenv("TOR_SOCKS_PORT", "9050")),
            captcha_api_key=os.getenv("CAPTCHA_API_KEY"),
            randomize=os.getenv("SCRAPER_RANDOMIZE", "1") == "1",
            tor_control_port=int(os.getenv("TOR_CONTROL_PORT", "9051")),
            tor_control_password=os.getenv("TOR_CONTROL_PASSWORD"),
            tor_rotation_min_interval_s=int(os.getenv("TOR_ROTATE_MIN_S", "10")),
            tor_request_threshold=int(os.getenv("TOR_ROTATE_REQ_THRESHOLD", "5")),

        )
        if cfg.randomize:
            profile = random.choice(UA_PROFILES)
            cfg.user_agent = profile.user_agent
            cfg.device_type = profile.device_type
            cfg.accept_language = random.choice(profile.accept_languages)
            cfg.locale = cfg.accept_language.split(",")[0]
            cfg.timezone = random.choice(profile.timezones)
            cfg.viewport = random.choice(profile.viewports)
        else:
            # Deterministic fallback: first profile
            profile = UA_PROFILES[0]
            cfg.user_agent = os.getenv("SCRAPER_UA", profile.user_agent)
            cfg.device_type = profile.device_type
            cfg.accept_language = profile.accept_languages[0]
            cfg.locale = cfg.accept_language.split(",")[0]
            cfg.timezone = profile.timezones[0]
            cfg.viewport = profile.viewports[0]
        return cfg
