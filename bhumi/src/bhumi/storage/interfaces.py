"""Storage portability layer. Business logic talks to these Protocols only —
never to sqlite3/psycopg/etc directly. See CLAUDE.md rule 1 and rule 6.

Vector/Text/Graph are defined now (Phase 5 needs them) but not implemented
until Phase 5 — MVP-1 doesn't need retrieval. Implementing them now would be
speculative; the interface costs nothing, the implementation would.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol


class BlobStore(Protocol):
    def put(self, content: bytes, sha256: str) -> str: ...
    def get(self, ref: str) -> bytes: ...
    def exists(self, sha256: str) -> bool: ...
    def local_path(self, ref: str) -> Path | None: ...


class VectorIndex(Protocol):
    dim: int

    def upsert(self, ids: list[str], vectors: list[list[float]]) -> None: ...
    def knn(self, vector: list[float], k: int) -> list[tuple[str, float]]: ...
    def count(self) -> int: ...


class TextIndex(Protocol):
    def index(self, doc_id: str, text: str, meta: dict) -> None: ...
    def search(self, query: str, k: int) -> list[tuple[str, float]]: ...


class GraphStore(Protocol):
    def upsert_node(self, node_id: str, label: str, props: dict) -> None: ...
    def upsert_edge(self, src: str, dst: str, rel: str, props: dict) -> None: ...
    def neighbours(
        self, node_id: str, rel: str | None = None,
        direction: Literal["out", "in", "both"] = "both",
    ) -> list[dict]: ...
