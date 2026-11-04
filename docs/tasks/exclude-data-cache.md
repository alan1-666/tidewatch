<!-- workflow-task
{
  "id": "exclude-data-cache",
  "goal": "工作流 policy 排除根目录 data/ 缓存，与 .gitignore 一致",
  "acceptance": [
    "excluded_paths 包含 data/**，data/raw 下的缓存文件不再被判为越界或改变指纹；只排除根目录 data/，tests/data 等仍受检查"
  ],
  "allow": [
    ".workflow/policy.json"
  ],
  "profile": "python",
  "phase": "ready",
  "kind": "maintenance",
  "review_required": true
}
-->
# exclude-data-cache

目标：工作流 policy 排除根目录 data/ 缓存，与 .gitignore 一致

## 验收条件

- excluded_paths 包含 data/**，data/raw 下的缓存文件不再被判为越界或改变指纹；只排除根目录 data/，tests/data 等仍受检查

- 2026-11-04 16:16:54: 已建立任务；明确事实、未知项和计划后进入 implement。

- 2026-11-04 16:16:54: 只在 excluded_paths 加 data/**（matches 以仓库相对路径匹配，等价于根目录）。

- 2026-11-04 16:17:06: 验证 passed=True；日志 .workflow/runtime/verify-exclude-data-cache-1793780226298769000

- 2026-11-04 16:17:06: 验收 #1 证据：manual / pass / policy excluded_paths 增加 data/**；缓存移回 data/raw 后 workflow check 通过；在 data/raw 新增文件前后 snapshot 指纹相同；matches：data/raw/a.zip 排除，tests/data/x.py 与 tidewatch/data/x.py 不排除

- 2026-11-04 16:17:56: 验证 passed=True；日志 .workflow/runtime/verify-exclude-data-cache-1793780275881012000

- 2026-11-04 16:17:56: 验收 #1 证据：manual / pass / excluded_paths 增加 data/raw/**（按审查建议收窄）；缓存位于 data/raw 时 workflow check 通过；data/raw 新增文件不改变 snapshot 指纹；matches：data/raw/a.zip 排除，data/x.py、tests/data/x.py 不排除

- 2026-11-04 16:18:25: 审查记录：claude-subagent:general-purpose(read-only) / pass / 两轮：data/** 可被用来藏源码，按建议收窄为 data/raw/**；fnmatchcase 整路径匹配，等价根目录锚定；data/、tests/data 仍受检查。残余：被排除目录中的源码文件，需检查器层面另行处理

- 2026-11-04 16:18:25: 当前代码的配置内检查与所需审查已通过；不代表发布授权。

- 2026-11-04 16:18:25: 完成归档：policy 排除 data/raw/**
