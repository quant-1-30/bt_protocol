#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
from decimal import Decimal
from typing import Any, Dict, Tuple

from sqlalchemy.inspection import inspect


class DictSerializableMixin:
    """Shared column-cached dictionary serialization for SQLAlchemy ORM models.

    Caches column attribute names on the class (`__columns__`) on first access
    to avoid repeated `inspect(self).mapper.column_attrs` reflection on hot
    serialization paths.
    """

    __columns__: Tuple[str, ...] = ()

    def to_dict(self, include_id: bool = False) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for c in self.__columns__ or self._refresh_columns():
            if not include_id and c == "id":
                continue

            value = getattr(self, c)
            if value is None:
                result[c] = None
            elif isinstance(value, datetime.datetime):
                if value.tzinfo is None:
                    value = value.replace(tzinfo=datetime.timezone.utc)
                result[c] = int(value.timestamp())
            elif isinstance(value, Decimal):
                result[c] = float(value)
            else:
                result[c] = value
        return result

    @classmethod
    def _refresh_columns(cls) -> Tuple[str, ...]:
        cols = tuple(c.key for c in inspect(cls).mapper.column_attrs)
        cls.__columns__ = cols
        return cols


__all__ = ["DictSerializableMixin"]
