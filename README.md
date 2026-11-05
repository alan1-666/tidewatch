# tidewatch

加密货币量化研究平台：行情接入 → 多粒度行情库 → 因子挖掘 → 因子层 → 回测 → 绩效看板。

## MVP 范围

- 标的：币安 USDT 永续合约，按成交额取前 50～100，已下架合约保留（避免幸存者偏差）
- 数据：data.binance.vision 历史批量数据；只存 1 分钟线与资金费率，其他粒度在 ClickHouse 聚合；日线按 UTC 0 点切分
- 因子：注册 + IC/RankIC + 分层收益
- 回测：向量化，计入手续费与资金费率
- 看板：先用 notebook 出图

暂不做：L2 订单簿、秒级、实时流、LLM/遗传算法挖掘、Web 看板。

分层与模块职责见 [docs/design/architecture.md](docs/design/architecture.md)；各模块的行为规则（需求、场景、对应测试）见 [docs/specs/](docs/specs/)，时点约定在 [time-conventions.md](docs/specs/time-conventions.md)。

## 本地环境

```sh
uv sync                 # 建立 .venv
docker compose up -d    # 本地 ClickHouse，仅集成测试与数据导入需要
```

## 开发工作流

Codex 与 Claude Code 共用 `AGENTS.md` 规则，工作流来自 [coding-workflow](https://github.com/alan1-666/coding-workflow)，检查器修改先在那边回归再同步过来。

```sh
python3 scripts/workflow/workflow.py doctor
python3 scripts/workflow/workflow.py status
```

实现任务用 `start <id> --profile python|integration ...` 建卡，`verify` 先跑工作流自检，再跑所选 profile：`python` 是不需要 ClickHouse 的 pytest，`integration` 先跑同样的单元测试，再跑标记为 integration 的测试。运行环境：macOS/Linux，Python 3.12+、uv、Git，集成测试另需 Docker。

首次在本目录打开 Codex / Claude Code 时，需要在客户端里确认信任项目 Hooks；信任不会从 coding-workflow 继承。
