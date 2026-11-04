<!-- workflow-task
{
  "id": "ch-store",
  "goal": "ClickHouse 存储：klines_1m 与 funding_rate 的表结构及幂等建表",
  "acceptance": [
    "ensure_schema 可重复执行；两张表均为 ReplacingMergeTree(ingested_at)、按月分区、ORDER BY (symbol, ts)，ts 为 UTC 毫秒",
    "同一 (symbol, ts) 重复写入后用 FINAL 查询只得一行，且保留 ingested_at 最新的版本",
    "测试在独立临时数据库中进行并清理，不影响 tidewatch 库"
  ],
  "allow": [
    "tidewatch/**",
    "tests/**"
  ],
  "profile": "integration",
  "phase": "ready",
  "kind": "feature",
  "review_required": true
}
-->
# ch-store

目标：ClickHouse 存储：klines_1m 与 funding_rate 的表结构及幂等建表

## 验收条件

- ensure_schema 可重复执行；两张表均为 ReplacingMergeTree(ingested_at)、按月分区、ORDER BY (symbol, ts)，ts 为 UTC 毫秒
- 同一 (symbol, ts) 重复写入后用 FINAL 查询只得一行，且保留 ingested_at 最新的版本
- 测试在独立临时数据库中进行并清理，不影响 tidewatch 库

- 2026-11-04 15:55:12: 已建立任务；明确事实、未知项和计划后进入 implement。

- 2026-11-04 15:55:12: 列与官方 CSV 对应：K 线取 open_time→ts、OHLC、volume、quote_volume、count→trades、taker_buy_*；忽略 close_time 与 ignore。资金费率 calc_time→ts、funding_interval_hours→interval_hours、last_funding_rate→rate。不封装连接（调用方直接用 clickhouse_connect），store 只提供 DDL 与 ensure_schema(client)。

- 2026-11-04 15:55:44: 验证 passed=True；日志 .workflow/runtime/verify-ch-store-1793778944225863000

- 2026-11-04 15:55:45: 验收 #1 证据：check / pass / test_schema_is_idempotent_and_matches_design：连续两次 ensure_schema；system.tables 中两表均为 ReplacingMergeTree(ingested_at)、toYYYYMM(ts)、symbol, ts；ts 类型 DateTime64(3, UTC)

- 2026-11-04 15:55:45: 验收 #2 证据：check / pass / test_duplicate_writes_collapse…：两次 insert 后原始 count()=3 证明未提前合并；FINAL 下同 (symbol, ts) 只剩 ingested_at 较新的 close=100.5；另有毫秒时间戳往返测试

- 2026-11-04 15:55:45: 验收 #3 证据：check / pass / fixture 为每个用例 CREATE DATABASE tidewatch_test_<随机>，finally 中 DROP；跑完后 system.databases 只剩 tidewatch

- 2026-11-04 15:57:38: 审查修复：funding_rate 增加原始 calc_time，ts 改为 MATERIALIZED 四舍五入到秒（去重键与计费边界不受 1~3ms 抖动影响）；版本测试改为先写新版本后写旧版本并 STOP MERGES；docstring 写明同版本与时钟回拨行为。待办：architecture.md 数据口径补一句资金费率 ts 规整（不在本任务路径内）。

- 2026-11-04 15:57:39: 验证 passed=True；日志 .workflow/runtime/verify-ch-store-1793779058841937000

- 2026-11-04 15:57:39: 验收 #1 证据：check / pass / test_schema_is_idempotent_and_matches_design：两次 ensure_schema；两表 ReplacingMergeTree(ingested_at)、toYYYYMM(ts)、symbol, ts；ts 为 DateTime64(3, UTC)；K 线毫秒时间戳往返一致

- 2026-11-04 15:57:39: 验收 #2 证据：check / pass / keep_highest_ingested_at_not_last_insert：STOP MERGES 后先写新版本再写旧版本，原始 count()=3，FINAL 保留 ingested_at 较新的 close=100.5（证明依赖版本列而非插入顺序）；资金费率 ±ms 抖动规整到同一 ts 后同样只留新版本

- 2026-11-04 15:57:39: 验收 #3 证据：check / pass / fixture 每个用例建 tidewatch_test_<uuid hex> 库，finally 中 DROP；跑完 system.databases 无残留

- 2026-11-04 15:58:47: 审查记录：claude-subagent:general-purpose(read-only) / pass / 两轮只读审查：首轮 pass 附资金费率毫秒抖动与版本测试建议；修复后复查 pass。MATERIALIZED ts 拒绝显式写入、四舍五入边界正确、STOP MERGES 仅作用单表。遗留：get_funding 须显式 SELECT ts（SELECT * 不含 ts）；architecture.md 补资金费率 ts 规整说明

- 2026-11-04 15:58:47: 当前代码的配置内检查与所需审查已通过；不代表发布授权。

- 2026-11-04 15:58:47: 完成归档：ClickHouse 存储完成。后续：取数 SDK 的 get_funding 显式选 ts；文档补资金费率 ts 规整与 t+k 写法
