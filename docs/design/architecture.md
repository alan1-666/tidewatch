# tidewatch 架构（MVP）

加密货币 USDT 永续合约的因子研究平台。目标是把"取数 → 因子 → 标签 → 评测/回测 → 报告"这条链路做对，尤其是不用到未来数据。

## 分层

上层只调用下层。I/O 只出现在 ClickHouse 存储、Binance Vision 源、快照与实验清单、批量接入、合约注册表和取数 SDK；因子、标签、成本、评测、回测是传值进、返回值出的纯函数，不碰网络和数据库，可以只用小 DataFrame 测试。配置只由 CLI 读取，并以参数形式逐层传下去。

```
③ 编排        CLI / 流水线（唯一读取配置的地方）
② 上下文/呈现  可交易集合            研究报告
① 算子        批量接入  合约注册表  统一取数 SDK │ 因子评测  向量化回测
⓪ 基础原语    ClickHouse 存储  Binance Vision 源  快照与实验清单 │ 因子注册  未来收益标签  成本模型
```

| 模块 | 依赖 | 职责 | 规格 |
|---|---|---|---|
| ClickHouse 存储 | — | `klines_1m`、`funding_rate`、`symbols` 表结构；单节点见 `docker-compose.yml` | [clickhouse-store](../specs/clickhouse-store.md) |
| Binance Vision 源 | — | 下载并校验月度 zip，缓存到 `data/raw/`；列举合约与月份 | [binance-vision](../specs/binance-vision.md) |
| 因子注册 | — | `@factor(name, freq, lookback)` 修饰纯函数 `f(bars) -> (ts, symbol, value)` | [time-conventions](../specs/time-conventions.md)（待实现） |
| 未来收益标签 | — | `forward_return(bars, horizon, lag=1)` | [time-conventions](../specs/time-conventions.md)（待实现） |
| 成本模型 | — | 手续费（默认 taker 5bp）、滑点（先用固定 bp）、资金费率计费 | [time-conventions](../specs/time-conventions.md)（待实现） |
| 批量接入 | 源、存储 | 解析月度 zip 并幂等写入 | [ingest](../specs/ingest.md) |
| 合约注册表 | 源、存储 | 计价币、合约类型、首末月份、下架 | [symbol-registry](../specs/symbol-registry.md) |
| 统一取数 SDK | 存储 | `get_bars(symbols, freq, start, end)`、`get_funding(...)`：1m 聚合，返回 polars 长表 | [data-api](../specs/data-api.md) |
| 快照与实验清单 | — | 研究输入存为内容寻址的 parquet；实验清单记录快照、定义、时间策略、成交假设与全部尝试 | [snapshot](../specs/snapshot.md) |
| 因子评测 | 因子注册、标签 | 截面 IC / RankIC 与 IR、分位分层收益、因子换手 | 待实现 |
| 向量化回测 | 成本模型、标签 | 信号 → 多空中性权重 → 滞后成交 → 扣费用 → 净值与换手 | 待实现 |
| 可交易集合 | 取数 SDK、合约注册表 | `universe_at(ts)`：按过去 N 天成交额取前 K | [time-conventions](../specs/time-conventions.md)（待实现） |
| 研究报告 | 评测、回测结果 | 静态 HTML / notebook | 待实现 |
| CLI | 以上 | `tidewatch ingest / eval / backtest`；读取配置并逐层传值 | 待实现 |

## 时点约定（不变量）

防止使用未来数据的规则统一写在 [docs/specs/time-conventions.md](../specs/time-conventions.md)，这里不重复。要点：

- 所有模块之间唯一的 join 键是 `(ts, symbol)`，`ts` 为 bar 开盘时刻。
- 因子只用 `ts ≤ t` 的数据；标签与回测滞后 `lag ≥ 1` 根 bar 成交；可交易集合只用 `ts < t` 的数据；资金费率按持仓区间左开右闭计费。
- 不跨官方数据缺口计算收益。

## 数据口径

- 标的：币安 USDT 永续，按成交额取前 50～100。
- 只存 1 分钟线与资金费率；5m / 1h / 1d 在查询时聚合。日线按 UTC 0 点切分。
- 时间统一为 UTC 毫秒，bar 的 `ts` 是开盘时刻，收盘时刻为 `ts + freq`。
- 资金费率保留官方 `calc_time`，`ts` 由库四舍五入到秒（见 [clickhouse-store.md](../specs/clickhouse-store.md)）。
- 官方数据可能整段缺失（如 2026-10-28），接入不补值。
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
