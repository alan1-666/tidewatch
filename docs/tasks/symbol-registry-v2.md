<!-- workflow-task
{
  "id": "symbol-registry-v2",
  "goal": "合约注册表（v2，接续 symbol-registry）：列举全部合约及首末月份，分类并标记下架，写入 symbols 表",
  "acceptance": [
    "按合约列举月度 K 线文件（跟随分页，含无 NextMarker 的回退分页，支持中文合约名），得到升序的 (年, 月) 列表",
    "分类出计价币与 perpetual/delivery/settled：*SETTLED 后缀（可重复）去掉后识别计价币；无法识别时计价币为空并在卡片列明",
    "末月早于\"全体最新月份减一个月\"才标记已下架（容忍月初文件陆续发布；交割到期也算下架）；无文件的合约不入表",
    "symbols 表可重复刷新且 FINAL 下每个合约一行；require_known 对大小写不符、不存在的合约或传入字符串而非列表时报错"
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
# symbol-registry-v2

目标：合约注册表（v2，接续 symbol-registry）：列举全部合约及首末月份，分类并标记下架，写入 symbols 表

## 验收条件

- 按合约列举月度 K 线文件（跟随分页，含无 NextMarker 的回退分页，支持中文合约名），得到升序的 (年, 月) 列表
- 分类出计价币与 perpetual/delivery/settled：*SETTLED 后缀（可重复）去掉后识别计价币；无法识别时计价币为空并在卡片列明
- 末月早于"全体最新月份减一个月"才标记已下架（容忍月初文件陆续发布；交割到期也算下架）；无文件的合约不入表
- symbols 表可重复刷新且 FINAL 下每个合约一行；require_known 对大小写不符、不存在的合约或传入字符串而非列表时报错

- 2026-11-04 16:24:20: 已建立任务；明确事实、未知项和计划后进入 implement。

- 2026-11-04 16:24:21: 接续 symbol-registry 的工作区改动。新增：delisted 一个月宽限；classify 处理 SETTLED；list_months 无 NextMarker 分页测试；require_known 拒绝字符串参数。已知限制：月中新上市合约在其首个月度文件发布前不在注册表中，require_known 会拒绝；无法识别计价币的为 BTCU、ETHU、BTCUSD1、ETHUSD1、SPCXUSD1、ETHBTC 等。

- 2026-11-04 16:24:59: 验证 passed=True；日志 .workflow/runtime/verify-symbol-registry-v2-1793780698887860000

- 2026-11-04 16:25:00: 验收 #1 证据：check / pass / test_list_months_paginates_without_next_marker：无 NextMarker 时以本页最大 key 续页；test_list_months_follows_pagination…：中文合约 3 页、忽略 .CHECKSUM、URL 均 ASCII；实测 龙虾USDT 2026-03~2026-10

- 2026-11-04 16:25:00: 验收 #2 证据：check / pass / test_classify 11 例：交割、BUSD、中文、BNXUSDTSETTLED 与 AERGOUSDTSETTLEDSETTLED→(USDT, settled)、BTCUSD1/ETHBTC/BTCDOM/USDT→计价 None；无法识别清单见任务卡

- 2026-11-04 16:25:00: 验收 #3 证据：check / pass / test_build_rows_marks_delisted_with_one_month_grace…：最新 2026-10 时末月 2026-09 不下架、2026-08 下架；跨年 2027-01 时 2026-12 不下架、2026-11 下架；无文件合约不入表

- 2026-11-04 16:25:00: 验收 #4 证据：check / pass / test_refresh_is_repeatable_and_require_known_is_case_sensitive：刷新两次 FINAL 每合约一行；末月早于宽限的 SRMUSDT 下架、交割合约在宽限内未下架；btcusdt、NOPEUSDT 报 ValueError，传字符串报 TypeError

- 2026-11-04 16:26:11: 验证 passed=True；日志 .workflow/runtime/verify-symbol-registry-v2-1793780770442467000

- 2026-11-04 16:26:11: 验收 #1 证据：check / pass / test_list_months_paginates_without_next_marker：无 NextMarker 时以本页最大 key 续页；test_list_months_follows_pagination…：中文合约 3 页、忽略 .CHECKSUM、URL 均 ASCII

- 2026-11-04 16:26:11: 验收 #2 证据：check / pass / test_classify 12 例含 BNXUSDTSETTLED、AERGOUSDTSETTLEDSETTLED、ICPUSDT_SETTLED→(USDT, settled)；实测全量 1080 个分类：USDT 永续 923、USDT 交割 50、BUSD 永续 41、USDC 永续 40、USDT settled 18、BUSD 交割 2、计价 None 6（BTCU、BTCUSD1、ETHBTC、ETHU、ETHUSD1、SPCXUSD1）

- 2026-11-04 16:26:11: 验收 #3 证据：check / pass / test_build_rows_marks_delisted_with_one_month_grace…：最新 2026-10 时末月 2026-09 不下架、2026-08 下架；跨年 2027-01 时 2026-12 不下架、2026-11 下架；无文件合约不入表

- 2026-11-04 16:26:11: 验收 #4 证据：check / pass / test_refresh_is_repeatable_and_require_known_is_case_sensitive：刷新两次 FINAL 每合约一行；btcusdt、NOPEUSDT 报 ValueError，传字符串报 TypeError

- 2026-11-04 16:27:01: 审查记录：claude-subagent:general-purpose(read-only) / pass / 接续 symbol-registry 的审查（月初误判、SETTLED 识别、无 NextMarker 分页）后两轮复查：一个月宽限含跨年正确；ICPUSDT_SETTLED 等 18 个 settled 正确分类；真实清单分类计数核对一致

- 2026-11-04 16:27:01: 当前代码的配置内检查与所需审查已通过；不代表发布授权。

- 2026-11-04 16:27:01: 完成归档：合约注册表完成（v2）
