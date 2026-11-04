"""ClickHouse 表结构。只负责建表；连接由调用方用 clickhouse_connect 创建并传入。

两张表都用 ReplacingMergeTree(ingested_at)：同一 (symbol, ts) 重复导入时保留 ingested_at 最大的一行，
版本相同（同一批或同一毫秒）时保留最后插入的一行。ingested_at 取服务端时钟，时钟回拨会让较晚的导入被丢弃。
去重发生在后台合并时，读取需要精确结果的地方要加 FINAL。
"""

KLINES_1M = """
CREATE TABLE IF NOT EXISTS klines_1m (
    symbol LowCardinality(String),
    ts DateTime64(3, 'UTC') COMMENT 'bar 开盘时刻',
    open Float64,
    high Float64,
    low Float64,
    close Float64,
    volume Float64,
    quote_volume Float64,
    trades UInt32,
    taker_buy_volume Float64,
    taker_buy_quote_volume Float64,
    ingested_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
"""

FUNDING_RATE = """
CREATE TABLE IF NOT EXISTS funding_rate (
    symbol LowCardinality(String),
    calc_time DateTime64(3, 'UTC') COMMENT '官方原始结算时间，常比整点晚 1~3ms',
    -- 去重键与计费边界都用规整后的时刻；由库计算，接入层只写 calc_time，无法写错。
    ts DateTime64(3, 'UTC') MATERIALIZED toStartOfSecond(calc_time + toIntervalMillisecond(500))
        COMMENT '结算时刻：calc_time 四舍五入到秒',
    interval_hours UInt8,
    rate Float64,
    ingested_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
"""

SYMBOLS = """
CREATE TABLE IF NOT EXISTS symbols (
    symbol String,
    quote LowCardinality(String) COMMENT '计价币；无法识别时为空串',
    contract LowCardinality(String) COMMENT 'perpetual 或 delivery',
    first_month Date COMMENT '首个有月度 1m K 线文件的月份（当月 1 日）',
    last_month Date COMMENT '最后一个有月度 1m K 线文件的月份',
    delisted UInt8 COMMENT '末月早于全体最新已发布月份',
    refreshed_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(refreshed_at)
ORDER BY symbol
"""

SCHEMA = (KLINES_1M, FUNDING_RATE, SYMBOLS)


def ensure_schema(client):
    """在 client 当前数据库中建表；已存在则跳过，可重复执行。"""
    for ddl in SCHEMA:
        client.command(ddl)
