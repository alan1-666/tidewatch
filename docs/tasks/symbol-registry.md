<!-- workflow-task
{
  "id": "symbol-registry",
  "goal": "合约注册表：从 Binance Vision 目录列举全部合约及其有数据的首末月份，分类并标记下架，写入 symbols 表",
  "acceptance": [
    "按合约列举月度 K 线文件（跟随分页，支持中文合约名），得到升序的 (年, 月) 列表",
    "分类出计价币与永续/交割；首末月份来自实际文件；末月早于全体最新月份的合约标记为已下架；无文件的合约不入表",
    "symbols 表可重复刷新且 FINAL 下每个合约一行；require_known 对大小写不符或不存在的合约报错"
  ],
  "allow": [
    "tidewatch/**",
    "tests/**"
  ],
  "profile": "integration",
  "phase": "verify",
  "kind": "feature",
  "review_required": true
}
-->
# symbol-registry

目标：合约注册表：从 Binance Vision 目录列举全部合约及其有数据的首末月份，分类并标记下架，写入 symbols 表

## 验收条件

- 按合约列举月度 K 线文件（跟随分页，支持中文合约名），得到升序的 (年, 月) 列表
- 分类出计价币与永续/交割；首末月份来自实际文件；末月早于全体最新月份的合约标记为已下架；无文件的合约不入表
- symbols 表可重复刷新且 FINAL 下每个合约一行；require_known 对大小写不符或不存在的合约报错

- 2026-11-04 16:18:26: 已建立任务；明确事实、未知项和计划后进入 implement。

- 2026-11-04 16:18:26: 在 binance_vision 抽出 _s3_list 共用分页，新增 list_months；store 增加 symbols 表（ReplacingMergeTree(refreshed_at) ORDER BY symbol）；新增 tidewatch/registry.py：classify、build_rows、refresh（16 线程并发列举）、require_known。

- 2026-11-04 16:22:07: 实测刷新 1080 个合约用时 144s：USDT 永续 923（31 个已下架）、USDT 交割 51、BUSD 永续 41、USDC 永续 40、无法识别计价 23。LUNAUSDT 末月 2022-05 已下架；SRMUSDT 2022 年下架但文件延续到 2024-05——末月可能晚于真实停止交易，可交易集合须按实际成交额筛选（记给 universe 任务）。

- 2026-11-04 16:22:08: 验证 passed=True；日志 .workflow/runtime/verify-symbol-registry-1793780527521039000

- 2026-11-04 16:22:08: 验收 #1 证据：check / pass / test_list_months_follows_pagination_and_ignores_other_keys：中文合约 龙虾USDT、6 个 key 分 3 页、忽略 .CHECKSUM，得到升序 (年,月)，所有请求 URL 为 ASCII；实测 龙虾USDT 2026-03 至 2026-10

- 2026-11-04 16:22:08: 验收 #2 证据：check / pass / test_classify（7 例含交割、BUSD、中文、无法识别）；test_build_rows_marks_delisted_and_skips_symbols_without_files；实测 LUNAUSDT 末月 2022-05 标记下架、BTCUSDT 2020-01~2026-10 未下架

- 2026-11-04 16:22:08: 验收 #3 证据：check / pass / test_refresh_is_repeatable_and_require_known_is_case_sensitive：刷新两次 FINAL 每合约一行；btcusdt 与 NOPEUSDT 均报错，已知合约通过；test_schema 增加 symbols 表结构断言

- 2026-11-04 16:24:20: 未完成归档：审查发现验收 #2 的下架定义在月初发布窗口会误判，且 *USDTSETTLED 合约计价币识别失败；验收语义需变更，按规则归档并以 symbol-registry-v2 重建。代码保留在工作区继续修改。
