class DataCleaner:
    def normalize(self, raw: dict) -> dict:
        out = {}
        for k, vals in raw.items():
            seen = set()
            cleaned = []
            for v in vals:
                nv = " ".join(v.split())
                if nv and nv not in seen:
                    seen.add(nv)
                    cleaned.append(nv)
            out[k] = cleaned
        return out
