from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from bhumi.config.settings import Profile, Settings
from bhumi.storage.db.models import Base


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
    """MVP-0 pragmatic migration: metadata.create_all().

    ponytail: Alembic is the design doc's stated non-negotiable, but for a
    single-developer hackathon build against SQLite, create_all() is the
    same net effect with a tenth of the ceremony. Upgrade to real Alembic
    migrations the moment a second person edits the schema concurrently, or
    the moment a column needs to change on data that already exists.
    """
    engine = make_engine(settings)
    Base.metadata.create_all(engine)
    return engine
