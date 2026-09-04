from __future__ import annotations

from pathlib import Path


class LocalBlobStore:
    """Content-addressed filesystem blob store. data/vault/<sha256[:2]>/<sha256><ext>."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, sha256: str, suffix: str = ".pdf") -> Path:
        return self.root / sha256[:2] / f"{sha256}{suffix}"

    def put(self, content: bytes, sha256: str, suffix: str = ".pdf") -> str:
        p = self._path(sha256, suffix)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_bytes(content)
        return str(p.relative_to(self.root.parent))

    def get(self, ref: str) -> bytes:
        return (self.root.parent / ref).read_bytes()

    def exists(self, sha256: str, suffix: str = ".pdf") -> bool:
        return self._path(sha256, suffix).exists()

    def local_path(self, ref: str) -> Path | None:
        p = self.root.parent / ref
        return p if p.exists() else None
