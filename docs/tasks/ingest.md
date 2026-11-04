<!-- workflow-task
{
  "id": "ingest",
  "goal": "批量接入：把 Binance Vision 月度 K 线与资金费率 zip 解析并写入 ClickHouse，可重复执行",
  "acceptance": [
    "解析兼容有无表头的官方 CSV，列映射与 store 表结构一致，毫秒时间戳精确转换为 UTC",
    "时间戳超出所属月份（含单位变成微秒）时报错不写入；资金费率在月界只容忍 1 秒抖动",
    "同一月份重复导入后 FINAL 行数不变；文件不存在的月份在汇总中记为 None，其他错误直接抛出",
    "data/ 目录不进入 git"
  ],
  "allow": [
    "tidewatch/**",
    "tests/**",
    ".gitignore"
  ],
  "profile": "integration",
  "phase": "ready",
  "kind": "feature",
  "review_required": true
}
-->
# ingest

目标：批量接入：把 Binance Vision 月度 K 线与资金费率 zip 解析并写入 ClickHouse，可重复执行

## 验收条件

- 解析兼容有无表头的官方 CSV，列映射与 store 表结构一致，毫秒时间戳精确转换为 UTC
- 时间戳超出所属月份（含单位变成微秒）时报错不写入；资金费率在月界只容忍 1 秒抖动
- 同一月份重复导入后 FINAL 行数不变；文件不存在的月份在汇总中记为 None，其他错误直接抛出
- data/ 目录不进入 git

- 2026-11-04 16:13:28: 已建立任务；明确事实、未知项和计划后进入 implement。

- 2026-11-04 16:13:28: 实现 tidewatch/ingest.py：csv_rows 跳过首行表头；parse_klines / parse_funding 按月界校验；ingest_month 下载→解析→insert；ingest 汇总。资金费率只写 calc_time，ts 由库计算。

- 2026-11-04 16:14:46: 工作流 policy 未排除 data/，实测导入的缓存被判越界。暂将 data/raw 移出仓库完成本任务；随后单独 maintenance 把 data/** 加入 excluded_paths 再移回。

- 2026-11-04 16:14:47: 验证 passed=True；日志 .workflow/runtime/verify-ingest-1793780086396529000

- 2026-11-04 16:14:55: 验收 #1 证据：check / pass / test_klines_parse_with_or_without_header（参数化有/无表头）断言列映射：close、trades 为 int、quote_volume 取第 8 列跳过 close_time；test_millisecond_precision_is_exact；实测 BTCUSDT 2024-01（有表头）与 2020-01（无表头）各 44640 行=31×1440

- 2026-11-04 16:14:55: 验收 #2 证据：check / pass / test_kline_outside_month_or_wrong_unit_is_rejected：上月、下月、微秒单位均 ValueError；test_funding_tolerates…：月界 -2ms/-1ms 通过，-2000ms 拒绝；test_month_bounds_cross_year

- 2026-11-04 16:14:55: 验收 #3 证据：check / pass / test_ingest_is_idempotent_and_reports_missing_months：两次导入汇总相同，原始 count=4、FINAL=2；缺失月份为 None；资金费率 ts 规整到整秒；test_ingest_propagates_errors_other_than_missing：错月文件抛 ValueError 且未写入

- 2026-11-04 16:14:55: 验收 #4 证据：manual / pass / .gitignore 新增 data/；git check-ignore 确认 data/raw/x.zip 被忽略；实测导入后 git status 不含 data/（工作流 policy 尚未排除 data/，已暂移缓存，另开 maintenance 处理）

- 2026-11-04 16:16:27: 审查修复：.gitignore 改为 /data/ 只忽略根目录；K 线整行断言；utf-8-sig 去 BOM；幂等测试 STOP MERGES。记录：并发导入同一月份时缓存有竞态（重跑可恢复）；官方重发删行不会清理旧行；K 线 0 行应由 CLI 提示。maintenance 排除 data/** 之前，cache_dir 须在仓库外。

- 2026-11-04 16:16:28: 验证 passed=True；日志 .workflow/runtime/verify-ingest-1793780187353772000

- 2026-11-04 16:16:28: 验收 #1 证据：check / pass / test_klines_parse_with_or_without_header：有/无表头两种格式整行比对全部 11 列（任意两列错位即失败）；test_bom_before_headerless_data…；test_millisecond_precision_is_exact；实测 BTCUSDT 2024-01 与 2020-01 各 44640 行

- 2026-11-04 16:16:28: 验收 #2 证据：check / pass / test_kline_outside_month_or_wrong_unit_is_rejected：上月、下月、微秒单位均 ValueError；test_funding_tolerates…：月界 -2ms/-1ms 通过，-2000ms 拒绝；test_month_bounds_cross_year

- 2026-11-04 16:16:28: 验收 #3 证据：check / pass / test_ingest_is_idempotent…（STOP MERGES 后）：两次导入汇总相同，原始 count=4、FINAL=2；缺失月份 None；test_ingest_propagates_errors…：错月文件抛错且未写入

- 2026-11-04 16:16:28: 验收 #4 证据：manual / pass / .gitignore 为 /data/：git check-ignore 只命中 data/raw/x，tests/data/x 与 tidewatch/data/x 不被忽略

- 2026-11-04 16:16:54: 审查记录：claude-subagent:general-purpose(read-only) / pass / 两轮只读审查：列映射逐列核对、整月先解析后写入无部分写入、ReplacingMergeTree 幂等；修复 /data/ 范围、整行断言、BOM、STOP MERGES 后确认 pass。后续：并发同月缓存竞态、官方重发删行残留、K 线 0 行提示

- 2026-11-04 16:16:54: 当前代码的配置内检查与所需审查已通过；不代表发布授权。

- 2026-11-04 16:16:54: 完成归档：批量接入完成
