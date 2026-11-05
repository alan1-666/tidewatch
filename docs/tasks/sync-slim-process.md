<!-- workflow-task
{
  "id": "sync-slim-process",
  "goal": "逐字同步 coding-workflow 已审查通过的\"控制流程开销\"条款（来源任务 slim-process）",
  "acceptance": [
    "AGENTS 的\"控制流程开销\"一节与检查表\"纯文案\"一行和 coding-workflow 逐字一致（diff 为空），其余内容不变"
  ],
  "allow": [
    "AGENTS.md"
  ],
  "profile": "python",
  "phase": "ready",
  "kind": "maintenance",
  "review_required": false
}
-->
# sync-slim-process

目标：逐字同步 coding-workflow 已审查通过的"控制流程开销"条款（来源任务 slim-process）

## 验收条件

- AGENTS 的"控制流程开销"一节与检查表"纯文案"一行和 coding-workflow 逐字一致（diff 为空），其余内容不变

- 2026-11-05 10:21:55: 已建立任务；明确事实、未知项和计划后进入 implement。

- 2026-11-05 10:21:55: 来源：coding-workflow 任务 slim-process（审查 pass，指纹 7cbfe17e…）。按该条款中的唯一免审例外处理：逐字同步、走 maintenance、注明来源。

- 2026-11-05 10:21:56: 验证 passed=True；日志 .workflow/runtime/verify-sync-slim-process-1793845315790745000

- 2026-11-05 10:21:56: 验收 #1 证据：manual / pass / diff 两仓库"控制流程开销"节与检查表"纯文案"行均为空；git diff 仅 AGENTS.md，新增该节并替换一行，其余不变

- 2026-11-05 10:21:56: 当前代码的配置内检查与所需审查已通过；不代表发布授权。

- 2026-11-05 10:21:56: 完成归档：同步完成（来源 coding-workflow slim-process）
