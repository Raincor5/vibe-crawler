class Fingerprint:
    def __init__(self, config, logger):
        self.cfg = config
        self.logger = logger

    def summary(self) -> dict:
        fp = {
            "user_agent": self.cfg.user_agent,
            "device_type": self.cfg.device_type,
            "accept_language": self.cfg.accept_language,
            "locale": self.cfg.locale,
            "timezone": self.cfg.timezone,
            "viewport": self.cfg.viewport,
            "engine": self.cfg.engine,
            "headless": self.cfg.headless,
        }
        self.logger.info(f"Fingerprint: {fp}")
        return fp
