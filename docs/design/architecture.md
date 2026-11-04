# tidewatch 架构（MVP）

加密货币 USDT 永续合约的因子研究平台。目标是把"取数 → 因子 → 标签 → 评测/回测 → 报告"这条链路做对，尤其是不用到未来数据。

## 分层

上层只调用下层。I/O 只出现在 ClickHouse 存储、Binance Vision 源、批量接入、合约注册表和取数 SDK；因子、标签、成本、评测、回测是传值进、返回值出的纯函数，不碰网络和数据库，可以只用小 DataFrame 测试。配置只由 CLI 读取，并以参数形式逐层传下去。

```
③ 编排        CLI / 流水线（唯一读取配置的地方）
② 上下文/呈现  可交易集合            研究报告
① 算子        批量接入  合约注册表  统一取数 SDK │ 因子评测  向量化回测
⓪ 基础原语    ClickHouse 存储  Binance Vision 源 │ 因子注册  未来收益标签  成本模型
```

| 模块 | 依赖 | 职责与约定 |
|---|---|---|
| ClickHouse 存储 | — | 单节点（`docker-compose.yml`）。`klines_1m`、`funding_rate` 用 `ReplacingMergeTree`，按月分区，`ORDER BY (symbol, ts)`，重复导入幂等。只提供执行、写入、查询，不含业务逻辑 |
| Binance Vision 源 | — | 从 data.binance.vision 下载 USDT-M 永续的月/日 zip（1m K 线、资金费率），校验 `.CHECKSUM`，缓存到 `data/raw/`（不进 git）。另提供目录清单，含已下架合约 |
| 因子注册 | — | `@factor(name, freq, lookback)` 修饰纯函数 `f(bars) -> (ts, symbol, value)`，`ts` 与输入 bar 的 `ts` 相同（见时点约定） |
| 未来收益标签 | — | `forward_return(bars, horizon, lag=1)`，键为 `(ts, symbol)`，`lag ≥ 1`；可选扣资金费率 |
| 成本模型 | — | 手续费（默认 taker 5bp）、滑点（固定 bp 起步）；资金费率按 `funding_rate` 表中的实际结算时间戳对持仓计费，不假设固定间隔（币安部分合约是 4h 或 1h，且会调整） |
| 批量接入 | 源、存储 | 解析 zip CSV（兼容有无表头的历史格式），统一为 UTC 毫秒时间戳，按（合约, 月）可重跑 |
| 合约注册表 | 源、存储 | `symbols` 表：合约、首末数据日期、是否已下架 |
| 统一取数 SDK | 存储 | `get_bars(symbols, freq, start, end)`、`get_funding(...)`；在 ClickHouse 内由 1m 聚合，日线按 UTC 0 点切；返回 polars 长表 |
| 因子评测 | 因子注册、标签 | 截面 IC / RankIC 与 IR、分位分层收益、因子换手 |
| 向量化回测 | 成本模型、标签 | 信号 → 截面 rank 多空中性权重 → 滞后 `lag`（默认 1）根 bar、按 `close(t + lag)` 成交 → 扣费用 → 净值与换手 |
| 可交易集合 | 取数 SDK、合约注册表 | `universe_at(ts)`：按过去 N 天成交额取前 K，含之后会下架的合约 |
| 研究报告 | 评测、回测结果 | 静态 HTML / notebook：净值、IC 序列、分层收益、换手、费后收益 |
| CLI | 以上 | `tidewatch ingest / eval / backtest`；读取配置并逐层传值 |

## 时点约定（不变量）

下面四条是防止未来数据的核心，相关改动必须有对应的不变量测试（见 AGENTS.md）：

所有模块之间唯一的 join 键是 `(ts, symbol)`，`ts` 是 bar 的**开盘时刻**；记 `close(t)` 为 `ts = t` 那根 bar 的收盘**价**，`close_ts(t) = t + freq` 为它的收盘**时刻**，`t + k` 表示往后第 k 根 bar。

1. **因子时间戳**：键为 `t` 的因子值只能用 `ts ≤ t` 的 bar，即在 `t` 这根 bar 收盘时才可知。因子输出沿用 bar 的 `ts`，不另改成收盘时刻。
2. **滞后成交**：键为 `t` 的标签 = `close(t + lag + horizon) / close(t + lag) - 1`，`lag ≥ 1`（默认 1）。即信号在 `t` 收盘时产生，最早按 `t + lag` 的收盘价成交，不用 `t` 本身的价格。回测用同一定义。
3. **可交易集合**：键为 `t` 的集合只用 `ts < t` 的数据决定，且历史上存在、之后下架的合约必须包含在内。这里有意比因子少用一根 bar：集合在 `t` 开盘前就已确定，不随当根 bar 变化。
4. **资金费率区间**：持仓区间按左开右闭计费，即结算时间戳落在 `(close_ts(t + lag), close_ts(t + lag + horizon)]` 内的资金费率计入，开仓时刻的那次不算，平仓时刻的那次算。标签扣资金费率和回测计费用同一规则。

因子、标签、可交易集合按 `(ts, symbol)` 直接 join，不做任何平移。每条约定对应一个不变量测试，在 `ts = s` 构造一根价格或成交额突变的 bar：

- 因子：键 `t < s` 的因子值不变。
- 标签：`close(s)` 只影响键 `t ∈ [s - lag - horizon, s - lag]` 的标签；键 `t > s - lag` 的标签不变。
- 可交易集合：`universe_at(s)` 不变，只有 `s` 之后的集合可能变化；另断言之后会下架的合约出现在下架前的集合里。
- 资金费率：结算时间戳恰好等于开仓时刻的不计入，恰好等于平仓时刻的计入。

## 数据口径

- 标的：币安 USDT 永续，按成交额取前 50～100。
- 只存 1 分钟线与资金费率；5m / 1h / 1d 在查询时聚合。日线按 UTC 0 点切分。
- 时间统一为 UTC 毫秒，bar 的 `ts` 是开盘时刻，收盘时刻为 `ts + freq`。
- 原始 zip 缓存在 `data/raw/`，ClickHouse 可随时从缓存重建。

## 开发与验证

- 环境：`uv sync` 建立 `.venv`；本地 ClickHouse 用 `docker compose up -d`。
- `python` profile：`pytest -m "not integration"`，纯函数单元测试，不需要 ClickHouse。
- `integration` profile：先跑上面的单元测试，再跑 `pytest -m integration`，需要本地 ClickHouse。涉及数据库的任务用它。

## 开发顺序

1. 开发环境（本文档所在任务）
2. ClickHouse 存储 + Binance Vision 源
3. 批量接入 + 合约注册表：先导入 10 个合约、3 个月数据跑通（检查点）
4. 统一取数 SDK
5. 因子注册、标签、成本模型 → 因子评测、向量化回测 → 可交易集合 → 研究报告 → CLI

## 暂不做

L2 订单簿、秒级数据、实时流、LLM / 遗传算法因子挖掘、Web 看板、逐笔事件驱动回测。它们将来作为新模块挂在现有层之上，不改变上述时点约定。
