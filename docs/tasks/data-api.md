<!-- workflow-task
{
  "id": "data-api",
  "goal": "统一取数 SDK：按合约、周期、时间区间取 K 线与资金费率，返回 polars 长表，显式暴露数据缺口",
  "acceptance": [
    "get_bars 支持 1m/5m/15m/1h/4h/1d，在 ClickHouse 内由 1m 聚合（FINAL 去重）：开收为周期内首末分钟、高低为极值、量与笔数求和，日线按 UTC 0 点切分",
    "每行输出该周期实际包含的 1m 根数 bars；没有任何 1m 的周期不输出；任何情况下不补值",
    "区间为 [start, end)，start 与 end 必须对齐所选周期，否则报错；周期不支持时报错",
    "get_funding 显式选取规整后的 ts，返回 ts、symbol、rate、interval_hours；ts 列为 UTC 时区的 datetime",
    "docs/specs/data-api.md 记录上述规则与对应测试，time-conventions 的缺口规则标明聚合部分已实现"
  ],
  "allow": [
    "tidewatch/**",
    "tests/**",
    "docs/specs/*.md",
    "pyproject.toml",
    "uv.lock"
  ],
  "profile": "integration",
  "phase": "ready",
  "kind": "feature",
  "review_required": true
}
-->
# data-api

目标：统一取数 SDK：按合约、周期、时间区间取 K 线与资金费率，返回 polars 长表，显式暴露数据缺口

## 验收条件

- get_bars 支持 1m/5m/15m/1h/4h/1d，在 ClickHouse 内由 1m 聚合（FINAL 去重）：开收为周期内首末分钟、高低为极值、量与笔数求和，日线按 UTC 0 点切分
- 每行输出该周期实际包含的 1m 根数 bars；没有任何 1m 的周期不输出；任何情况下不补值
- 区间为 [start, end)，start 与 end 必须对齐所选周期，否则报错；周期不支持时报错
- get_funding 显式选取规整后的 ts，返回 ts、symbol、rate、interval_hours；ts 列为 UTC 时区的 datetime
- docs/specs/data-api.md 记录上述规则与对应测试，time-conventions 的缺口规则标明聚合部分已实现

- 2026-11-05 10:45:51: 已建立任务；明确事实、未知项和计划后进入 implement。

- 2026-11-05 10:45:51: 新增依赖 polars（取数结果的标准格式，架构已定）；不引入 pyarrow，用 clickhouse-connect 的列式结果直接构造 DataFrame。

- 2026-11-05 10:48:49: 验证 passed=True；日志 .workflow/runtime/verify-data-api-1793846928044284000

- 2026-11-05 10:48:59: 验收 #1 证据：check / pass / test_hourly_aggregation…：开=新版本 99、收=00:59、高低极值、量与笔数求和，FINAL 下重复分钟只计一次（否则 bars=61）；test_daily_bars_split_at_utc_midnight：前一日 23:59 单独成一根日线

- 2026-11-05 10:48:59: 验收 #2 证据：check / pass / test_hourly_aggregation…：缺 10 分钟的小时 bars=50，02:00 整小时无数据不输出；实测正式库 10-27~10-30 日线仅 27、29 两行（官方缺 10-28）

- 2026-11-05 10:48:59: 验收 #3 证据：check / pass / test_check_range_rejects_bad_input（不支持周期、首尾未对齐、无时区、空区间）与 accepts_aligned…（含东京时区对齐）；集成 test_range_is_half_open…：[00:00,00:05) 恰 5 行

- 2026-11-05 10:48:59: 验收 #4 证据：check / pass / test_funding_returns_rounded_ts_in_utc：calc_time+3ms 以整点返回、等于 end 的不返回、ts 为 Datetime(ms, UTC)；get_funding 显式 SELECT ts

- 2026-11-05 10:48:59: 验收 #5 证据：manual / pass / 新增 docs/specs/data-api.md（四条需求含场景与测试，引用的测试名均存在）；time-conventions 缺口规则的测试行标明聚合部分已实现、标签待实现

