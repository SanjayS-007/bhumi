"""Decimal("3.42") must round-trip exactly through the DB — SQLite has no
native NUMERIC, so a naive float column would silently corrupt a coal
production figure."""
from decimal import Decimal

from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from bhumi.storage.db.types import DecimalString


def test_decimal_round_trips_exactly(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    metadata = MetaData()
    t = Table("t", metadata, Column("id", Integer, primary_key=True), Column("value", DecimalString))
    metadata.create_all(engine)

    with Session(engine) as session:
        session.execute(t.insert().values(id=1, value=Decimal("3.42")))
        session.commit()
        row = session.execute(t.select()).mappings().one()
        assert row["value"] == Decimal("3.42")
        assert str(row["value"]) == "3.42"
