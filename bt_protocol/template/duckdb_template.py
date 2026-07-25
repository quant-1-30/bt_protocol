#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""DuckDB SQL templates for reading parquet market data.

All templates share the same FROM/WHERE fragment (parquet scan + sid UNNEST
filter + UTC datetime range), so it is factored into ``_BASE_FILTER``. Keeping a
single source of truth avoids the three copies drifting apart when the parquet
layout or timezone handling changes.

Bind-parameter order for the shared fragment is:
    1. parquet path(s)
    2. sid list (UNNEST)
    3. start datetime (UTC string)
    4. end   datetime (UTC string)
"""

# Shared FROM + WHERE clause. Callers embed this via f-string/str.format and
# then append any extra predicates (e.g. close > 0), GROUP BY, ORDER BY.
_BASE_FILTER = """\
    FROM read_parquet(?, hive_partitioning=true, hive_types={'sid': 'VARCHAR'})
    WHERE sid IN (SELECT * FROM UNNEST(?))
      AND datetime BETWEEN (?::TIMESTAMPTZ AT TIME ZONE 'UTC') AND (?::TIMESTAMPTZ AT TIME ZONE 'UTC')
"""

# Shanghai-trading-day column expression used by both CLOSE and DAILY templates.
# UTC -> TIMESTAMPTZ -> Asia/Shanghai naive TIMESTAMP -> YYYYMMDD integer.
_DAY_COLUMN = (
    "strftime((datetime AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Shanghai'), '%Y%m%d')::INTEGER as day"
)

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
      AND close IS NOT NULL
      AND close > 0
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
      AND close IS NOT NULL
      AND close > 0
    GROUP BY 1, 2
    ORDER BY sid, day ASC
"""

__all__ = ["TICK_TEMPLATE", "CLOSE_TEMPLATE", "DAILY_TEMPLATE"]