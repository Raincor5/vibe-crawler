class DataCleaner:
    def normalize(self, raw: dict) -> dict:
        out = {}
        for k, vals in raw.items():
            if not isinstance(vals, list):
                out[k] = vals
                continue
            # Detect record dicts with text/html
            if vals and isinstance(vals[0], dict) and {'text', 'html'} <= set(vals[0].keys()):
                seen = set()
                cleaned_records = []
                for rec in vals:
                    text = rec.get('text', '')
                    html = rec.get('html', '')
                    norm_text = " ".join(text.split()) if isinstance(text, str) else ''
                    key = (norm_text, html)
                    if key in seen:
                        continue
                    seen.add(key)
                    cleaned_records.append({
                        'text': norm_text,
                        'html': html
                    })
                out[k] = cleaned_records
            else:
                # Assume list of strings
                seen = set()
                cleaned = []
                for v in vals:
                    if not isinstance(v, str):
                        continue
                    nv = " ".join(v.split())
                    if nv and nv not in seen:
                        seen.add(nv)
                        cleaned.append(nv)
                out[k] = cleaned
        return out
