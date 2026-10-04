import hashlib


def stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha1("\x1f".join(str(p) for p in parts).encode()).hexdigest()[:20]
    return f"{prefix}_{digest}"
