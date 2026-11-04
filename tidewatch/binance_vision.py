"""data.binance.vision 上 USDT-M 永续的历史数据：下载、校验、缓存与合约清单。

只做网络与文件 IO，不解析 CSV。所有函数都接受可注入的 fetch，便于离线测试。
"""
import hashlib
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = 'https://data.binance.vision'
LISTING = 'https://s3-ap-northeast-1.amazonaws.com/data.binance.vision'
KLINES_PREFIX = 'data/futures/um/monthly/klines/'
_S3 = '{http://s3.amazonaws.com/doc/2006-03-01/}'
KINDS = ('klines', 'fundingRate')


class NotAvailable(Exception):
    """文件不存在：合约当月未上市、已下架，或当月数据尚未发布。与网络故障区分开。"""


class ChecksumMismatch(Exception):
    """下载内容与官方 .CHECKSUM 不一致。"""


def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotAvailable(url) from exc
        raise


def monthly_path(kind, symbol, year, month):
    """官方月度文件在站点上的相对路径；K 线只取 1m，其余粒度由 ClickHouse 聚合。"""
    # symbol 会拼进本地缓存路径和 URL：只放行 Unicode 字母、数字和下划线。
    # 官方确有中文名合约（如 龙虾USDT）和带下划线的交割合约；/ . - 等可穿越路径的字符一律拒绝。
    if not isinstance(symbol, str) or not re.fullmatch(r'\w+', symbol):
        raise ValueError(f'非法合约名: {symbol!r}')
    if kind == 'klines':
        return f'data/futures/um/monthly/klines/{symbol}/1m/{symbol}-1m-{year}-{month:02d}.zip'
    if kind == 'fundingRate':
        return f'data/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{year}-{month:02d}.zip'
    raise ValueError(f'未知数据类型 {kind}，可选 {KINDS}')


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _parse_checksum(text):
    # 官方格式为 "<sha256>  <文件名>"。
    digest = text.split()[0] if text.split() else ''
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ChecksumMismatch(f'无法识别的 CHECKSUM 内容: {text[:80]!r}')
    return digest


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.pending-')
    try:
        os.fchmod(fd, 0o644)  # mkstemp 默认 0600，缓存需要能被其他进程读取
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def download(kind, symbol, year, month, cache_dir, fetch=fetch):
    """返回已校验的本地 zip 路径。

    缓存里同时保存 zip 与它的 CHECKSUM；两者对得上就直接返回，不访问网络。
    先写 zip 后写 CHECKSUM，中途中断时下次会重新下载，不会把半成品当成有效缓存。
    """
    rel = monthly_path(kind, symbol, year, month)
    dest = Path(cache_dir) / rel
    stored = dest.with_name(dest.name + '.CHECKSUM')
    if dest.is_file() and stored.is_file() and _sha256(dest.read_bytes()).encode() == stored.read_bytes().strip():
        return dest
    # 缓存无效：先清掉，保证之后无论成功与否，都不会留下过不了校验的旧文件。
    stored.unlink(missing_ok=True)
    dest.unlink(missing_ok=True)
    url = f'{BASE}/{urllib.parse.quote(rel)}'  # 中文合约名需百分号编码
    expected = _parse_checksum(fetch(f'{url}.CHECKSUM').decode())
    data = fetch(url)
    if _sha256(data) != expected:
        raise ChecksumMismatch(f'{rel}: 期望 {expected}，实际 {_sha256(data)}')
    _atomic_write(dest, data)
    _atomic_write(stored, expected.encode())
    return dest


def list_symbols(fetch=fetch):
    """全部 USDT-M 合约（含 USDC 计价、交割合约与已下架合约），按字母排序；筛选交给合约注册表。

    官方会保留已下架合约的历史目录，所以按目录列举能避免幸存者偏差。
    """
    symbols, marker = [], ''
    while True:
        query = urllib.parse.urlencode({'delimiter': '/', 'prefix': KLINES_PREFIX, 'marker': marker})
        root = ET.fromstring(fetch(f'{LISTING}?{query}'))
        prefixes = [p.text for p in root.findall(f'{_S3}CommonPrefixes/{_S3}Prefix')]
        symbols += [p.rstrip('/').rsplit('/', 1)[1] for p in prefixes]
        if root.findtext(f'{_S3}IsTruncated') != 'true':
            return sorted(symbols)
        next_marker = root.findtext(f'{_S3}NextMarker') or (prefixes[-1] if prefixes else '')
        # S3 的 marker 按字典序单调递增；不前进就是异常，避免死循环。
        if not next_marker or next_marker <= marker:
            raise RuntimeError('S3 清单声称还有下一页，却没有给出更靠后的 marker')
        marker = next_marker
