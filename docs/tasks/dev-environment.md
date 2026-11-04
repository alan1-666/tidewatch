<!-- workflow-task
{
  "id": "dev-environment",
  "goal": "建立 uv 项目、pytest 验证、本地 ClickHouse 与设计文档位置，为数据层开发做准备",
  "acceptance": [
    "uv sync 建立 .venv 并锁定依赖；python profile 用 .venv 中的 pytest 运行且排除集成测试，不需要 ClickHouse 即可通过",
    "新增 integration profile 只运行标记为 integration 的测试；docker compose 启动的本地 ClickHouse 能通过连通性测试",
    "policy 允许 docs/design/*.md，架构设计写入 docs/design/architecture.md，README 与 AGENTS 指向它"
  ],
  "allow": [
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".gitignore",
    "docker-compose.yml",
    ".workflow/**",
    "docs/design/**",
    "AGENTS.md",
    "README.md",
    "tests/**",
    "tidewatch/**"
  ],
  "profile": "python",
  "phase": "ready",
  "kind": "maintenance",
  "review_required": true
}
-->
# dev-environment

目标：建立 uv 项目、pytest 验证、本地 ClickHouse 与设计文档位置，为数据层开发做准备

## 验收条件

- uv sync 建立 .venv 并锁定依赖；python profile 用 .venv 中的 pytest 运行且排除集成测试，不需要 ClickHouse 即可通过
- 新增 integration profile 只运行标记为 integration 的测试；docker compose 启动的本地 ClickHouse 能通过连通性测试
- policy 允许 docs/design/*.md，架构设计写入 docs/design/architecture.md，README 与 AGENTS 指向它

- 2026-11-04 15:20:25: 已建立任务；明确事实、未知项和计划后进入 implement。

- 2026-11-04 15:20:25: 计划：uv init 风格的 pyproject（依赖 clickhouse-connect，dev 组 pytest）；pytest marker integration；profiles python/integration；compose 固定 clickhouse 镜像版本并只绑定 127.0.0.1；policy 增加 docs/design/*.md；写架构文档。Docker 守护进程未启动，集成部分可能 blocked。

- 2026-11-04 15:21:49: 验证 passed=True；日志 .workflow/runtime/verify-dev-environment-1793776909466596000

- 2026-11-04 15:21:57: 验收 #1 证据：check / pass / uv sync 建立 .venv（Python 3.14.5、pytest 9.2），uv.lock 锁定；python profile 用 .venv/bin/python -m pytest -m "not integration"，1 passed、1 deselected，未连接 ClickHouse

- 2026-11-04 15:21:57: 验收 #3 证据：manual / pass / policy.document_paths 增加 docs/design/*.md，workflow check 通过；docs/design/architecture.md 写入分层、模块约定、三条时点不变量；AGENTS 开始工作一节与 README 均指向该文档

- 2026-11-04 15:21:57: 验收 #2 受阻：Docker Desktop 已启动但守护进程未就绪（docker.sock 无法连接），可能停在首次启动的协议/登录界面；需用户处理后 docker compose up -d 并运行 integration profile。其余两条已有证据。

- 2026-11-04 15:41:33: 阻塞解除：Docker Desktop 升级到 4.98.0，修复 Docker.raw 属主后重置数据磁盘；docker compose 启动 ClickHouse 25.8，ping 通过

- 2026-11-04 15:41:33: 验证 passed=True；日志 .workflow/runtime/verify-dev-environment-1793778093565470000

- 2026-11-04 15:41:40: 验收 #1 证据：check / pass / uv sync 建立 .venv（Python 3.14.5、pytest 9.2），uv.lock 锁定；python profile 运行 .venv/bin/python -m pytest -m "not integration"：1 passed、1 deselected，不连接 ClickHouse

- 2026-11-04 15:41:40: 验收 #2 证据：manual / pass / docker compose up -d 启动 clickhouse-server:25.8（127.0.0.1:8123，ping=Ok）；integration profile 命令 .venv/bin/python -m pytest -q -m integration 退出 0：1 passed（test_local_clickhouse_reachable SELECT 1）、1 deselected；日志 .workflow/runtime/integration-1793778093.log。ClickHouse 停止时同一测试失败（连接拒绝），已在 Docker 修复前观察到

- 2026-11-04 15:44:21: 验证 passed=True；日志 .workflow/runtime/verify-dev-environment-1793778260760951000

- 2026-11-04 15:44:30: 验收 #1 证据：check / pass / uv.lock 锁定 clickhouse-connect 1.12.0、pytest 9.2.0；python profile .venv/bin/python -m pytest -m "not integration"（--strict-markers）：1 passed、1 deselected，不连接 ClickHouse；拼错的 marker 会直接报错

- 2026-11-04 15:44:31: 验收 #2 证据：manual / pass / compose 镜像固定为 clickhouse-server:25.8.33.6@sha256:0152dd51…，重建容器后 integration profile（pytest -m integration）退出 0：1 passed、1 deselected；日志 .workflow/runtime/integration-1793778270.log；测试直接 import clickhouse_connect，不再 importorskip

- 2026-11-04 15:44:31: 验收 #3 证据：manual / pass / policy 增加 docs/design/*.md，.pytest_cache 改为 excluded_paths 根目录排除，恢复原紧凑格式；architecture.md 明确唯一 join 键 (ts=开盘, symbol)、标签公式 close(t+lag+h)/close(t+lag)-1、I/O 模块范围与按实际结算时间计资金费率；AGENTS/README 指向该文档

- 2026-11-04 15:45:38: 验证 passed=True；日志 .workflow/runtime/verify-dev-environment-1793778338173356000

- 2026-11-04 15:45:38: 验收 #1 证据：check / pass / uv.lock 锁定 clickhouse-connect 1.12.0、pytest 9.2.0；python profile .venv/bin/python -m pytest -m "not integration"（--strict-markers）：1 passed、1 deselected，不连接 ClickHouse

- 2026-11-04 15:45:38: 验收 #2 证据：manual / pass / compose 镜像 clickhouse-server:25.8.33.6@sha256:0152dd51…；integration profile（pytest -m integration）退出 0：1 passed、1 deselected，日志 .workflow/runtime/integration-1793778270.log；本轮只改文档，未触及测试与配置

- 2026-11-04 15:45:38: 验收 #3 证据：manual / pass / policy 允许 docs/design/*.md；architecture.md 含唯一 join 键、因子/标签/可交易集合/资金费率区间四条时点约定及各自不变量测试构造；AGENTS/README 指向该文档

- 2026-11-04 15:46:26: 验证 passed=True；日志 .workflow/runtime/verify-dev-environment-1793778385655039000

- 2026-11-04 15:46:26: 验收 #1 证据：check / pass / uv.lock 锁定 clickhouse-connect 1.12.0、pytest 9.2.0；python profile .venv/bin/python -m pytest -m "not integration"（--strict-markers）：1 passed、1 deselected，不连接 ClickHouse

- 2026-11-04 15:46:26: 验收 #2 证据：manual / pass / compose 镜像 clickhouse-server:25.8.33.6@sha256:0152dd51…；integration profile（pytest -m integration）退出 0：1 passed、1 deselected，日志 .workflow/runtime/integration-1793778270.log；之后只改文档

- 2026-11-04 15:46:26: 验收 #3 证据：manual / pass / policy 允许 docs/design/*.md；architecture.md 含唯一 join 键、close/close_ts 记号、四条时点约定与各自不变量测试；AGENTS/README 指向该文档

- 2026-11-04 15:46:51: 审查记录：claude-subagent:general-purpose(read-only) / pass / 四轮只读审查，指纹前后一致：两 profile 均实跑通过，0 选中退出 5 不误报；strict-markers、直接 import、镜像 digest、policy 两行改动均已核对；时点约定无 off-by-one 与未来数据。遗留措辞：t+k 与 t+freq 共用加号，待下个时点相关任务改为 t+k·freq

- 2026-11-04 15:46:51: 当前代码的配置内检查与所需审查已通过；不代表发布授权。

- 2026-11-04 15:46:51: 完成归档：开发环境就绪：uv/.venv、python 与 integration 两个 profile、本地 ClickHouse 25.8.33.6、架构设计文档。遗留：architecture.md 第 36 行 t+k 写法歧义
