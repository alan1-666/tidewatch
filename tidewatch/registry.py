"""合约注册表：每个合约的类型、计价币、有数据的首末月份，以及是否已下架。

来源是 Binance Vision 的目录（含已下架合约），而不是当前 exchangeInfo，避免幸存者偏差。
"""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from tidewatch import binance_vision as bv

QUOTES = ('USDT', 'USDC', 'BUSD')
COLUMNS = ['symbol', 'quote', 'contract', 'first_month', 'last_month', 'delisted']


def classify(symbol):
    """(计价币, 合约类型)。计价币无法识别时为 None。

    交割合约形如 BTCUSDT_240329。结算后改名的合约带 SETTLED 或 _SETTLED 后缀（官方偶有叠加，
    如 AERGOUSDTSETTLEDSETTLED、ICPUSDT_SETTLED），先去掉后缀再判断，类型记为 settled，
    免得被当成交割合约或让可交易集合漏掉它们。
    """
    stripped = re.sub(r'(_?SETTLED)+$', '', symbol)
    base = stripped.split('_', 1)[0]
    quote = next((q for q in QUOTES if base.endswith(q) and len(base) > len(q)), None)
    contract = 'settled' if stripped != symbol else 'delivery' if '_' in stripped else 'perpetual'
    return quote, contract


def build_rows(months_by_symbol):
    """months_by_symbol: {symbol: [(year, month), ...]}。没有任何月份文件的合约不入表。

    最新已发布月份取所有合约末月的最大值。上月文件在月初陆续发布，所以只有末月早于
    "最新月份减一个月"才算已下架，避免月初把尚未发布的合约误判。交割合约到期也算下架。
    """
    spans = {s: (min(m), max(m)) for s, m in months_by_symbol.items() if m}
    if not spans:
        return []
    latest = max(last for _, last in spans.values())
    cutoff = (latest[0], latest[1] - 1) if latest[1] > 1 else (latest[0] - 1, 12)
    rows = []
    for symbol, (first, last) in sorted(spans.items()):
        quote, contract = classify(symbol)
        rows.append([symbol, quote or '', contract, date(*first, 1), date(*last, 1), int(last < cutoff)])
    return rows


def refresh(client, fetch=bv.fetch, workers=16):
    """重新列举全部合约及其月份并写入 symbols 表，返回写入行数。约 1000 次只读请求，并发执行。"""
    symbols = bv.list_symbols(fetch=fetch)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        months = dict(zip(symbols, pool.map(lambda s: bv.list_months(s, fetch=fetch), symbols)))
    rows = build_rows(months)
    if rows:
        client.insert('symbols', rows, column_names=COLUMNS)
    return len(rows)


def require_known(client, symbols):
    """确认 symbols 都在注册表中（大小写敏感），否则报错。

    macOS 文件系统不区分大小写，btcusdt 会命中 BTCUSDT 的缓存；在入口拦住手写的错误合约名。
    注意：月中新上市的合约在首个月度文件发布前不在注册表中，会被拒绝。
    """
    if isinstance(symbols, str):
        raise TypeError('symbols 应为合约名列表，而不是单个字符串')
    known = {r[0] for r in client.query('SELECT symbol FROM symbols FINAL WHERE symbol IN {s:Array(String)}',
                                         parameters={'s': list(symbols)}).result_rows}
    unknown = sorted(set(symbols) - known)
    if unknown:
        raise ValueError(f'注册表中没有这些合约: {unknown}')
