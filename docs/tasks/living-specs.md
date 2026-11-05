<!-- workflow-task
{
  "id": "living-specs",
  "goal": "引入 docs/specs 作为各模块行为规则的唯一事实来源，任务完成时合并新增或变更的规则",
  "acceptance": [
    "policy 允许 docs/specs/*.md；已完成模块（数据源、存储、批量接入、合约注册表）与时点约定各有规格文件，规则以\"需求 + 场景\"书写并注明对应测试",
    "时点约定只保留在 specs 中，architecture.md 改为引用，不重复；修正 t+k 写法歧义并补充资金费率 ts 规整",
    "AGENTS 与 README 写明：业务任务交付前须把新增或变更的规则合并进对应规格文件，审查核对规格与代码一致"
  ],
  "allow": [
    ".workflow/policy.json",
    "AGENTS.md",
    "README.md",
    "docs/specs/**",
    "docs/design/architecture.md"
  ],
  "profile": "python",
  "phase": "ready",
  "kind": "maintenance",
  "review_required": true
}
-->
# living-specs

目标：引入 docs/specs 作为各模块行为规则的唯一事实来源，任务完成时合并新增或变更的规则

## 验收条件

- policy 允许 docs/specs/*.md；已完成模块（数据源、存储、批量接入、合约注册表）与时点约定各有规格文件，规则以"需求 + 场景"书写并注明对应测试
- 时点约定只保留在 specs 中，architecture.md 改为引用，不重复；修正 t+k 写法歧义并补充资金费率 ts 规整
- AGENTS 与 README 写明：业务任务交付前须把新增或变更的规则合并进对应规格文件，审查核对规格与代码一致

- 2026-11-05 09:27:28: 已建立任务；明确事实、未知项和计划后进入 implement。

- 2026-11-05 09:27:28: 借鉴 OpenSpec 的"规格是持续维护的唯一事实"，只借规格格式，任务/验证/审查仍用现有工作流。规格内容取自已归档任务卡与审查结论，不新增未实现的规则。

- 2026-11-05 09:29:09: 验证 passed=True；日志 .workflow/runtime/verify-living-specs-1793842149171626000

- 2026-11-05 09:29:09: 验收 #1 证据：manual / pass / policy.document_paths 增加 docs/specs/*.md，workflow check 通过；新增 time-conventions、binance-vision、clickhouse-store、ingest、symbol-registry 五份规格，均为"需求 + 场景 + 测试"；脚本核对规格引用的 31 个测试名全部存在于 pytest 收集结果，未引用的仅为冒烟/连通性测试

- 2026-11-05 09:29:09: 验收 #2 证据：manual / pass / architecture.md 的时点约定节改为链接 + 三条要点，四条规则与不变量测试只在 time-conventions.md；t+k 定义为 t+k·freq；数据口径补资金费率 ts 规整与官方缺失

- 2026-11-05 09:29:09: 验收 #3 证据：manual / pass / AGENTS 开始工作要求读相关规格；协作与交付新增规格合并规则（建卡 --allow 含 docs/specs/**、审查核对规格与代码测试一致）；README 指向 docs/specs 与 time-conventions

- 2026-11-05 09:31:26: 审查后修订：资金费率措辞改为规整后的 ts；未单测的声明注明；AGENTS 统一 docs/specs/*.md 并要求无规则变化时注明；architecture 模块表只留职责与规格链接。缺口处理与 t+k 按日历时间两条为新语义，规格中标"待用户确认"，等用户决定后再交付。

- 2026-11-05 09:33:43: 用户确认：缺口处理（区间内缺任意一根 bar 则标签缺失；聚合输出实际 1m 根数；不补值）与 t+k 按日历时间 t+k·freq，均按推荐方案。

- 2026-11-05 09:33:43: 验证 passed=True；日志 .workflow/runtime/verify-living-specs-1793842423231823000

- 2026-11-05 09:33:43: 验收 #1 证据：manual / pass / policy 允许 docs/specs/*.md，check 通过；五份规格为需求+场景+测试，引用的 31 个测试名全部存在；未单测的声明已注明（refresh 失败不写入、同版本保留最后插入、空文件记 0）

- 2026-11-05 09:33:43: 验收 #2 证据：manual / pass / architecture 时点约定节仅链接与要点、模块表只留职责与规格链接；t+k 定义为 t+k·freq（按日历时间，用户确认）；资金费率用规整后的 ts；补缺口规则（用户确认）

- 2026-11-05 09:33:43: 验收 #3 证据：manual / pass / AGENTS：开工读相关规格；交付前合并规则，建卡 --allow 含 docs/specs/*.md，无规则变化须在任务卡注明，审查核对规格与代码测试一致；README 指向 docs/specs

- 2026-11-05 09:34:30: 验证 passed=True；日志 .workflow/runtime/verify-living-specs-1793842469894496000

- 2026-11-05 09:34:30: 验收 #1 证据：manual / pass / policy 允许 docs/specs/*.md，check 通过；五份规格为需求+场景+测试，引用的 31 个测试名全部存在；未单测的声明已注明

- 2026-11-05 09:34:30: 验收 #2 证据：manual / pass / architecture 时点约定节仅链接与要点、模块表只留职责与规格链接（保留成本模型默认 taker 5bp、固定 bp 滑点）；t+k 按日历时间、缺口规则均经用户确认

- 2026-11-05 09:34:30: 验收 #3 证据：manual / pass / AGENTS：开工读相关规格；交付前合并规则，--allow 含 docs/specs/*.md，无规则变化注明；审查核对规格与代码测试一致；README 指向 docs/specs

- 2026-11-05 09:34:48: 审查记录：claude-subagent:general-purpose(read-only) / pass / 四轮只读审查：规格与代码逐条核对一致；新语义（缺口、t+k 按日历时间）经用户确认；未单测声明已注明；AGENTS 规定与 policy 一致；成本模型默认参数保留。指纹与主 Agent 改动后记录值一致

- 2026-11-05 09:34:48: 当前代码的配置内检查与所需审查已通过；不代表发布授权。

- 2026-11-05 09:34:48: 完成归档：引入 docs/specs 规格库与合并规则
