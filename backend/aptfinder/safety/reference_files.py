import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

from aptfinder.http import PoliteClient


@dataclass(frozen=True)
class ReferenceFile:
    url: str
    path: Path
    fetched_at: datetime
    sha256: str
    from_cache: bool

    def read_text(self) -> str:
        raw = self.path.read_bytes()
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return raw.decode("latin-1")


def fetch_reference_file(client: PoliteClient, url: str, dest_dir: Path, max_age: timedelta) -> ReferenceFile:
    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    body_path = dest_dir / name
    meta_path = dest_dir / f"{name}.meta.json"
    if meta_path.exists() and body_path.exists():
        meta = json.loads(meta_path.read_text())
        fetched_at = datetime.fromisoformat(meta["fetched_at"])
        if meta["url"] == url and datetime.now(UTC) - fetched_at <= max_age:
            return ReferenceFile(url, body_path, fetched_at, meta["sha256"], from_cache=True)

    content = client.get_bytes(url)
    fetched_at = datetime.now(UTC)
    sha = hashlib.sha256(content).hexdigest()
    dest_dir.mkdir(parents=True, exist_ok=True)
    partial = body_path.with_name(f"{name}.partial")
    partial.write_bytes(content)
    partial.replace(body_path)
    meta_path.write_text(json.dumps({"url": url, "fetched_at": fetched_at.isoformat(), "sha256": sha}))
    return ReferenceFile(url, body_path, fetched_at, sha, from_cache=False)
