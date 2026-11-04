import hashlib
import io
import urllib.error

import pytest

from tidewatch import binance_vision as bv

ZIP = b'PK fake zip bytes'
REL = 'data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip'


def site(files):
    """假的站点：url -> bytes；不存在的 url 按真实 fetch 的约定抛 NotAvailable，并记录访问。"""
    calls = []

    def fetch(url):
        calls.append(url)
        if url not in files:
            raise bv.NotAvailable(url)
        return files[url]
    fetch.calls = calls
    return fetch


def official(data=ZIP, checksum=None):
    digest = checksum or hashlib.sha256(data).hexdigest()
    return {f'{bv.BASE}/{REL}': data,
            f'{bv.BASE}/{REL}.CHECKSUM': f'{digest}  BTCUSDT-1m-2024-01.zip\n'.encode()}


def test_paths_match_official_layout():
    assert bv.monthly_path('klines', 'BTCUSDT', 2024, 1) == REL
    assert bv.monthly_path('fundingRate', 'BTCUSDT', 2024, 1) == \
        'data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-01.zip'
    with pytest.raises(ValueError):
        bv.monthly_path('aggTrades', 'BTCUSDT', 2024, 1)
    assert bv.monthly_path('klines', 'BTCUSDT_240329', 2024, 1).endswith('BTCUSDT_240329-1m-2024-01.zip')


def test_non_ascii_symbol_is_cached_and_url_is_percent_encoded(tmp_path):
    # 官方清单里有中文名合约；本地路径保留原名，请求 URL 必须编码。
    rel = bv.monthly_path('klines', '龙虾USDT', 2025, 11)
    quoted = f'{bv.BASE}/{bv.urllib.parse.quote(rel)}'
    data = b'PK lobster'
    fetch = site({quoted: data, f'{quoted}.CHECKSUM': f'{hashlib.sha256(data).hexdigest()}  x.zip'.encode()})
    path = bv.download('klines', '龙虾USDT', 2025, 11, tmp_path, fetch=fetch)
    assert path == tmp_path / rel and path.read_bytes() == data
    assert all(url.isascii() for url in fetch.calls)


@pytest.mark.parametrize('symbol', ['../../etc/x', 'BTC/USDT', '..', 'BTC.USDT', 'BTC-USDT', '', None])
def test_symbol_cannot_escape_cache_dir(tmp_path, symbol):
    with pytest.raises(ValueError):
        bv.download('klines', symbol, 2024, 1, tmp_path, fetch=site({}))
    assert list(tmp_path.iterdir()) == []


def test_verified_download_is_cached_and_not_fetched_again(tmp_path):
    path = bv.download('klines', 'BTCUSDT', 2024, 1, tmp_path, fetch=site(official()))
    assert path == tmp_path / REL and path.read_bytes() == ZIP
    offline = site({})
    assert bv.download('klines', 'BTCUSDT', 2024, 1, tmp_path, fetch=offline) == path
    assert offline.calls == []


def test_checksum_mismatch_raises_and_leaves_no_cache(tmp_path):
    with pytest.raises(bv.ChecksumMismatch):
        bv.download('klines', 'BTCUSDT', 2024, 1, tmp_path, fetch=site(official(checksum='0' * 64)))
    assert not any(p.is_file() for p in tmp_path.rglob('*'))


def test_corrupted_cache_is_downloaded_again(tmp_path):
    path = bv.download('klines', 'BTCUSDT', 2024, 1, tmp_path, fetch=site(official()))
    path.write_bytes(b'truncated')
    again = site(official())
    assert bv.download('klines', 'BTCUSDT', 2024, 1, tmp_path, fetch=again).read_bytes() == ZIP
    assert len(again.calls) == 2


def test_cache_without_checksum_file_is_not_trusted(tmp_path):
    # 模拟写完 zip、还没写 CHECKSUM 就中断：下次必须重新校验下载。
    path = bv.download('klines', 'BTCUSDT', 2024, 1, tmp_path, fetch=site(official()))
    stored = path.with_name(path.name + '.CHECKSUM')
    stored.unlink()
    again = site(official())
    bv.download('klines', 'BTCUSDT', 2024, 1, tmp_path, fetch=again)
    assert len(again.calls) == 2
    assert path.read_bytes() == ZIP and stored.read_text() == hashlib.sha256(ZIP).hexdigest()


def test_bad_redownload_removes_stale_cache(tmp_path):
    path = bv.download('klines', 'BTCUSDT', 2024, 1, tmp_path, fetch=site(official()))
    path.write_bytes(b'truncated')
    with pytest.raises(bv.ChecksumMismatch):
        bv.download('klines', 'BTCUSDT', 2024, 1, tmp_path, fetch=site(official(checksum='0' * 64)))
    assert not any(p.is_file() for p in tmp_path.rglob('*'))


