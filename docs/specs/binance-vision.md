# Binance Vision 数据源

模块：`tidewatch/binance_vision.py`。从 data.binance.vision 下载 USDT-M 合约的月度文件并缓存，列举合约与月份。只做网络与文件 IO，只依赖标准库。

状态：已实现（任务 vision-source，symbol-registry-v2 增加 `list_months`）。

## 需求

### 路径与官方布局一致

K 线固定取 1m：`data/futures/um/monthly/klines/{SYM}/1m/{SYM}-1m-{YYYY}-{MM}.zip`。资金费率：`data/futures/um/monthly/fundingRate/{SYM}/{SYM}-fundingRate-{YYYY}-{MM}.zip`。本地缓存沿用同一相对路径。其他数据类型报 `ValueError`。

- 测试：`test_paths_match_official_layout`

### 只缓存通过官方校验的文件

下载的 zip 必须与官方 `.CHECKSUM` 的 sha256 一致才写入缓存，缓存内同时保存 zip 与其 CHECKSUM。CHECKSUM 不符或无法解析时报 `ChecksumMismatch`，并且不留下任何缓存文件，包括之前已损坏的旧文件。

- 场景：sha256 不符时抛错，缓存目录中没有文件。
- 场景：缓存 zip 被截断，或缺少 CHECKSUM 文件时，重新下载。
- 测试：`test_checksum_mismatch_raises_and_leaves_no_cache`、`test_bad_redownload_removes_stale_cache`、`test_unparseable_checksum_is_rejected`、`test_corrupted_cache_is_downloaded_again`、`test_cache_without_checksum_file_is_not_trusted`

### 缓存命中不访问网络；缺失与故障分开

zip 与 CHECKSUM 一致时直接返回，不发请求。只有 HTTP 404 映射为 `NotAvailable`（该月份无文件）；其他 HTTP 错误、网络错误和超时原样抛出。缓存文件权限为 0644。

- 场景：第二次下载同一月份，注入的 fetch 没有被调用。
- 场景：503 仍是 `HTTPError`；`URLError` 不被当作 `NotAvailable`。
- 测试：`test_verified_download_is_cached_and_not_fetched_again`、`test_missing_month_is_not_available`、`test_fetch_maps_only_404_to_not_available`、`test_network_error_is_not_not_available_and_leaves_no_cache`、`test_funding_rate_goes_through_same_verified_flow`

### 合约名不能逃出缓存目录

合约名只允许 Unicode 字母、数字和下划线（`\w+`）。官方确有中文名合约，如 `龙虾USDT`，以及带下划线的交割合约。`/`、`.`、`-` 和空串一律拒绝。本地路径保留原名，请求 URL 做百分号编码。

- 场景：`../../etc/x`、`BTC/USDT`、`..` 报 `ValueError`，且不产生任何文件。
- 场景：`龙虾USDT` 能缓存，所有请求 URL 都是 ASCII。
- 测试：`test_symbol_cannot_escape_cache_dir`、`test_non_ascii_symbol_is_cached_and_url_is_percent_encoded`

### 清单跟随分页取全

`list_symbols` 列出全部合约，包括已下架、交割、settled 和中文名合约，不做筛选。`list_months(symbol)` 返回该合约已发布月度 1m K 线的升序 `(年, 月)`。分页优先用 NextMarker，没有时以本页最大的 key 续页。marker 必须严格前进，否则报错，避免死循环。

- 场景：两页清单合并；返回重复 NextMarker 时报错。
- 场景：不带 delimiter 列举时没有 NextMarker，仍能取全。
- 测试：`test_listing_follows_pagination`、`test_listing_without_progress_fails_instead_of_looping`、`test_listing_that_repeats_or_rewinds_marker_fails`、`test_list_months_paginates_without_next_marker`、`test_list_months_follows_pagination_and_ignores_other_keys`

## 已知限制

- 只取月度文件，当月数据要等官方月度发布。日度文件暂不支持。
- 多个进程并发导入同一个月份时，缓存可能互相删除对方刚写的文件，重跑即可恢复。
- macOS 文件系统不区分大小写：`btcusdt` 会命中 `BTCUSDT` 的缓存。入口由合约注册表的 `require_known` 拦截。
