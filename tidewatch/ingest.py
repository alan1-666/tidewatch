"""批量接入：把 Binance Vision 月度 zip 解析成 ClickHouse 行并写入。

可重复执行：表是 ReplacingMergeTree，同一 (symbol, ts) 重复导入会在 FINAL 下去重。
"""
import csv
import io
import zipfile
from datetime import datetime, timedelta, timezone

from tidewatch import binance_vision as bv

KLINE_COLUMNS = ['symbol', 'ts', 'open', 'high', 'low', 'close', 'volume', 'quote_volume', 'trades',
                 'taker_buy_volume', 'taker_buy_quote_volume']
FUNDING_COLUMNS = ['symbol', 'calc_time', 'interval_hours', 'rate']
TABLES = {'klines': ('klines_1m', KLINE_COLUMNS), 'fundingRate': ('funding_rate', FUNDING_COLUMNS)}
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
# 资金费率 calc_time 比整点晚几毫秒，月初那次可能略早于或晚于月界；只容忍 1 秒。
FUNDING_TOLERANCE_MS = 1000


def utc_ms(value):
    """毫秒整数 → UTC datetime；用 timedelta 避免浮点除法丢毫秒。"""
    return EPOCH + timedelta(milliseconds=value)


def month_bounds_ms(year, month):
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year + month // 12, month % 12 + 1, 1, tzinfo=timezone.utc)
    return int((start - EPOCH).total_seconds() * 1000), int((end - EPOCH).total_seconds() * 1000)


def csv_rows(zip_path):
    """zip 中唯一 CSV 的数据行；跳过表头（官方旧文件无表头、新文件有）。utf-8-sig 去掉可能的 BOM，免得首行数据被误当表头。"""
    with zipfile.ZipFile(zip_path) as archive:
        names = [n for n in archive.namelist() if n.endswith('.csv')]
        if len(names) != 1:
            raise ValueError(f'{zip_path}: 期望恰好一个 CSV，实际 {names}')
        with archive.open(names[0]) as raw:
            for i, row in enumerate(csv.reader(io.TextIOWrapper(raw, 'utf-8-sig'))):
                if i == 0 and row and not row[0].isdigit():
                    continue
                yield row


def _check_month(zip_path, value, lo, hi):
    # 时间戳单位若变成微秒或文件放错月份，会落在区间外；宁可报错也不写入错位数据。
    if not lo <= value < hi:
        raise ValueError(f'{zip_path}: 时间戳 {value} 超出该月范围 [{lo}, {hi})')


def parse_klines(zip_path, symbol, year, month):
    lo, hi = month_bounds_ms(year, month)
    rows = []
    for r in csv_rows(zip_path):
        ts = int(r[0])
        _check_month(zip_path, ts, lo, hi)
        rows.append([symbol, utc_ms(ts), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]),
                     float(r[7]), int(r[8]), float(r[9]), float(r[10])])
    return rows


def parse_funding(zip_path, symbol, year, month):
    lo, hi = month_bounds_ms(year, month)
    rows = []
    for r in csv_rows(zip_path):
        calc_time = int(r[0])
        _check_month(zip_path, calc_time, lo - FUNDING_TOLERANCE_MS, hi + FUNDING_TOLERANCE_MS)
        rows.append([symbol, utc_ms(calc_time), int(r[1]), float(r[2])])
    return rows


PARSERS = {'klines': parse_klines, 'fundingRate': parse_funding}


def ingest_month(client, kind, symbol, year, month, cache_dir, fetch=bv.fetch):
    """下载（或命中缓存）并写入一个月的数据，返回写入行数；文件不存在时抛 bv.NotAvailable。"""
    path = bv.download(kind, symbol, year, month, cache_dir, fetch=fetch)
    rows = PARSERS[kind](path, symbol, year, month)
    table, columns = TABLES[kind]
    if rows:
        client.insert(table, rows, column_names=columns)
    return len(rows)


def ingest(client, symbols, months, cache_dir, kinds=bv.KINDS, fetch=bv.fetch):
    """批量导入；返回 {(kind, symbol, 'YYYY-MM'): 行数，文件不存在为 None}。其他错误直接抛出。"""
    summary = {}
    for symbol in symbols:
        for year, month in months:
            for kind in kinds:
                key = (kind, symbol, f'{year}-{month:02d}')
                try:
                    summary[key] = ingest_month(client, kind, symbol, year, month, cache_dir, fetch=fetch)
                except bv.NotAvailable:
                    summary[key] = None
    return summary
