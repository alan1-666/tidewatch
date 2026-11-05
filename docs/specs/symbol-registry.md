# 合约注册表

模块：`tidewatch/registry.py`。按 Binance Vision 目录记录每个合约的计价币、合约类型、首末月份和下架状态。目录里保留了已下架合约，所以能避免幸存者偏差。

状态：已实现（任务 symbol-registry-v2）。

## 需求

### 识别计价币与合约类型

计价币取 USDT、USDC、BUSD 之一，无法识别时为空。合约类型分三种：

- `settled`：结算后改名的合约，名字末尾带 `SETTLED` 或 `_SETTLED`（可能重复），先去掉后缀再识别计价币。
- `delivery`：交割合约，形如 `BTCUSDT_240329`。
- `perpetual`：其余合约。

截至 2026-11，以下 6 个识别不出计价币：BTCU、ETHU、BTCUSD1、ETHUSD1、SPCXUSD1、ETHBTC。

- 场景：`ICPUSDT_SETTLED` 与 `AERGOUSDTSETTLEDSETTLED` 识别为 `(USDT, settled)`，`BTCUSDT_240329` 为 `(USDT, delivery)`，`龙虾USDT` 为 `(USDT, perpetual)`。
- 测试：`test_classify`

### 首末月份与下架

首末月份取自实际存在的月度 K 线文件，没有任何文件的合约不进表。最新月份取全体合约末月的最大值。末月早于"最新月份减一个月"才标记为下架，这一个月的宽限用来容忍月初上月文件陆续发布，跨年同样适用。交割合约到期也算下架。

- 场景：最新为 2026-10 时，末月 2026-09 不算下架，2026-08 算下架。
- 场景：最新为 2027-01 时，2026-12 不算下架，2026-11 算下架。
- 测试：`test_build_rows_marks_delisted_with_one_month_grace_and_skips_symbols_without_files`

### 可重复刷新，入口拦截错误合约名

`refresh` 并发列举后一次写入；任一请求失败，整次刷新失败，不会写入一半（由实现顺序保证，未单测）。`FINAL` 下每个合约一行。`require_known` 区分大小写，遇到不存在的合约报 `ValueError`，传入字符串而不是列表时报 `TypeError`。

- 场景：刷新两次，每个合约仍只有一行；`btcusdt`、`NOPEUSDT` 被拒绝。
- 测试：`test_refresh_is_repeatable_and_require_known_is_case_sensitive`

## 已知限制

- 月中新上市的合约，在首个月度文件发布前不在注册表中，`require_known` 会拒绝它。
- 官方文件可能在合约下架后继续发布一段时间（例如 SRMUSDT 2022 年下架，文件一直延续到 2024-05），所以末月可能晚于真实停止交易的时间。
- 全量刷新约 1100 次只读请求，用时 1.5～2.5 分钟，没有重试。
