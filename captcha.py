class CaptchaSolver:
    def __init__(self, api_key: str | None, logger):
        self.api_key = api_key
        self.logger = logger

    async def solve(self, meta: dict) -> str:
        if not self.api_key:
            self.logger.info("Captcha solver disabled (no key).")
            return ""
        self.logger.info("Captcha solve placeholder invoked.")
        return "DUMMY_SOLUTION"
