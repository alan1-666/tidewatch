from datetime import datetime, timedelta, timezone

import pytest

from tidewatch import store

pytestmark = pytest.mark.integration

KLINE_COLUMNS = ['symbol', 'ts', 'open', 'high', 'low', 'close', 'volume', 'quote_volume', 'trades',
                 'taker_buy_volume', 'taker_buy_quote_volume', 'ingested_at']
T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def kline(ts, close, ingested_at):
    return ['BTCUSDT', ts, close, close, close, close, 1.0, close, 1, 0.5, close / 2, ingested_at]


def test_schema_is_idempotent_and_matches_design(client):
    store.ensure_schema(client)
    store.ensure_schema(client)
    rows = client.query(
        "SELECT name, engine_full, partition_key, sorting_key FROM system.tables "
        "WHERE database = currentDatabase() ORDER BY name").result_rows
    tables = {r[0]: r[1:] for r in rows}
    assert sorted(tables) == ['funding_rate', 'klines_1m', 'symbols']
    for name in ('funding_rate', 'klines_1m'):
        engine, partition, sorting = tables[name]
        assert engine.startswith('ReplacingMergeTree(ingested_at)'), name
        assert partition == 'toYYYYMM(ts)' and sorting == 'symbol, ts', name
    engine, partition, sorting = tables['symbols']
    assert engine.startswith('ReplacingMergeTree(refreshed_at)') and partition == '' and sorting == 'symbol'
    types = dict(client.query(
        "SELECT name, type FROM system.columns WHERE database = currentDatabase() AND table = 'klines_1m'"
    ).result_rows)
    assert types['ts'] == "DateTime64(3, 'UTC')" and types['trades'] == 'UInt32'


def test_duplicate_writes_keep_highest_ingested_at_not_last_insert(client):
    store.ensure_schema(client)
    client.command('SYSTEM STOP MERGES klines_1m')  # 保证断言时尚未后台合并
    older, newer = T0 + timedelta(hours=1), T0 + timedelta(hours=2)
    # 先写版本较新的，再写较旧的：若引擎不看 ingested_at、只留最后插入的行，这里会失败。
    client.insert('klines_1m', [kline(T0, 100.5, newer), kline(T0 + timedelta(minutes=1), 101.0, newer)],
                  column_names=KLINE_COLUMNS)
    client.insert('klines_1m', [kline(T0, 100.0, older)], column_names=KLINE_COLUMNS)
    assert client.command('SELECT count() FROM klines_1m') == 3
    rows = client.query('SELECT ts, close FROM klines_1m FINAL ORDER BY ts').result_rows
    assert [(r[0].replace(tzinfo=timezone.utc), r[1]) for r in rows] == \
        [(T0, 100.5), (T0 + timedelta(minutes=1), 101.0)]


def ms(value):
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def test_kline_millisecond_utc_timestamp_round_trips(client):
    store.ensure_schema(client)
    client.insert('klines_1m', [kline(ms(1704067200123), 1.0, T0)], column_names=KLINE_COLUMNS)
    assert client.command('SELECT toUnixTimestamp64Milli(ts) FROM klines_1m') == 1704067200123


def test_funding_ts_is_calc_time_rounded_to_second_and_dedups_jitter(client):
    # 官方 calc_time 常比整点晚几毫秒；同一次结算的不同抖动必须落到同一个 ts 并去重。
    store.ensure_schema(client)
    hour = 1704096000000  # 2024-01-01 08:00:00 UTC
    cols = ['symbol', 'calc_time', 'interval_hours', 'rate', 'ingested_at']
    client.insert('funding_rate', [['BTCUSDT', ms(hour + 1), 8, 0.0001, T0]], column_names=cols)
    client.insert('funding_rate', [['BTCUSDT', ms(hour + 3), 8, 0.0002, T0 + timedelta(hours=1)],
                                   ['BTCUSDT', ms(hour + 8 * 3600_000 - 2), 8, 0.0003, T0]], column_names=cols)
    rows = client.query('SELECT toUnixTimestamp64Milli(ts), toUnixTimestamp64Milli(calc_time), rate '
                        'FROM funding_rate FINAL ORDER BY ts').result_rows
    assert rows == [(hour, hour + 3, 0.0002), (hour + 8 * 3600_000, hour + 8 * 3600_000 - 2, 0.0003)]
