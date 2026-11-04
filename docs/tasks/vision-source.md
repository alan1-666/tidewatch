<!-- workflow-task
{
  "id": "vision-source",
  "goal": "Binance Vision 数据源：按合约与月份下载 USDT-M 永续 1m K 线与资金费率 zip，校验并缓存；列出全部合约（含已下架）",
  "acceptance": [
    "下载的 zip 必须与官方 .CHECKSUM 的 sha256 一致才进入缓存；不一致时报错且不留下缓存文件",
    "已缓存且校验通过的文件不重复下载；不存在的月份（404）报 NotAvailable，与网络错误区分",
    "合约清单跟随 S3 分页取全，包含已下架合约；仅依赖标准库"
  ],
  "allow": [
    "tidewatch/**",
    "tests/**"
  ],
  "profile": "python",
  "phase": "ready",
  "kind": "feature",
  "review_required": true
}
-->
# vision-source

目标：Binance Vision 数据源：按合约与月份下载 USDT-M 永续 1m K 线与资金费率 zip，校验并缓存；列出全部合约（含已下架）

## 验收条件

- 下载的 zip 必须与官方 .CHECKSUM 的 sha256 一致才进入缓存；不一致时报错且不留下缓存文件
- 已缓存且校验通过的文件不重复下载；不存在的月份（404）报 NotAvailable，与网络错误区分
- 合约清单跟随 S3 分页取全，包含已下架合约；仅依赖标准库

- 2026-11-04 15:49:00: 已建立任务；明确事实、未知项和计划后进入 implement。

- 2026-11-04 15:49:00: 已实测：月度 URL /data/futures/um/monthly/{klines/SYM/1m|fundingRate/SYM}/…zip；CHECKSUM 为 "sha256  文件名"；2024 CSV 有表头、2020 无；S3 列表 XML 用 NextMarker 分页。实现：tidewatch/sources/binance_vision.py，fetch 函数可注入以便离线测试。

- 2026-11-04 15:50:32: 验证 passed=True；日志 .workflow/runtime/verify-vision-source-1793778632031430000

- 2026-11-04 15:50:32: 验收 #1 证据：check / pass / test_checksum_mismatch_raises_and_leaves_no_cache：sha256 不符抛 ChecksumMismatch 且缓存目录无文件；test_verified_download_is_cached…：校验通过才落盘。另实测 BTCUSDT 2024-01 K 线与资金费率 zip 均通过官方 CHECKSUM

- 2026-11-04 15:50:32: 验收 #2 证据：check / pass / cached…not_fetched_again：缓存命中零网络调用；corrupted_cache / cache_without_checksum：缓存损坏或缺 CHECKSUM 时重下；missing_month：404→NotAvailable；fetch_maps_only_404：503 仍为 HTTPError。实测 2010-01 返回 NotAvailable，缓存命中 3ms 且注入的 fetch 未被调用

- 2026-11-04 15:50:32: 验收 #3 证据：check / pass / listing_follows_pagination：按 NextMarker 取两页；listing_without_progress：无新 marker 时报错不死循环。实测 list_symbols 返回 1080 个，含已下架 SRMUSDT；模块只 import 标准库

- 2026-11-04 15:53:16: 更正：实现文件为 tidewatch/binance_vision.py（非 sources/ 子包）。只做月度文件，日度暂不做（当月数据需等月度发布，接入层需要时再加）。后续事项：.gitignore 需忽略 data/（不在本任务范围，放到批量接入任务）。审查修复：symbol 白名单 [A-Z0-9_]+ 防路径穿越；缓存文件 0644；无效缓存先清除；marker 必须单调前进。

- 2026-11-04 15:53:17: 验证 passed=True；日志 .workflow/runtime/verify-vision-source-1793778796942135000

- 2026-11-04 15:53:17: 验收 #1 证据：check / pass / checksum_mismatch / bad_redownload_removes_stale_cache / unparseable_checksum：不符或无法解析时抛 ChecksumMismatch，缓存目录无任何文件；实测 BTCUSDT 2024-01 K 线与资金费率通过官方 CHECKSUM

- 2026-11-04 15:53:17: 验收 #2 证据：check / pass / cached…not_fetched_again 零网络；corrupted / without_checksum 重下并重建 CHECKSUM；missing_month 经真实 fetch 的 404→NotAvailable 且无缓存；network_error：URLError 不被映射且无缓存；fetch_maps_only_404：503 仍为 HTTPError

- 2026-11-04 15:53:17: 验收 #3 证据：check / pass / listing_follows_pagination 两页取全；without_progress 与 repeats_or_rewinds 防死循环；实测 1080 个合约（含已下架 SRMUSDT、53 个交割合约），全部符合 symbol 白名单；仅标准库

- 2026-11-04 15:53:58: 更正上一条：symbol 白名单 [A-Z0-9_]+ 会拒绝官方的 5 个中文名合约（龙虾USDT 等），改为 Unicode \w+ 并对 URL 百分号编码；实测龙虾USDT 2026-09 下载校验通过。

- 2026-11-04 15:53:58: 验证 passed=True；日志 .workflow/runtime/verify-vision-source-1793778838139818000

- 2026-11-04 15:53:58: 验收 #1 证据：check / pass / checksum_mismatch / bad_redownload_removes_stale_cache / unparseable_checksum：不符或无法解析时抛 ChecksumMismatch，缓存目录无任何文件；实测 BTCUSDT 2024-01 K 线与资金费率、龙虾USDT 2026-09 K 线均通过官方 CHECKSUM

- 2026-11-04 15:53:58: 验收 #2 证据：check / pass / cached…not_fetched_again 零网络；corrupted / without_checksum 重下并重建 CHECKSUM；missing_month 经真实 fetch 的 404→NotAvailable 且无缓存；network_error：URLError 不被映射且无缓存；fetch_maps_only_404：503 仍为 HTTPError

- 2026-11-04 15:53:58: 验收 #3 证据：check / pass / listing_follows_pagination 两页取全；without_progress 与 repeats_or_rewinds 防死循环；实测 1080 个合约（含已下架 SRMUSDT、交割合约、5 个中文名合约）全部通过 \w+ 白名单；仅标准库

- 2026-11-04 15:55:02: 审查记录：claude-subagent:general-purpose(read-only) / pass / 两轮只读审查：首轮因 symbol 路径穿越判 fail；修复后复查 pass。\w+ 经全码点 NFC/NFD 扫描不会产生分隔符或 ..；quote 只用于 URL；23 passed。遗留：macOS 大小写不敏感，btcusdt 会命中 BTCUSDT 缓存——由合约注册表校验 symbol 在官方清单中

- 2026-11-04 15:55:02: 当前代码的配置内检查与所需审查已通过；不代表发布授权。

- 2026-11-04 15:55:02: 完成归档：Binance Vision 源完成。后续：合约注册表校验 symbol 属于官方清单（大小写）；批量接入任务把 data/ 加入 .gitignore
