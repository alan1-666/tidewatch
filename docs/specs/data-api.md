# 统一取数 SDK

模块：`tidewatch/data.py`。研究、回测与报告共用的唯一取数口径，返回 polars 长表，每行一个 `(ts, symbol)`，按 `(symbol, ts)` 排序。

状态：已实现（任务 data-api）。

## 需求

### K 线由 1m 在库内聚合

`get_bars(client, symbols, freq, start, end)` 支持 `1m`、`5m`、`15m`、`1h`、`4h`、`1d`。聚合在 ClickHouse 内完成，读取 `klines_1m FINAL`，重复导入的同一分钟只计一次。每个周期的取值规则：

- 开盘价：周期内最早一分钟的开盘价；收盘价：最晚一分钟的收盘价。
- 最高价、最低价：取极值。
- 成交量、成交额、成交笔数、主动买入量和主动买入额：求和。
- `ts`：周期开盘时刻，日线按 UTC 0 点切分。

返回列与类型固定为 `data.BAR_SCHEMA`：`ts` 为 `Datetime('ms', 'UTC')`，`symbol` 为 String，`trades` 与 `bars` 为 Int64，其余为 Float64。空结果与非空结果类型一致，可以直接拼接。

- 场景：用价格与各类量都不单调的数据，按 1h、15m、5m 聚合后与纯 Python 独立重算的结果逐列一致；同一分钟重复导入时取新版本，不重复计数。
- 场景：前一天 23:59 的一根与当天的数据分属两根日线。
- 测试：`test_hourly_aggregation_reports_gap_and_never_fills`、`test_finer_frequencies_match_reference`、`test_daily_bars_split_at_utc_midnight`。另做过变异检查：把开收改成极值、去掉 FINAL、对调两个 taker 列、用计数代替成交量，测试均失败。

### 显式暴露缺口，不补值

每行的 `bars` 是该周期实际包含的 1m 根数，满额为周期分钟数。没有任何 1m 的周期不输出，任何情况下都不补值、不前向填充。缺口的下游处理见 [time-conventions.md](time-conventions.md)。

- 场景：1 小时内缺 10 分钟，该行 `bars` 为 50；整小时无数据时不输出该行。
- 场景（人工核对）：真实数据 2026-10-28 官方缺失，取 10-27 至 10-30 的日线不输出该日。
- 测试：`test_hourly_aggregation_reports_gap_and_never_fills`

### 区间半开且对齐周期

区间为 `[start, end)`。`start` 和 `end` 必须是带时区的 datetime，并且都对齐所选周期（相对 Unix 纪元），以免首尾出现残缺周期。周期不支持、未对齐、不带时区、`start ≥ end` 时报 `ValueError`。`symbols` 必须是列表，传入单个字符串报 `TypeError`。

- 场景：1m 取 `[00:00, 00:05)` 恰好 5 行，其他合约的数据不混入。
- 场景：结果为空时类型与非空结果完全一致，二者可以 `pl.concat`。
- 测试：`test_check_range_rejects_bad_input`、`test_check_range_accepts_aligned_utc_and_other_timezones`、`test_range_is_half_open_and_other_symbols_excluded`、`test_empty_result_keeps_schema`

### 资金费率取规整后的结算时刻

`get_funding(client, symbols, start, end)` 返回 `ts, symbol, rate, interval_hours`，类型固定为 `data.FUNDING_SCHEMA`。`ts` 是规整到秒的结算时刻，属于 `MATERIALIZED` 列，查询时显式选取；区间为 `[start, end)`，`start`、`end` 必须带时区且 `start < end`，否则报 `ValueError`（不要求对齐周期）。

- 场景：`calc_time` 晚 3ms 的结算以整点返回；恰好等于 `end` 的那次不返回；不带时区或空区间报错；空结果类型不变。
- 测试：`test_funding_returns_rounded_ts_in_utc`

## 已知限制

- 结果整体读入内存。10 个合约 3 个月的 1m 约 131 万行，可以接受；全市场长区间的 1m 需要分批读取。
- 不校验 `symbols` 是否在合约注册表中，未知合约返回空表；需要拦截手写错误时，调用方先用 `registry.require_known`。
