<!-- workflow-task
{
  "id": "snapshot",
  "goal": "研究输入可复现：声明历史回放假设，提供内容寻址的数据快照与不可变实验清单",
  "acceptance": [
    "time-conventions 新增历史回放假设：Binance Vision 归档数据没有可用时间，统一假设 bar 在 close_ts 可见、滞后 lag 根成交，研究结论只在该假设下成立",
    "snapshot.save 把 DataFrame 写成以文件 sha256 命名的 parquet，原子写入，同名已存在时不覆盖；snapshot.load 校验哈希，不一致或不存在时报错",
    "snapshot.record_experiment 写入实验清单（快照 id、因子或规则定义、时间策略、成交假设、全部尝试记录），id 为清单内容哈希；快照不存在、缺字段或尝试记录为空时报错；修订任一字段得到新 id，旧清单不变",
    "docs/specs/snapshot.md 记录上述规则与对应测试，architecture 模块表加入快照与实验清单"
  ],
  "allow": [
    "tidewatch/**",
    "tests/**",
    "docs/specs/*.md",
    "docs/design/*.md"
  ],
  "profile": "python",
  "phase": "ready",
  "kind": "feature",
  "review_required": true
}
-->
# snapshot

目标：研究输入可复现：声明历史回放假设，提供内容寻址的数据快照与不可变实验清单

## 验收条件

- time-conventions 新增历史回放假设：Binance Vision 归档数据没有可用时间，统一假设 bar 在 close_ts 可见、滞后 lag 根成交，研究结论只在该假设下成立
- snapshot.save 把 DataFrame 写成以文件 sha256 命名的 parquet，原子写入，同名已存在时不覆盖；snapshot.load 校验哈希，不一致或不存在时报错
- snapshot.record_experiment 写入实验清单（快照 id、因子或规则定义、时间策略、成交假设、全部尝试记录），id 为清单内容哈希；快照不存在、缺字段或尝试记录为空时报错；修订任一字段得到新 id，旧清单不变
- docs/specs/snapshot.md 记录上述规则与对应测试，architecture 模块表加入快照与实验清单

- 2026-11-05 15:48:21: 已建立任务；明确事实、未知项和计划后进入 implement。

- 2026-11-05 15:48:22: 快照放 root/snapshots/<sha256>.parquet，清单放 root/experiments/<sha256>.json；root 由调用方（将来的 CLI）传入。不改 ClickHouse 版本机制：快照即固定输入。无新依赖（polars 自带 parquet 读写）。

- 2026-11-05 15:49:34: 验证 passed=True；日志 .workflow/runtime/verify-snapshot-1793864974212929000

- 2026-11-05 15:49:51: 验收 #1 证据：manual / pass / 人工核对：time-conventions.md 新增'历史回放假设'节，写明 Binance Vision 只有事件时间、bar 在 close_ts 可见、延迟由 lag≥1 吸收、结论仅在该假设下成立；属声明，无专门测试

- 2026-11-05 15:49:56: 验收 #2 证据：check / pass / test_snapshot_round_trips_and_is_content_addressed（同内容同 id、补数新 id、旧快照可读、UTC 类型保留）、test_existing_snapshot_is_not_overwritten、test_snapshot_load_rejects_tampered_missing_or_bad_id（篡改/不存在/../x/大写/截短）

- 2026-11-05 15:49:57: 验收 #3 证据：check / pass / test_experiment_manifest_is_immutable_and_revisions_get_new_ids（键序无关、换快照/改费用得新 id、旧清单原样）、test_experiment_manifest_rejects_incomplete_input（逐个缺字段、trials 空或非列表、快照不存在、清单被改读取报错、无临时文件残留）

- 2026-11-05 15:49:57: 验收 #4 证据：manual / pass / 人工核对：docs/specs/snapshot.md 三条需求均列测试名与已知限制；architecture 模块表与分层图加入快照与实验清单，并修正取数 SDK 行的规格链接

- 2026-11-05 15:52:25: 审查记录：general-purpose 子 Agent（只读） / fail / 第 1 轮 changes-requested：M1 '失败写入不留临时文件'与原子写入无测试，证据不实；L1 与 binance_vision._atomic_write 重复且 fchmod 在 try 外；L2 NaN 写成非标准 JSON；L3 规格未写 5/5.0、tuple、非字符串键等限制；L4 已存在文件不校验即返回；L5 并发 TOCTOU（内容相同，接受）；回放假设一句重复、'官方事后修订'未注来源

- 2026-11-05 15:52:33: 验证 passed=True；日志 .workflow/runtime/verify-snapshot-1793865153331321000

- 2026-11-05 15:52:34: 验收 #1 证据：manual / pass / 人工核对：time-conventions.md'历史回放假设'节：只有事件时间、官方可能重发月度文件（引 clickhouse-store 已知限制）、bar 在 close_ts 可见、延迟由 lag≥1 吸收并引用'标签滞后成交'、结论仅在该假设下成立；属声明，无专门测试

- 2026-11-05 15:52:34: 验收 #2 证据：check / pass / test_snapshot_round_trips_and_is_content_addressed；test_existing_snapshot_is_not_overwritten_and_is_verified（同名坏文件 save 报错且不改写）；test_failed_write_leaves_nothing_behind（os.replace 注入失败，目录为空）；test_snapshot_load_rejects_tampered_missing_or_bad_id。原子写入复用 binance_vision._atomic_write

- 2026-11-05 15:52:34: 验收 #3 证据：check / pass / test_experiment_manifest_is_immutable_and_revisions_get_new_ids（键序无关、换快照/改费用得新 id、旧清单原样）；test_experiment_manifest_rejects_incomplete_input（逐个缺字段、trials 空或非列表、NaN、快照不存在、清单被改读取报错）；引用坏快照报错见 test_existing_snapshot_is_not_overwritten_and_is_verified

- 2026-11-05 15:52:34: 验收 #4 证据：manual / pass / 人工核对：docs/specs/snapshot.md 三条需求列测试名，已知限制补充 JSON 语义（5/5.0、tuple、非字符串键）与并发同 id；architecture 模块表与分层图加入快照与实验清单

- 2026-11-05 15:53:29: 审查记录：general-purpose 子 Agent（只读） / pass / 第 2 轮 pass：M1 已解决（删清理、非原子直写两种变异均被 test_failed_write_leaves_nothing_behind 抓到）；L4、L2 修改各有变异被测试抓到；规格与回放假设一致。后续事项（low，不触发复审）：snapshot 导入 binance_vision 私有的 _atomic_write，architecture 依赖栏仍写'—'，将来提到公共小模块或在依赖栏注明

- 2026-11-05 15:53:29: 当前代码的配置内检查与所需审查已通过；不代表发布授权。

- 2026-11-05 15:53:33: 完成归档：快照与实验清单完成：回放假设已声明；save/load 内容寻址、原子写、哈希校验；record_experiment 不可变并要求全部尝试。两轮审查 pass。后续：_atomic_write 私有导入（见审查记录）
