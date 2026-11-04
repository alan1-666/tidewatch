#!/usr/bin/env python3
"""Generate/check thin client adapters from shared role files, without global writes."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ROLES = {'explorer': '定位真实代码、契约和影响面；只读',
         'implementer': '在指定范围实现一个功能切片并验证',
         'reviewer': '独立检查需求符合度、缺陷和验证缺口；只读'}


def expected(root):
    files = {'CLAUDE.md': '@AGENTS.md\n'}
    for role, description in ROLES.items():
        content = (root / '.workflow/roles' / (role + '.md')).read_text()
        codex = '\n'.join([f'name = "{role}"', f'description = {json.dumps(description, ensure_ascii=False)}',
                            'developer_instructions = ' + json.dumps(content, ensure_ascii=False), ''])
        tools = 'Read, Glob, Grep' if role != 'implementer' else 'Read, Glob, Grep, Edit, Write, Bash'
        claude = f'---\nname: {role}\ndescription: {description}\ntools: {tools}\n---\n\n{content}'
        files[f'.codex/agents/{role}.toml'] = codex
        files[f'.claude/agents/{role}.md'] = claude
    for client in ('codex', 'claude'):
        # Codex has no CLAUDE_PROJECT_DIR; resolve the independent lab repository root.
        base = '$(git rev-parse --show-toplevel)' if client == 'codex' else '${CLAUDE_PROJECT_DIR}'
        command = f'python3 "{base}/scripts/workflow/hook.py" --client {client}'
        hooks = {}
        for event in ('SessionStart', 'PreToolUse', 'PostToolUse', 'Stop'):
            group = {'hooks': [{'type': 'command', 'command': command, 'timeout': 15}]}
            if event in ('PreToolUse', 'PostToolUse'):
                group['matcher'] = '.*'  # Filter known writes in the adapter; never assume identical tool names.
            hooks[event] = [group]
        name = '.codex/hooks.json' if client == 'codex' else '.claude/settings.json'
        files[name] = json.dumps({'hooks': hooks}, ensure_ascii=False, indent=2) + '\n'
    return files


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    p.add_argument('--root', type=Path, default=ROOT)
    args = p.parse_args()
    root = args.root.resolve()
    planned = expected(root)
    if not args.check:
        conflicts = [name for name, content in planned.items()
                     if (root / name).exists() and (root / name).read_text() != content]
        if conflicts:
            print('拒绝覆盖已有适配器；先审阅差异并显式移走旧文件: ' + ', '.join(conflicts), file=sys.stderr)
            return 1
    changed = []
    for name, content in planned.items():
        dest = root / name
        if not dest.exists() or dest.read_text() != content:
            changed.append(name)
            if not args.check:
                if dest.exists():
                    print(f'拒绝覆盖已有适配器 {name}；先审阅差异并显式移走旧文件。', file=sys.stderr)
                    return 1
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content)
    print(json.dumps({'adapter_drift': changed, 'mode': 'check' if args.check else 'create'}, ensure_ascii=False))
    return int(bool(changed) and args.check)


if __name__ == '__main__':
    sys.exit(main())
