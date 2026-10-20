#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""DuckDB SQL templates for reading parquet market data.

All templates share the same FROM/WHERE fragment (parquet scan + sid UNNEST
filter + UTC datetime range), so it is factored into ``_BASE_FILTER``. Keeping a
single source of truth avoids the three copies drifting apart when the parquet
layout or timezone handling changes.

Bind-parameter order for the shared fragment is:
    1. parquet path(s)
    2. sid list (UNNEST, ``List[str]``)
    3. start datetime (UTC string)
    4. end   datetime (UTC string)
"""

_BASE_FILTER = """\
    FROM read_parquet(?, hive_partitioning=true, hive_types={'sid': 'VARCHAR'})
    WHERE sid IN (SELECT * FROM UNNEST(?))
      AND datetime BETWEEN (?::TIMESTAMPTZ AT TIME ZONE 'UTC') AND (?::TIMESTAMPTZ AT TIME ZONE 'UTC')
"""

_VALID_CLOSE_FILTER = "AND close IS NOT NULL AND close > 0"

# Cast `datetime::TIMESTAMP` first so both naive UTC `TIMESTAMP` (2000-2025)
# and `TIMESTAMPTZ` (2026+) shift +8h to Asia/Shanghai trading day consistently.
_DAY_COLUMN = (
    "strftime((datetime::TIMESTAMP AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Shanghai'), '%Y%m%d')::INTEGER as day"
)

DAILY_AGG_SELECT = f"""
    CAST(sid AS VARCHAR) AS sid,
    {_DAY_COLUMN},
    CAST(round(arg_min(open, datetime)) AS BIGINT) AS open,
    CAST(round(max(high)) AS BIGINT) AS high,
    CAST(round(min(low)) AS BIGINT) AS low,
    CAST(round(arg_max(close, datetime)) AS BIGINT) AS close,
    CAST(round(sum(volume)) AS DECIMAL(38, 0)) AS volume,
    CAST(round(sum(amount)) AS DECIMAL(38, 0)) AS amount
"""

TICK_TEMPLATE = f"""
    SELECT
        CAST(sid AS VARCHAR)::BLOB as sid,
        tick, open, high, low, close, volume, amount
    {_BASE_FILTER}
    ORDER BY sid, datetime ASC
"""

CLOSE_TEMPLATE = f"""
    SELECT
        CAST(sid AS VARCHAR)::BLOB as sid,
        {_DAY_COLUMN},
        arg_max(close, datetime) as close
    {_BASE_FILTER}
      {_VALID_CLOSE_FILTER}
    GROUP BY 1, 2
    ORDER BY 1, 2 ASC
"""

DAILY_TEMPLATE = f"""
    SELECT
        CAST(sid AS VARCHAR)::BLOB as sid,
        {_DAY_COLUMN},

        -- K线日度聚合逻辑
        arg_min(open, datetime) as open,
        max(high) as high,
        min(low) as low,
        arg_max(close, datetime) as close,
        sum(volume) as volume,
        sum(amount) as amount

    {_BASE_FILTER}
      {_VALID_CLOSE_FILTER}
    GROUP BY 1, 2
    ORDER BY sid, day ASC
"""

_PREAGG_DAY_FILTER = """\
    FROM read_parquet(?, hive_partitioning=false)
    WHERE sid IN (SELECT * FROM UNNEST(?))
      AND day BETWEEN strftime((?::TIMESTAMPTZ AT TIME ZONE 'Asia/Shanghai'), '%Y%m%d')::INTEGER
                  AND strftime((?::TIMESTAMPTZ AT TIME ZONE 'Asia/Shanghai'), '%Y%m%d')::INTEGER
"""

DAILY_FETCH_TEMPLATE = f"""
    SELECT
        CAST(sid AS VARCHAR)::BLOB as sid,
        day, open, high, low, close, volume, amount
    {_PREAGG_DAY_FILTER}
    ORDER BY sid, day ASC
"""

CLOSE_FETCH_TEMPLATE = f"""
    SELECT
        CAST(sid AS VARCHAR)::BLOB as sid,
        day, close
    {_PREAGG_DAY_FILTER}
    ORDER BY 1, 2 ASC
"""

__all__ = [
    "TICK_TEMPLATE",
    "CLOSE_TEMPLATE",
    "DAILY_TEMPLATE",
    "DAILY_FETCH_TEMPLATE",
    "CLOSE_FETCH_TEMPLATE",
    "DAILY_AGG_SELECT",
]
