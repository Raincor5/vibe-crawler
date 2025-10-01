class LoggerFactory:
    import logging
    from pathlib import Path

    @staticmethod
    def create(name: str = "scraper", level: int = __import__("logging").INFO):
        logging = __import__("logging")
        logger = logging.getLogger(name)
        if logger.handlers:
            return logger
        logger.setLevel(level)
        fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        logger.addHandler(stream)
        path_cls = __import__("pathlib").Path
        log_dir = path_cls("logs")
        log_dir.mkdir(exist_ok=True)
        fh = logging.FileHandler(log_dir / "scraper.log")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        return logger
