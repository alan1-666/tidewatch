import hashlib
import io
import zipfile
from datetime import datetime, timezone

import pytest

from tidewatch import binance_vision as bv
from tidewatch import ingest

KLINE_HEADER = 'open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore'
JAN = 1704067200000  # 2024-01-01 00:00:00 UTC
FEB = 1706745600000  # 2024-02-01 00:00:00 UTC


def kline_line(ts, close='42331.90'):
    return f'{ts},42314.00,42335.80,42289.60,{close},289.641,{ts + 59999},12256155.25625,3310,175.211,7414459.86355,0'


def make_zip(lines, name='x.csv'):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(name, '\n'.join(lines) + '\n')
    return buffer.getvalue()


def write_zip(tmp_path, lines, **kw):
    path = tmp_path / 'month.zip'
    path.write_bytes(make_zip(lines, **kw))
    return path


@pytest.mark.parametrize('header', [True, False])
def test_klines_parse_with_or_without_header(tmp_path, header):
    lines = ([KLINE_HEADER] if header else []) + [kline_line(JAN), kline_line(JAN + 60000, '42350.40')]
    rows = ingest.parse_klines(write_zip(tmp_path, lines), 'BTCUSDT', 2024, 1)
    # 各列取值互不相同，整行比对能发现任意两列错位；close_time 与 ignore 不入库。
    assert rows[0] == ['BTCUSDT', datetime(2024, 1, 1, tzinfo=timezone.utc), 42314.0, 42335.8, 42289.6, 42331.9,
                       289.641, 12256155.25625, 3310, 175.211, 7414459.86355]
    assert rows[1][5] == 42350.40 and isinstance(rows[0][8], int)


def test_bom_before_headerless_data_does_not_drop_first_row(tmp_path):
    path = tmp_path / 'bom.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('x.csv', '\ufeff' + kline_line(JAN) + '\n')
    assert len(ingest.parse_klines(path, 'BTCUSDT', 2024, 1)) == 1


def test_millisecond_precision_is_exact():
    assert ingest.utc_ms(1704067200123) == datetime(2024, 1, 1, 0, 0, 0, 123000, tzinfo=timezone.utc)


@pytest.mark.parametrize('ts', [JAN - 60000, FEB, JAN * 1000])
def test_kline_outside_month_or_wrong_unit_is_rejected(tmp_path, ts):
    # 上月数据、下月数据、单位变成微秒，都必须拒绝而不是写错位。
    with pytest.raises(ValueError):
        ingest.parse_klines(write_zip(tmp_path, [kline_line(ts)]), 'BTCUSDT', 2024, 1)


def test_month_bounds_cross_year():
    assert ingest.month_bounds_ms(2023, 12) == (1701388800000, JAN)


def test_funding_tolerates_millisecond_jitter_at_month_edges(tmp_path):
    lines = ['calc_time,funding_interval_hours,last_funding_rate',
             f'{JAN - 2},8,0.0001', f'{JAN + 8 * 3600_000 + 3},4,-0.0002', f'{FEB - 1},8,0.0003']
    rows = ingest.parse_funding(write_zip(tmp_path, lines), 'BTCUSDT', 2024, 1)
    assert [(r[2], r[3]) for r in rows] == [(8, 0.0001), (4, -0.0002), (8, 0.0003)]
    with pytest.raises(ValueError):
        ingest.parse_funding(write_zip(tmp_path, [f'{JAN - 2000},8,0.1']), 'BTCUSDT', 2024, 1)


def test_zip_must_hold_exactly_one_csv(tmp_path):
    path = tmp_path / 'two.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('a.csv', kline_line(JAN))
        archive.writestr('b.csv', kline_line(JAN))
    with pytest.raises(ValueError):
        list(ingest.csv_rows(path))


def fake_site(payloads):
    """payloads: {(kind, symbol, year, month): zip bytes}；附上正确 CHECKSUM，其他 URL 返回 404。"""
    files = {}
    for (kind, symbol, year, month), data in payloads.items():
        url = f'{bv.BASE}/{bv.urllib.parse.quote(bv.monthly_path(kind, symbol, year, month))}'
        files[url] = data
        files[url + '.CHECKSUM'] = f'{hashlib.sha256(data).hexdigest()}  f.zip'.encode()

    def fetch(url):
        if url not in files:
            raise bv.NotAvailable(url)
        return files[url]
    return fetch


@pytest.mark.integration
def test_ingest_is_idempotent_and_reports_missing_months(client, tmp_path):
    from tidewatch import store
    store.ensure_schema(client)
    client.command('SYSTEM STOP MERGES klines_1m')  # 保证"未合并时有重复"的断言稳定
    klines = make_zip([KLINE_HEADER, kline_line(JAN), kline_line(JAN + 60000)])
    funding = make_zip(['calc_time,funding_interval_hours,last_funding_rate', f'{JAN + 1},8,0.0001'])
    fetch = fake_site({('klines', 'BTCUSDT', 2024, 1): klines, ('fundingRate', 'BTCUSDT', 2024, 1): funding})
    months = [(2024, 1), (2024, 2)]
    first = ingest.ingest(client, ['BTCUSDT'], months, tmp_path, fetch=fetch)
    assert first == {('klines', 'BTCUSDT', '2024-01'): 2, ('fundingRate', 'BTCUSDT', '2024-01'): 1,
                     ('klines', 'BTCUSDT', '2024-02'): None, ('fundingRate', 'BTCUSDT', '2024-02'): None}
    assert ingest.ingest(client, ['BTCUSDT'], months, tmp_path, fetch=fetch) == first
    assert client.command('SELECT count() FROM klines_1m') == 4  # 两次导入，未合并
    assert client.command('SELECT count() FROM klines_1m FINAL') == 2
    assert client.command('SELECT count() FROM funding_rate FINAL') == 1
    # 资金费率只写 calc_time，ts 由库规整到整秒。
    assert client.command('SELECT toUnixTimestamp64Milli(ts) FROM funding_rate FINAL') == JAN
    row = client.query('SELECT close, trades, quote_volume FROM klines_1m FINAL ORDER BY ts LIMIT 1').result_rows[0]
    assert row == (42331.90, 3310, 12256155.25625)


@pytest.mark.integration
def test_ingest_propagates_errors_other_than_missing(client, tmp_path):
    from tidewatch import store
    store.ensure_schema(client)
    bad = make_zip([kline_line(FEB)])  # 放错月份
    with pytest.raises(ValueError):
        ingest.ingest(client, ['BTCUSDT'], [(2024, 1)], tmp_path, kinds=('klines',),
                      fetch=fake_site({('klines', 'BTCUSDT', 2024, 1): bad}))
    assert client.command('SELECT count() FROM klines_1m') == 0
