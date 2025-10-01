class TorProxyManager:
    import socket

    def __init__(self, host: str, port: int, logger):
        self.host = host
        self.port = port
        self.logger = logger

    def is_available(self) -> bool:
        socket = __import__("socket")
        try:
            with socket.create_connection((self.host, self.port), timeout=2):
                self.logger.info("Tor SOCKS proxy reachable.")
                return True
        except OSError:
            self.logger.warning("Tor SOCKS proxy not reachable.")
            return False

    def playwright_proxy_settings(self) -> dict | None:
        if self.is_available():
            return {"server": f"socks5://{self.host}:{self.port}"}
        return None
