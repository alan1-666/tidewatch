<!-- workflow-task
{
  "id": "integration-profile-superset",
  "goal": "integration profile 同时运行单元测试与集成测试，使涉及数据库的任务不漏跑纯函数测试",
  "acceptance": [
    "integration profile 依次运行 unit-tests（not integration）与 integration-tests（integration），任一失败则验证失败；python profile 不变"
  ],
  "allow": [
    ".workflow/project.json",
    "AGENTS.md",
    "README.md",
    "docs/design/architecture.md"
  ],
  "profile": "python",
  "phase": "ready",
  "kind": "maintenance",
  "review_required": true
}
-->
# integration-profile-superset

目标：integration profile 同时运行单元测试与集成测试，使涉及数据库的任务不漏跑纯函数测试

## 验收条件

- integration profile 依次运行 unit-tests（not integration）与 integration-tests（integration），任一失败则验证失败；python profile 不变

- 2026-11-04 16:12:16: 已建立任务；明确事实、未知项和计划后进入 implement。

- 2026-11-04 16:12:16: 只在 integration profile 前面加入与 python profile 相同的 unit-tests 检查；文档同步一句。

- 2026-11-04 16:12:17: 验证 passed=True；日志 .workflow/runtime/verify-integration-profile-superset-1793779936919580000

- 2026-11-04 16:12:27: 验证 passed=True；日志 .workflow/runtime/verify-integration-profile-superset-1793779947379958000

- 2026-11-04 16:12:28: 验收 #1 证据：manual / pass / project.json integration profile 依次为 unit-tests（-m not integration）与 integration-tests（-m integration），python profile 未变；按该 profile 逐条执行：unit-tests 0（23 passed）、integration-tests 0（5 passed），日志 .workflow/runtime/profile-integration-1793779947.log；verify 对任一检查非 0 即失败（检查器既有行为）

- 2026-11-04 16:13:28: 审查记录：claude-subagent:general-purpose(read-only) / pass / 同名 unit-tests 仅在各自 profile 内唯一，verify 只跑任务 profile、日志按序号、evidence 按本次 run 查找，均无冲突；三处文档与配置一致。提示：下个 integration 任务确认两条检查都出现在日志中

- 2026-11-04 16:13:28: 当前代码的配置内检查与所需审查已通过；不代表发布授权。

- 2026-11-04 16:13:28: 完成归档：integration profile 现为单元测试加集成测试
