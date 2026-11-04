import urllib.parse
from datetime import date

import pytest

from tidewatch import binance_vision as bv
from tidewatch import registry, store

NS = 'http://s3.amazonaws.com/doc/2006-03-01/'


def page(prefixes=(), keys=(), next_marker=None):
    body = ''.join(f'<CommonPrefixes><Prefix>{p}</Prefix></CommonPrefixes>' for p in prefixes)
    body += ''.join(f'<Contents><Key>{k}</Key></Contents>' for k in keys)
    marker = f'<NextMarker>{next_marker}</NextMarker>' if next_marker else ''
    truncated = 'true' if next_marker else 'false'
    return (f'<?xml version="1.0" encoding="UTF-8"?><ListBucketResult xmlns="{NS}">'
            f'{marker}<IsTruncated>{truncated}</IsTruncated>{body}</ListBucketResult>').encode()


def folder(symbol):
    return f'{bv.KLINES_PREFIX}{symbol}/1m/'


def month_keys(symbol, months):
    keys = []
    for y, m in months:
        name = f'{folder(symbol)}{symbol}-1m-{y}-{m:02d}.zip'
        keys += [name, name + '.CHECKSUM']
    return keys


def fake_bucket(months_by_symbol):
    """按 prefix 路由的假 S3：根目录给出合约前缀，合约目录给出月度文件（每页两个 key，强制分页）。"""
    calls = []

    def fetch(url):
        calls.append(url)
        assert url.isascii()
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query, keep_blank_values=True).items()}
        if q['prefix'] == bv.KLINES_PREFIX:
            return page(prefixes=[f'{bv.KLINES_PREFIX}{s}/' for s in months_by_symbol])
        symbol = q['prefix'][len(bv.KLINES_PREFIX):].split('/')[0]
        keys = [k for k in month_keys(symbol, months_by_symbol[symbol]) if k > q['marker']]
        return page(keys=keys[:2], next_marker=keys[1] if len(keys) > 2 else None)
    fetch.calls = calls
    return fetch


@pytest.mark.parametrize('symbol, expected', [
    ('BTCUSDT', ('USDT', 'perpetual')), ('BTCUSDT_240329', ('USDT', 'delivery')),
    ('ETHUSDC', ('USDC', 'perpetual')), ('BTCBUSD_210129', ('BUSD', 'delivery')),
    ('龙虾USDT', ('USDT', 'perpetual')), ('USDT', (None, 'perpetual')), ('BTCDOM', (None, 'perpetual')),
    ('BNXUSDTSETTLED', ('USDT', 'settled')), ('AERGOUSDTSETTLEDSETTLED', ('USDT', 'settled')),
    ('ICPUSDT_SETTLED', ('USDT', 'settled')),
    ('BTCUSD1', (None, 'perpetual')), ('ETHBTC', (None, 'perpetual'))])
def test_classify(symbol, expected):
    assert registry.classify(symbol) == expected


def test_list_months_paginates_without_next_marker():
    # 不带 delimiter 时 S3 不返回 NextMarker，只能以本页最后一个 key 作为 marker。
    keys = month_keys('BTCUSDT', [(2024, 1), (2024, 2)])
    pages = {'': page(keys=keys[:2]).replace(b'<IsTruncated>false', b'<IsTruncated>true'), keys[1]: page(keys=keys[2:])}

    def fetch(url):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query, keep_blank_values=True)
        return pages[q['marker'][0]]
    assert bv.list_months('BTCUSDT', fetch=fetch) == [(2024, 1), (2024, 2)]


def test_list_months_follows_pagination_and_ignores_other_keys():
    fetch = fake_bucket({'龙虾USDT': [(2025, 11), (2025, 12), (2026, 1)]})
    assert bv.list_months('龙虾USDT', fetch=fetch) == [(2025, 11), (2025, 12), (2026, 1)]
    assert len(fetch.calls) == 3  # 6 个 key，每页 2 个


def test_build_rows_marks_delisted_with_one_month_grace_and_skips_symbols_without_files():
    # 月初：BTCUSDT 已有 2026-10，LATEUSDT 的 2026-10 尚未发布，不能算下架；末月 2026-08 才算。
    rows = registry.build_rows({'BTCUSDT': [(2020, 1), (2026, 10)], 'LATEUSDT': [(2026, 9)],
                                'GONEUSDT': [(2026, 8)], 'SRMUSDT': [(2020, 9), (2024, 5)], 'EMPTYUSDT': []})
    assert [(r[0], r[5]) for r in rows] == [('BTCUSDT', 0), ('GONEUSDT', 1), ('LATEUSDT', 0), ('SRMUSDT', 1)]
    assert rows[0] == ['BTCUSDT', 'USDT', 'perpetual', date(2020, 1, 1), date(2026, 10, 1), 0]
    # 跨年：最新 2027-01 时，2026-12 不算下架，2026-11 算。
    edge = registry.build_rows({'A': [(2027, 1)], 'B': [(2026, 12)], 'C': [(2026, 11)]})
    assert [(r[0], r[5]) for r in edge] == [('A', 0), ('B', 0), ('C', 1)]
    assert registry.build_rows({'EMPTYUSDT': []}) == []


@pytest.mark.integration
def test_refresh_is_repeatable_and_require_known_is_case_sensitive(client):
    store.ensure_schema(client)
    fetch = fake_bucket({'BTCUSDT': [(2024, 1), (2024, 2), (2024, 3)], 'SRMUSDT': [(2024, 1)],
                         'BTCUSDT_240329': [(2024, 1), (2024, 2)]})
    assert registry.refresh(client, fetch=fetch) == 3
    assert registry.refresh(client, fetch=fetch) == 3
    rows = client.query('SELECT symbol, contract, delisted FROM symbols FINAL ORDER BY symbol').result_rows
    assert rows == [('BTCUSDT', 'perpetual', 0), ('BTCUSDT_240329', 'delivery', 0), ('SRMUSDT', 'perpetual', 1)]
    registry.require_known(client, ['BTCUSDT', 'SRMUSDT'])
    with pytest.raises(TypeError):
        registry.require_known(client, 'BTCUSDT')
    for bad in (['btcusdt'], ['BTCUSDT', 'NOPEUSDT']):
        with pytest.raises(ValueError):
            registry.require_known(client, bad)
