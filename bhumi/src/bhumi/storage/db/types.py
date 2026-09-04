from __future__ import annotations

from decimal import Decimal

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


class DecimalString(TypeDecorator):
    """Stores Decimal as exact-text so SQLite (no native NUMERIC) never
    silently corrupts a coal production figure through float rounding.
    Round-trip-tested in tests/test_provenance_invariant.py.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(Decimal(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Decimal(value)
