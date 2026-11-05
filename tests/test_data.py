from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from tidewatch import data, store

UTC = timezone.utc
D0 = datetime(2024, 1, 2, tzinfo=UTC)
KLINE_COLUMNS = ['symbol', 'ts', 'open', 'high', 'low', 'close', 'volume', 'quote_volume', 'trades',
                 'taker_buy_volume', 'taker_buy_quote_volume', 'ingested_at']


def minute(i, price=None, ingested=D0, symbol='AUSDT'):
    """第 i 分钟（相对 D0）的一根 1m。价格与各类量都不单调、彼此不同，
    这样"首末分钟"与"极值"、"求和"与"计数"、各列之间错位都能被测试区分。"""
    p = float(price if price is not None else 100 + (i * 37) % 61)
    vol = 1.0 + (i * 5) % 7
    return [symbol, D0 + timedelta(minutes=i), p, p + 3 + i % 4, p - 2 - i % 3, p + (i * 13) % 5 - 2,
            vol, p * vol, i % 5 + 1, vol / 3, p * vol / 4, ingested]


def reference(rows, step):
    """用纯 Python 独立重算期望结果：按 (symbol, ts) 保留 ingested_at 最新的一行，再按周期聚合。"""
    latest = {}
    for r in rows:
        key = (r[0], r[1])
        if key not in latest or r[11] >= latest[key][11]:
            latest[key] = r
    buckets = {}
    for r in sorted(latest.values(), key=lambda r: (r[0], r[1])):
        start = D0 + ((r[1] - D0) // step) * step
        buckets.setdefault((r[0], start), []).append(r)
    out = []
    for (symbol, start), rs in sorted(buckets.items()):
        out.append((start, symbol, rs[0][2], max(r[3] for r in rs), min(r[4] for r in rs), rs[-1][5],
                    sum(r[6] for r in rs), sum(r[7] for r in rs), sum(r[8] for r in rs),
                    sum(r[9] for r in rs), sum(r[10] for r in rs), len(rs)))
    return out


def assert_rows(actual, expected):
    """ts 与 symbol 精确相等，数值列按浮点近似比较（求和顺序不同可能有末位误差）。"""
    assert len(actual) == len(expected)
    for got, want in zip(actual, expected):
        assert got[:2] == want[:2] and list(got[2:]) == pytest.approx(list(want[2:]))


@pytest.mark.parametrize('freq, start, end', [
    ('2h', D0, D0 + timedelta(hours=2)),                      # 不支持的周期
    ('1h', D0 + timedelta(minutes=30), D0 + timedelta(hours=2)),  # start 未对齐
    ('1d', D0, D0 + timedelta(hours=12)),                     # end 未对齐
    ('1h', D0.replace(tzinfo=None), D0 + timedelta(hours=1)),  # 无时区
    ('1h', D0, D0),                                           # 空区间
])
def test_check_range_rejects_bad_input(freq, start, end):
    with pytest.raises(ValueError):
        data.check_range(freq, start, end)


def test_check_range_accepts_aligned_utc_and_other_timezones():
    data.check_range('4h', D0 + timedelta(hours=4), D0 + timedelta(days=1))
    tokyo = timezone(timedelta(hours=9))
    data.check_range('1d', datetime(2024, 1, 2, 9, tzinfo=tokyo), datetime(2024, 1, 3, 9, tzinfo=tokyo))


@pytest.fixture
def seeded(client):
    store.ensure_schema(client)
    # 00:00–01:59 共 120 分钟，缺 01:10–01:19；02:00 起整小时无数据。
    rows = [minute(i) for i in range(120) if not 70 <= i < 80]
    # 前一天 23:59 一根，用来检查日线按 UTC 0 点切分。
    rows.append(minute(-1, price=50))
    client.insert('klines_1m', rows, column_names=KLINE_COLUMNS)
    # 00:00 重复导入一次（版本更新、价格不同），FINAL 下只计一根且取新值。
    newer = minute(0, price=130, ingested=D0 + timedelta(hours=1))
    client.insert('klines_1m', [newer], column_names=KLINE_COLUMNS)
    client.seeded_rows = rows + [newer]
    return client


@pytest.mark.integration
def test_hourly_aggregation_reports_gap_and_never_fills(seeded):
    df = data.get_bars(seeded, ['AUSDT'], '1h', D0, D0 + timedelta(hours=3))
    assert df.columns == data.BAR_COLUMNS
    assert df['ts'].to_list() == [D0, D0 + timedelta(hours=1)]  # 02:00 无数据，不输出
    assert df['bars'].to_list() == [60, 50]  # 第二个小时缺 10 分钟，如实报告
    in_range = [r for r in seeded.seeded_rows if D0 <= r[1] < D0 + timedelta(hours=3)]
    assert_rows(df.rows(), reference(in_range, timedelta(hours=1)))
    # 数据非单调：开盘不是最小值、收盘不是最大值，确保测的是"首末分钟"而不是极值。
    first = df.row(0, named=True)
    assert first['open'] == 130.0 and first['open'] != first['low'] and first['close'] != first['high']


@pytest.mark.integration
@pytest.mark.parametrize('freq, step', [('5m', timedelta(minutes=5)), ('15m', timedelta(minutes=15))])
def test_finer_frequencies_match_reference(seeded, freq, step):
    df = data.get_bars(seeded, ['AUSDT'], freq, D0, D0 + timedelta(hours=2))
    in_range = [r for r in seeded.seeded_rows if D0 <= r[1] < D0 + timedelta(hours=2)]
    assert_rows(df.rows(), reference(in_range, step))


@pytest.mark.integration
def test_daily_bars_split_at_utc_midnight(seeded):
    df = data.get_bars(seeded, ['AUSDT'], '1d', D0 - timedelta(days=1), D0 + timedelta(days=1))
    assert df.select('ts', 'bars').rows() == [(D0 - timedelta(days=1), 1), (D0, 110)]


@pytest.mark.integration
def test_range_is_half_open_and_other_symbols_excluded(seeded):
    seeded.insert('klines_1m', [minute(2, symbol='BUSDT')], column_names=KLINE_COLUMNS)
    df = data.get_bars(seeded, ['AUSDT'], '1m', D0, D0 + timedelta(minutes=5))
    assert df['ts'].to_list() == [D0 + timedelta(minutes=i) for i in range(5)]
    assert set(df['symbol']) == {'AUSDT'} and df['bars'].to_list() == [1] * 5
    both = data.get_bars(seeded, ['AUSDT', 'BUSDT'], '5m', D0, D0 + timedelta(minutes=5))
    assert both.select('symbol', 'bars').rows() == [('AUSDT', 5), ('BUSDT', 1)]


@pytest.mark.integration
def test_empty_result_keeps_schema(seeded):
    df = data.get_bars(seeded, ['NOPEUSDT'], '1h', D0, D0 + timedelta(hours=1))
    assert df.height == 0 and dict(df.schema) == data.BAR_SCHEMA
    full = data.get_bars(seeded, ['AUSDT'], '1h', D0, D0 + timedelta(hours=1))
    assert dict(full.schema) == data.BAR_SCHEMA
    assert pl.concat([full, df]).height == full.height  # 空表与非空表可直接拼接
    with pytest.raises(TypeError):
        data.get_bars(seeded, 'AUSDT', '1h', D0, D0 + timedelta(hours=1))


@pytest.mark.integration
def test_funding_returns_rounded_ts_in_utc(client):
    store.ensure_schema(client)
    hour = D0 + timedelta(hours=8)
    client.insert('funding_rate', [['AUSDT', hour + timedelta(milliseconds=3), 8, 0.0001],
                                   ['AUSDT', D0 + timedelta(days=1), 8, 0.0002]],
                  column_names=['symbol', 'calc_time', 'interval_hours', 'rate'])
    df = data.get_funding(client, ['AUSDT'], D0, D0 + timedelta(days=1))
    assert df.columns == data.FUNDING_COLUMNS
    assert df.rows() == [(hour, 'AUSDT', 0.0001, 8)]  # 毫秒抖动已规整；end 不含
    assert dict(df.schema) == data.FUNDING_SCHEMA
    empty = data.get_funding(client, ['NOPEUSDT'], D0, D0 + timedelta(days=1))
    assert empty.height == 0 and dict(empty.schema) == data.FUNDING_SCHEMA
    for bad in ((D0.replace(tzinfo=None), D0 + timedelta(days=1)), (D0, D0)):
        with pytest.raises(ValueError):
            data.get_funding(client, ['AUSDT'], *bad)