- 2026-11-05 10:53:06: 首审 fail：中1 空结果列类型为 Null（改为固定 BAR_SCHEMA/FUNDING_SCHEMA）；中2 测试分不出首末分钟与极值（改为非单调数据 + 纯 Python 参考实现逐列比对，补 5m/15m）。顺带修低1（全列比对）、低2（规格注明人工核对）、低3（get_funding 校验时区与区间）。补做变异检查 5 项均被测试拦下。

- 2026-11-05 10:53:08: 验证 passed=True；日志 .workflow/runtime/verify-data-api-1793847186376276000

- 2026-11-05 10:53:08: 验收 #1 证据：check / pass / test_hourly_aggregation… 与 test_finer_frequencies_match_reference（1h/15m/5m）：非单调数据下与纯 Python 参考实现逐列一致；test_daily_bars_split_at_utc_midnight；变异检查：开收改极值、去 FINAL、对调 taker 列、计数代成交量均使测试失败

- 2026-11-05 10:53:08: 验收 #2 证据：check / pass / test_hourly_aggregation…：bars=[60,50]，02:00 无数据不输出；实测正式库 10-27~10-30 日线不含 10-28（人工核对）

- 2026-11-05 10:53:08: 验收 #3 证据：check / pass / test_check_range_rejects_bad_input / accepts_aligned…；集成 test_range_is_half_open…：[00:00,00:05) 恰 5 行，其他合约不混入

- 2026-11-05 10:53:08: 验收 #4 证据：check / pass / test_funding_returns_rounded_ts_in_utc：+3ms 以整点返回、等于 end 不返回、类型等于 FUNDING_SCHEMA、空结果类型一致、无时区或空区间报 ValueError

- 2026-11-05 10:53:08: 验收 #5 证据：manual / pass / data-api.md 四条需求含场景、测试与变异检查说明，引用测试名均存在；人工核对项已注明；time-conventions 缺口规则标明聚合已实现

- 2026-11-05 10:53:23: 验证 passed=True；日志 .workflow/runtime/verify-data-api-1793847201927623000

- 2026-11-05 10:53:23: 验收 #1 证据：check / pass / test_hourly_aggregation… 与 test_finer_frequencies_match_reference（1h/15m/5m）：非单调数据下与纯 Python 参考实现逐列一致；test_daily_bars_split_at_utc_midnight；变异检查：开收改极值、去 FINAL、对调 taker 列、计数代成交量均使测试失败

- 2026-11-05 10:53:23: 验收 #2 证据：check / pass / test_hourly_aggregation…：bars=[60,50]，02:00 无数据不输出；实测正式库 10-27~10-30 日线不含 10-28（人工核对）

- 2026-11-05 10:53:23: 验收 #3 证据：check / pass / test_check_range_rejects_bad_input / accepts_aligned…；集成 test_range_is_half_open…：[00:00,00:05) 恰 5 行，其他合约不混入

- 2026-11-05 10:53:23: 验收 #4 证据：check / pass / test_funding_returns_rounded_ts_in_utc：+3ms 以整点返回、等于 end 不返回、类型等于 FUNDING_SCHEMA、空结果类型一致、无时区或空区间报 ValueError

- 2026-11-05 10:53:23: 验收 #5 证据：manual / pass / data-api.md 四条需求含场景、测试与变异检查说明，引用测试名均存在；人工核对项已注明；time-conventions 缺口规则标明聚合已实现

- 2026-11-05 10:54:28: 审查记录：claude-subagent:general-purpose(read-only, fresh) / pass / 两轮：首审 fail（中1 空结果列类型为 Null、中2 测试分不出首末分钟与极值）；修复后复审 pass。审查者另用正式库数据以 polars 独立聚合交叉核对 5m/15m/1h/4h/1d 全部一致，UTC 与东京时区下均无偏移。后续事项：test_data.py 中 close!=high 断言恒真宜改或删；data-api.md 的变异检查过程记录宜移到任务卡

- 2026-11-05 10:54:29: 当前代码的配置内检查与所需审查已通过；不代表发布授权。

- 2026-11-05 10:54:29: 完成归档：统一取数 SDK 完成；后续事项见审查记录
