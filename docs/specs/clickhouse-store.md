# ClickHouse 存储

模块：`tidewatch/store.py`。定义表结构并提供 `ensure_schema(client)`；连接由调用方创建。将来其他语言的服务（如 Go 实时接入）写入同一批表，因此本文件也是跨服务的存储契约。

状态：已实现（任务 ch-store，symbol-registry-v2 增加 `symbols` 表）。

## 需求

### 建表可重复执行

`ensure_schema` 可重复调用。`klines_1m` 与 `funding_rate` 均为 `ReplacingMergeTree(ingested_at)`，`PARTITION BY toYYYYMM(ts)`，`ORDER BY (symbol, ts)`，`ts` 为 `DateTime64(3, 'UTC')`。`symbols` 为 `ReplacingMergeTree(refreshed_at)`，`ORDER BY symbol`，不分区。

- 场景：连续建表两次，`system.tables` 中引擎、分区键、排序键与上述一致。
- 测试：`test_schema_is_idempotent_and_matches_design`、`test_kline_millisecond_utc_timestamp_round_trips`

### 重复写入保留版本最新的一行

同一 `(symbol, ts)` 多次写入后，`FINAL` 下只剩 `ingested_at` 最大的那行；版本相同时保留最后插入的（ClickHouse 引擎行为，未单测）。去重发生在后台合并时，需要精确结果的读取必须加 `FINAL`。

- 场景：先写版本较新的、再写较旧的，并停止合并；未合并时 `count()` 包含重复，`FINAL` 留下较新的版本。
- 测试：`test_duplicate_writes_keep_highest_ingested_at_not_last_insert`

### 资金费率结算时刻规整到秒

官方 `calc_time` 常比整点晚 1~3ms，原值存入 `calc_time` 列。`ts` 是 `MATERIALIZED` 列，取 `calc_time` 四舍五入到秒，由库计算：写入时不能指定 `ts`，`SELECT *` 也不返回它，读取方必须显式选 `ts`。去重和计费边界都用 `ts`。

- 场景：`+1ms`、`+3ms` 两次写入落到同一个 `ts`，只留版本较新的；下一整点 `-2ms` 规整到下一整点。
- 测试：`test_funding_ts_is_calc_time_rounded_to_second_and_dedups_jitter`

## 已知限制

- `CREATE TABLE IF NOT EXISTS` 发现不了已有表结构与 DDL 不一致，表结构变更需另做迁移。
- `ingested_at` 取服务端时钟，时钟回拨会让较晚的导入被丢弃。
- 官方重新发布某月文件并删掉部分行时，旧行不会被清理；需要时按（合约, 月）删除后重导。
