from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from bhumi.config.settings import Profile, Settings

REPO_ROOT = Path(__file__).resolve().parents[4]


def make_engine(settings: Settings) -> Engine:
    if settings.profile == Profile.SQLITE:
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(f"sqlite:///{settings.sqlite_path}")
    if not settings.postgres_url:
        raise RuntimeError(
            f"profile {settings.profile} requires BHUMI_POSTGRES_URL to be set"
        )
    return create_engine(settings.postgres_url.get_secret_value())


def migrate(settings: Settings) -> Engine:
    """Apply the Alembic migration chain (wired 2026-09-05 — see
    PROVENANCE.md for why create_all() was the pragmatic MVP-0/1 choice and
    what triggered the switch). alembic/env.py resolves its own DB URL from
    this same Settings object, so `task migrate` always targets whatever
    BHUMI_PROFILE currently points at."""
    engine = make_engine(settings)
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    command.upgrade(cfg, "head")
    return engine
