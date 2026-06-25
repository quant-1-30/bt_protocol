TICK_TEMPLATE = """
    SELECT 
        CAST(sid AS VARCHAR)::BLOB as sid, 
        tick, open, high, low, close, volume, amount
    FROM read_parquet(?, hive_partitioning=true, hive_types={'sid': 'VARCHAR'})
    WHERE sid IN (SELECT * FROM UNNEST(?))
      -- ? DuckDB TIMESTAMPTZ 
      -- AT TIME ZONE 'UTC'
      AND datetime BETWEEN (?::TIMESTAMPTZ AT TIME ZONE 'UTC') AND (?::TIMESTAMPTZ AT TIME ZONE 'UTC')
    ORDER BY sid, datetime ASC
"""

CLOSE_TEMPLATE = """
    SELECT 
        CAST(sid AS VARCHAR)::BLOB as sid,
        -- strftime(datetime + INTERVAL 8 HOUR, '%Y%m%d')::INTEGER as day,
        -- UTC -> TIMESTAMPTZ -> Shanghai Naive TIMESTAMP -> String
        strftime(
            (datetime AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Shanghai'), 
            '%Y%m%d'
        )::INTEGER as day,
        arg_max(close, datetime) as close
    FROM read_parquet(?, hive_partitioning=true, hive_types={'sid': 'VARCHAR'})
    WHERE sid IN (SELECT * FROM UNNEST(?))
      AND datetime BETWEEN (?::TIMESTAMPTZ AT TIME ZONE 'UTC') AND (?::TIMESTAMPTZ AT TIME ZONE 'UTC')
      AND close IS NOT NULL 
      AND close > 0
    GROUP BY 1, 2
    ORDER BY 1, 2 ASC
"""

DAILY_TEMPLATE = """
    SELECT 
        CAST(sid AS VARCHAR)::BLOB as sid,
        -- strftime(datetime + INTERVAL 8 HOUR, '%Y%m%d')::INTEGER as day,
        -- UTC -> TIMESTAMPTZ -> Shanghai Naive TIMESTAMP -> String -> Integer
        strftime(
            (datetime AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Shanghai'), 
            '%Y%m%d'
        )::INTEGER as day,
        
        -- K线日度聚合逻辑
        arg_min(open, datetime) as open,       
        max(high) as high,                     
        min(low) as low,
        arg_max(close, datetime) as close,     
        sum(volume) as volume,                 
        sum(amount) as amount                  
        
    FROM read_parquet(?, hive_partitioning=true, hive_types={'sid': 'VARCHAR'})
    WHERE sid IN (SELECT * FROM UNNEST(?))
      AND datetime BETWEEN (?::TIMESTAMPTZ AT TIME ZONE 'UTC') AND (?::TIMESTAMPTZ AT TIME ZONE 'UTC')
      AND close IS NOT NULL 
      AND close > 0
    GROUP BY 1, 2
    ORDER BY sid, day ASC
"""
