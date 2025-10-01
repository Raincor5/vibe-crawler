class DataStorage:
    import json
    from pathlib import Path
    from datetime import datetime

    def __init__(self, base_dir: str, logger):
        path_cls = __import__("pathlib").Path
        self.base = path_cls(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.logger = logger

    def save_json(self, payload: dict, stem: str):
        json = __import__("json")
        dt = __import__("datetime").datetime
        ts = dt.utcnow().strftime("%Y%m%dT%H%M%SZ")
        path = self.base / f"{stem}_{ts}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Saved: {path}")
        return path
