# 批量接入

模块：`tidewatch/ingest.py`。把 Binance Vision 月度 zip 解析成 ClickHouse 行并写入，可以重复执行。

状态：已实现（任务 ingest）。

## 需求

### 解析官方 CSV

兼容有表头和无表头两种格式，读取时去掉 BOM。K 线列映射：`open_time→ts`，`open/high/low/close/volume`，`quote_volume`，`count→trades`，`taker_buy_volume`，`taker_buy_quote_volume`；`close_time` 与 `ignore` 不入库。资金费率只写 `calc_time`、`interval_hours`、`rate`。毫秒时间戳用整数换算，不经过浮点。每个 zip 必须恰好包含一个 CSV。

- 场景：有表头和无表头两种格式整行比对 11 列，任意两列错位都会被发现。
- 测试：`test_klines_parse_with_or_without_header`、`test_bom_before_headerless_data_does_not_drop_first_row`、`test_millisecond_precision_is_exact`、`test_zip_must_hold_exactly_one_csv`

### 时间戳必须属于文件所在月份

K 线时间戳超出该月 `[月初, 下月初)` 就报错且不写入，用来防止文件放错月份或时间单位变成微秒。资金费率在月界前后各容忍 1 秒。

- 场景：上月、下月和微秒单位的时间戳都报 `ValueError`；资金费率 `-2ms` 通过，`-2000ms` 拒绝。
- 测试：`test_kline_outside_month_or_wrong_unit_is_rejected`、`test_funding_tolerates_millisecond_jitter_at_month_edges`、`test_month_bounds_cross_year`

### 幂等导入与结果汇总

整月先解析完再一次写入，解析出错时不会写入一部分。`ingest` 返回 `{(kind, symbol, 'YYYY-MM'): 行数}`：文件不存在为 `None`，文件存在但无数据为 `0`（未单测），其他错误直接抛出。重复导入后 `FINAL` 行数不变。

- 场景：导入两次，汇总相同，`FINAL` 行数不变，缺失月份为 `None`。
- 场景：放错月份的文件抛错，表里没有写入任何行。
- 测试：`test_ingest_is_idempotent_and_reports_missing_months`、`test_ingest_propagates_errors_other_than_missing`

## 已知限制

- 官方数据本身可能缺失：2026-10 的月度文件和日度文件都没有 10-28 这一天。接入不补值；完整度检查待取数 SDK 或 CLI 实现，按"天数 × 1440"对比行数。
- K 线为 0 行通常意味着异常，目前只体现在汇总里，尚无提示。
