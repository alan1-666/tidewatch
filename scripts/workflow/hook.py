#!/usr/bin/env python3
"""Codex/Claude lifecycle adapter; policy is shared, tool payloads are normalized."""
import argparse
from contextlib import nullcontext
import json
import re
import sys
from pathlib import Path

from policy import WorkflowError, config, inspect, path_errors, relative
from workflow import DEFAULT_ROOT, active, lock, read_task, readiness, save_state

EDITORS = {'Write', 'Edit', 'MultiEdit', 'apply_patch'}
SHELLS = {'Bash', 'exec_command', 'shell', 'shell_command', 'write_stdin'}


def context(event, message):
    return {'hookSpecificOutput': {'hookEventName': event, 'additionalContext': message}}


def deny(message):
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                                  'permissionDecision': 'deny', 'permissionDecisionReason': message}}


def editor_paths(payload):
    tool = payload.get('tool_name')
    data = payload.get('tool_input', {})
    if tool == 'apply_patch':
        if not isinstance(data, (str, dict)):
            raise WorkflowError('无法识别 apply_patch 输入结构；需要字符串或对象')
        patch = data if isinstance(data, str) else data.get('command', data.get('patch', data.get('input', '')))
        if not isinstance(patch, str):
            raise WorkflowError('无法识别 apply_patch 输入')
        paths = re.findall(r'^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$', patch, re.M)
        if not paths:
            raise WorkflowError('无法解析 patch 文件范围；检查未完成')
        return paths
    if tool in EDITORS:
        path = data.get('file_path', data.get('path')) if isinstance(data, dict) else None
        if not isinstance(path, str) or not path:
            raise WorkflowError('编辑工具缺少文件路径；检查未完成')
        return [path]
    return []


def handle(root, client, payload):
    event = payload.get('hook_event_name')
    if event not in ('SessionStart', 'PreToolUse', 'PostToolUse', 'Stop'):
        raise WorkflowError(f'不支持的 Hook 事件: {event}')
    policy, _ = config(root)
    state = active(root)
    task = read_task(root, state) if state else None
    tool = payload.get('tool_name')
    if event == 'SessionStart':
        message = '共用规则入口 AGENTS.md；检查器 scripts/workflow/workflow.py。'
        if task:
            message += f"当前任务 {task['id']}，阶段 {task['phase']}，写入者 {state.get('owner')}。先读 docs/tasks/{task['id']}.md 并运行 status。"
            if state.get('handoff'):
                message += '上次交接的下一步：' + '；'.join(state['handoff']['next']) + '。执行 brief 核对当前变化和证据。'
        else:
            message += '未绑定实现任务，阅读/设计可继续；开始写代码前建立任务卡。'
        return context(event, message)
    if event == 'PreToolUse':
        paths = editor_paths(payload)
        if not paths:
            if tool in SHELLS:
                return context(event, 'Shell 不是安全的路径解析边界。写入须先绑定任务并 claim；后置检查/CI 会检测越界，不保证执行前拦截。')
            return {}
        if not task:
            return deny('尚未绑定实现任务；先运行 workflow.py start，再 phase implement。')
        # Tool paths are relative to the actual tool/session cwd, never assumed repo-root.
        cwd = Path(payload.get('cwd', root))
        cwd = cwd if cwd.is_absolute() else root / cwd
        errors = []
        for path in paths:
            target = Path(path) if Path(path).is_absolute() else cwd / path
            rel = relative(root, target)
            if rel == f"docs/tasks/{task['id']}.md":
                continue
            errors.extend(path_errors(root, policy, rel, task))
        if errors:
            return deny('\n'.join(errors))
        session = payload.get('session_id')
        if not isinstance(session, str) or not session:
            return deny('缺少 session_id，无法确认写入者；检查未完成')
        owner = f'{client}:{session}'
        if state.get('owner') not in (None, owner):
            return deny(f"工作区由 {state['owner']} 写入；先显式 handoff，或使用独立 worktree。")
        state['owner'] = owner
        save_state(root, state)
        return {}
    if event == 'PostToolUse':
        # Read-only tools don't trigger another full-tree pass.
        if tool not in EDITORS | SHELLS:
            return {}
        errors = inspect(root, task, state)
        if errors:
            return context(event, '后置检查发现问题（写入已发生，不会回滚）：\n' + '\n'.join(errors[:15]))
        return {}
    # Stop is not a universal completion gate: only a deliberate ready attempt is gated.
    if not task or task['phase'] == 'blocked' or not state.get('delivery_requested'):
        return {}
    errors = readiness(root, state, task)
    if not errors:
        return {}
    message = '当前任务尚不可交付：' + '；'.join(errors[:8])
    if payload.get('stop_hook_active'):
        return {'systemMessage': message + '。已执行一次补验提示，允许结束；请如实报告未完成。'}
    return {'decision': 'block', 'reason': message + '。补验一次；受阻时记录 blocked，不得声称通过。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', choices=('codex', 'claude'), required=True)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    payload = {}
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise WorkflowError('Hook 输入必须是 JSON 对象')
        # Only editor PreToolUse mutates owner state. Parallel read tools must not
        # compete for the mutation lock (verify also holds it while checking).
        mutates = payload.get('hook_event_name') == 'PreToolUse' and payload.get('tool_name') in EDITORS
        with lock(args.root.resolve()) if mutates else nullcontext():
            output = handle(args.root.resolve(), args.client, payload)
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (WorkflowError, OSError, ValueError, TypeError, KeyError) as exc:
        message = f'workflow Hook 检查不可用: {exc}'
        if isinstance(payload, dict) and payload.get('hook_event_name') == 'Stop':
            if payload.get('stop_hook_active'):
                output = {'systemMessage': message + '。补验后仍不可用，允许结束；必须报告未完成。'}
            else:
                output = {'decision': 'block', 'reason': message + '。只补验一次；不能修复时如实报告未完成。'}
            print(json.dumps(output, ensure_ascii=False))
            return 0
        # Exit 2 signals an unavailable check; never silently produce a passing result.
        print(message, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