def test_unparseable_checksum_is_rejected(tmp_path):
    files = official()
    files[f'{bv.BASE}/{REL}.CHECKSUM'] = b'<html>not a checksum</html>'
    with pytest.raises(bv.ChecksumMismatch):
        bv.download('klines', 'BTCUSDT', 2024, 1, tmp_path, fetch=site(files))
    assert not any(p.is_file() for p in tmp_path.rglob('*'))


def test_network_error_is_not_not_available_and_leaves_no_cache(tmp_path):
    def flaky(url):
        if url.endswith('.CHECKSUM'):
            return official()[url]
        raise urllib.error.URLError('connection reset')
    with pytest.raises(urllib.error.URLError) as exc:
        bv.download('klines', 'BTCUSDT', 2024, 1, tmp_path, fetch=flaky)
    assert not isinstance(exc.value, bv.NotAvailable)
    assert not any(p.is_file() for p in tmp_path.rglob('*'))


def test_funding_rate_goes_through_same_verified_flow(tmp_path):
    rel = bv.monthly_path('fundingRate', 'BTCUSDT', 2024, 1)
    data = b'PK funding'
    files = {f'{bv.BASE}/{rel}': data,
             f'{bv.BASE}/{rel}.CHECKSUM': f'{hashlib.sha256(data).hexdigest()}  x.zip'.encode()}
    path = bv.download('fundingRate', 'BTCUSDT', 2024, 1, tmp_path, fetch=site(files))
    assert path == tmp_path / rel and path.read_bytes() == data
    assert oct(path.stat().st_mode & 0o777) == oct(0o644)


def test_missing_month_is_not_available(tmp_path, monkeypatch):
    # 走真实 fetch：urlopen 返回 404，download 应抛 NotAvailable 且不留缓存。
    def urlopen(url, timeout):
        raise urllib.error.HTTPError(url, 404, 'Not Found', {}, io.BytesIO())
    monkeypatch.setattr(bv.urllib.request, 'urlopen', urlopen)
    with pytest.raises(bv.NotAvailable):
        bv.download('klines', 'BTCUSDT', 2010, 1, tmp_path)
    assert not any(p.is_file() for p in tmp_path.rglob('*'))


def test_fetch_maps_only_404_to_not_available(monkeypatch):
    def raising(code):
        def urlopen(url, timeout):
            raise urllib.error.HTTPError(url, code, 'x', {}, io.BytesIO())
        return urlopen
    monkeypatch.setattr(bv.urllib.request, 'urlopen', raising(404))
    with pytest.raises(bv.NotAvailable):
        bv.fetch('https://example.invalid/a.zip')
    monkeypatch.setattr(bv.urllib.request, 'urlopen', raising(503))
    with pytest.raises(urllib.error.HTTPError) as exc:
        bv.fetch('https://example.invalid/a.zip')
    assert not isinstance(exc.value, bv.NotAvailable)


def listing_page(symbols, next_marker=None):
    prefixes = ''.join(f'<CommonPrefixes><Prefix>{bv.KLINES_PREFIX}{s}/</Prefix></CommonPrefixes>' for s in symbols)
    truncated = 'true' if next_marker else 'false'
    marker = f'<NextMarker>{next_marker}</NextMarker>' if next_marker else ''
    return (f'<?xml version="1.0" encoding="UTF-8"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f'<Prefix>{bv.KLINES_PREFIX}</Prefix>{marker}<IsTruncated>{truncated}</IsTruncated>{prefixes}'
            f'</ListBucketResult>').encode()


def test_listing_follows_pagination():
    pages = {'': listing_page(['ETHUSDT', 'BTCUSDT'], f'{bv.KLINES_PREFIX}ETHUSDT/'),
             f'{bv.KLINES_PREFIX}ETHUSDT/': listing_page(['SRMUSDT'])}
    seen = []

    def fetch(url):
        marker = bv.urllib.parse.parse_qs(bv.urllib.parse.urlsplit(url).query).get('marker', [''])[0]
        seen.append(marker)
        return pages[marker]
    assert bv.list_symbols(fetch=fetch) == ['BTCUSDT', 'ETHUSDT', 'SRMUSDT']
    assert seen == ['', f'{bv.KLINES_PREFIX}ETHUSDT/']


def test_listing_without_progress_fails_instead_of_looping():
    # 声称还有下一页却没有 NextMarker、也没有任何前缀可作 marker。
    stuck = listing_page([]).replace(b'<IsTruncated>false', b'<IsTruncated>true')
    with pytest.raises(RuntimeError):
        bv.list_symbols(fetch=lambda url: stuck)


def test_listing_that_repeats_or_rewinds_marker_fails():
    # 每页都返回同一个 NextMarker：第二页起 marker 不再前进。
    same = listing_page(['BTCUSDT'], f'{bv.KLINES_PREFIX}BTCUSDT/')
    with pytest.raises(RuntimeError):
        bv.list_symbols(fetch=lambda url: same)
