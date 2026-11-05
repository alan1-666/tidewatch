"""统一取数 SDK：研究、回测与报告共用的唯一取数口径。

K 线在 ClickHouse 内由 1m 聚合，返回 polars 长表（每行一个 (ts, symbol)）。官方数据可能整段缺失，
这里不补值：每行带上该周期实际包含的 1m 根数 bars，一根都没有的周期不输出，由使用方判断。
"""
from datetime import datetime, timedelta, timezone

import polars as pl

# 周期 → (ClickHouse 间隔表达式, 周期长度)。日线按 UTC 0 点切，ts 列本身是 UTC。
FREQS = {
    '1m': ('INTERVAL 1 MINUTE', timedelta(minutes=1)),
    '5m': ('INTERVAL 5 MINUTE', timedelta(minutes=5)),
    '15m': ('INTERVAL 15 MINUTE', timedelta(minutes=15)),
    '1h': ('INTERVAL 1 HOUR', timedelta(hours=1)),
    '4h': ('INTERVAL 4 HOUR', timedelta(hours=4)),
    '1d': ('INTERVAL 1 DAY', timedelta(days=1)),
}
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
# 固定输出类型：空结果与非空结果一致，按合约或分批取数后可以直接拼接。
BAR_SCHEMA = {'ts': pl.Datetime('ms', 'UTC'), 'symbol': pl.String, 'open': pl.Float64, 'high': pl.Float64,
              'low': pl.Float64, 'close': pl.Float64, 'volume': pl.Float64, 'quote_volume': pl.Float64,
              'trades': pl.Int64, 'taker_buy_volume': pl.Float64, 'taker_buy_quote_volume': pl.Float64,
              'bars': pl.Int64}
FUNDING_SCHEMA = {'ts': pl.Datetime('ms', 'UTC'), 'symbol': pl.String, 'rate': pl.Float64, 'interval_hours': pl.Int64}
BAR_COLUMNS = list(BAR_SCHEMA)
FUNDING_COLUMNS = list(FUNDING_SCHEMA)


def _check_times(start, end):
    for name, value in (('start', start), ('end', end)):
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError(f'{name} 必须是带时区的 datetime')
    if start >= end:
        raise ValueError('start 必须早于 end')


def check_range(freq, start, end):
    """校验周期与区间 [start, end)：必须是带时区的 datetime，且两端都对齐周期，避免首尾出现残缺周期。"""
    if freq not in FREQS:
        raise ValueError(f'不支持的周期 {freq!r}，可选 {list(FREQS)}')
    _check_times(start, end)
    step = FREQS[freq][1]
    for name, value in (('start', start), ('end', end)):
        if (value - EPOCH) % step:
            raise ValueError(f'{name}={value.isoformat()} 未对齐周期 {freq}')


def _frame(result, schema):
    data = dict(zip(schema, result.result_columns)) if result.result_rows else {}
    # clickhouse-connect 对 DateTime64('UTC') 返回不带时区的 datetime：先按无时区读入，再标为 UTC。
    frame = pl.DataFrame(data, schema={**schema, 'ts': pl.Datetime('ms')})
    return frame.with_columns(pl.col('ts').dt.replace_time_zone('UTC'))


def get_bars(client, symbols, freq, start, end):
    """[start, end) 内的 K 线，按 (symbol, ts) 排序。"""
    check_range(freq, start, end)
    if isinstance(symbols, str):
        raise TypeError('symbols 应为合约名列表，而不是单个字符串')
    interval = FREQS[freq][0]
    # FINAL：重复导入的同一分钟只计一次。开收取周期内最早、最晚那一分钟。
    sql = f'''
        SELECT toStartOfInterval(ts, {interval}) AS bucket, symbol,
               argMin(open, ts), max(high), min(low), argMax(close, ts),
               sum(volume), sum(quote_volume), sum(trades), sum(taker_buy_volume), sum(taker_buy_quote_volume),
               count() AS bars
        FROM klines_1m FINAL
        WHERE symbol IN {{symbols:Array(String)}} AND ts >= {{start:DateTime64(3, 'UTC')}} AND ts < {{end:DateTime64(3, 'UTC')}}
        GROUP BY symbol, bucket
        ORDER BY symbol, bucket'''
    result = client.query(sql, parameters={'symbols': list(symbols), 'start': start, 'end': end})
    return _frame(result, BAR_SCHEMA)


def get_funding(client, symbols, start, end):
    """[start, end) 内的资金费率结算，ts 为规整到秒的结算时刻。ts 是 MATERIALIZED 列，必须显式选取。"""
    _check_times(start, end)
    if isinstance(symbols, str):
        raise TypeError('symbols 应为合约名列表，而不是单个字符串')
    sql = '''
        SELECT ts, symbol, rate, interval_hours
        FROM funding_rate FINAL
        WHERE symbol IN {symbols:Array(String)} AND ts >= {start:DateTime64(3, 'UTC')} AND ts < {end:DateTime64(3, 'UTC')}
        ORDER BY symbol, ts'''
    result = client.query(sql, parameters={'symbols': list(symbols), 'start': start, 'end': end})
    return _frame(result, FUNDING_SCHEMA)
