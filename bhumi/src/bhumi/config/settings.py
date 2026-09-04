from __future__ import annotations

import os
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


def resolve_profile_with_reason() -> tuple[Profile, str]:
    """Auto-detection is the default; BHUMI_PROFILE is an explicit override
    that always wins (addon prompt §5). Printed by `task profile`/`doctor`
    so this is never a silent guess."""
    explicit = os.environ.get("BHUMI_PROFILE")
    if explicit:
        return Profile(explicit), f"explicit BHUMI_PROFILE={explicit}"
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            return Profile.WORKSTATION, f"workstation: CUDA device found ({name})"
    except ImportError:
        pass
    if os.environ.get("BHUMI_POSTGRES_URL"):
        return Profile.SUPABASE, "supabase: BHUMI_POSTGRES_URL configured, no CUDA device"
    return Profile.SQLITE, "sqlite: no CUDA device, no BHUMI_POSTGRES_URL (safe default)"


def get_settings() -> Settings:
    settings = Settings()
    if "BHUMI_PROFILE" not in os.environ:
        settings.profile, _ = resolve_profile_with_reason()
    return settings
