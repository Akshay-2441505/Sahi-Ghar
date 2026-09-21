import gzip
import hashlib
from pathlib import Path
from typing import Protocol


class RawStore(Protocol):
    def put(self, data: bytes) -> str:
        """Store bytes, return the key (content-addressed, so re-putting is a no-op)."""

    def get(self, key: str) -> bytes: ...


class LocalRawStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.gz"

    def put(self, data: bytes) -> str:
        key = hashlib.sha256(data).hexdigest()
        path = self._path(key)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(data))
        return key

    def get(self, key: str) -> bytes:
        return gzip.decompress(self._path(key).read_bytes())
