from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Profile(str, Enum):
    SQLITE = "sqlite"
    SUPABASE = "supabase"
    WORKSTATION = "workstation"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BHUMI_", env_file=".env", extra="ignore")

    profile: Profile = Profile.SQLITE
    offline: bool = False
    data_dir: Path = Path("data")

    sqlite_path: Path = Path("data/bhumi.db")
    postgres_url: Optional[SecretStr] = None

    vector_backend: Literal["auto", "sqlite_vec", "pgvector"] = "auto"
    text_backend: Literal["auto", "fts5", "tsvector"] = "auto"
    graph_backend: Literal["auto", "sql", "age", "neo4j"] = "auto"
    blob_backend: Literal["auto", "local", "supabase"] = "auto"

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    enable_tier2: bool = True
    enable_tier3: bool = False
    ocr_confidence_floor: float = 0.80

    max_ram_gb: Optional[float] = None
    max_vram_gb: Optional[float] = None


def get_settings() -> Settings:
    return Settings()
