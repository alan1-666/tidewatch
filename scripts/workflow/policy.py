"""Shared deterministic policy. No network, dependencies, or automatic fixes."""
import fnmatch
import hashlib
import json
import os
from pathlib import Path


class WorkflowError(Exception):
    pass


# verify 内置的工作流自检名称；profile 不得复用，避免日志和证据绑定指向不明。
SELFCHECK = 'workflow-selfcheck'


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise WorkflowError(f"无法读取配置/状态 {path}: {exc}") from exc


def config(root):
    policy = read_json(root / '.workflow/policy.json')
    project = read_json(root / '.workflow/project.json')
    if not isinstance(policy, dict) or not isinstance(project, dict):
        raise WorkflowError('policy.json 与 project.json 必须是 JSON 对象')
    if policy.get('version') != 1 or project.get('version') != 1:
        raise WorkflowError('不支持的配置版本')
    limit = policy.get('max_source_lines')
    if type(limit) is not int or not 1 <= limit <= 800:
        raise WorkflowError('max_source_lines 必须为 1..800 的整数')
    for key in ('source_extensions', 'ignored_directories', 'excluded_paths',
                'document_paths', 'protected_paths'):
        if not isinstance(policy.get(key), list) or not all(isinstance(x, str) for x in policy[key]):
            raise WorkflowError(f'无效策略: {key}')
    if not isinstance(policy.get('legacy_source_lines'), dict):
        raise WorkflowError('legacy_source_lines 必须是显式路径到行数的映射')
    for path, count in policy['legacy_source_lines'].items():
        if not isinstance(path, str) or type(count) is not int or count <= limit:
            raise WorkflowError('无效旧文件基线')
    if not isinstance(project.get('profiles'), dict) or not project['profiles']:
        raise WorkflowError('至少需要一个实际验证 profile')
    for checks in project['profiles'].values():
        if not isinstance(checks, list) or not checks:
            raise WorkflowError('验证 profile 不得为空')
        names = set()
        for check in checks:
            if not isinstance(check, dict):
                raise WorkflowError('无效验证命令')
            name, argv, timeout = check.get('name'), check.get('argv'), check.get('timeout')
            if not isinstance(name, str) or not name or name in names:
                raise WorkflowError('检查名称为空或重复')
            if name == SELFCHECK:
                raise WorkflowError(f'{SELFCHECK} 是 verify 内置自检的保留名称')
            if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
                raise WorkflowError('检查命令必须为非空 argv 数组，不执行 shell 字符串')
            if type(timeout) is not int or not 1 <= timeout <= 600:
                raise WorkflowError('检查 timeout 必须为 1..600 秒')
            names.add(name)
    return policy, project


def relative(root, path):
    candidate = Path(path)
    candidate = candidate if candidate.is_absolute() else root / candidate
    try:
        return candidate.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise WorkflowError(f'路径越出工作区: {path}') from exc


def inventory(root, policy):
    """Includes untracked and unstaged files; does not follow directory symlinks."""
    result = {}
    for base, directories, files in os.walk(root, followlinks=False):
        for name in list(directories):
            path = Path(base) / name
            rel = path.relative_to(root).as_posix()
            if name in policy['ignored_directories'] or matches(rel + '/', policy['excluded_paths']):
                directories.remove(name)
            elif path.is_symlink():
                directories.remove(name)
                result[rel] = {'link': os.readlink(path)}
        for name in sorted(files):
            path = Path(base) / name
            rel = path.relative_to(root).as_posix()
            if name in ('.DS_Store',) or name.endswith('.pyc') or matches(rel, policy['excluded_paths']):
                continue
            if path.is_symlink():
                result[rel] = {'link': os.readlink(path)}
                continue
            raw = path.read_bytes()
            result[rel] = {'sha256': hashlib.sha256(raw).hexdigest(), 'mode': path.stat().st_mode & 0o777}
    return result


def source_snapshot(root, policy, task_id=None):
    # Task prose may evolve without invalidating code; contract fields are hashed separately.
    own_card = f'docs/tasks/{task_id}.md' if task_id else None
    return {p: v for p, v in inventory(root, policy).items() if p != own_card}


def changes(before, after):
    return sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))


def path_errors(root, policy, path, task=None):
    rel = relative(root, path)
    errors = []
    if task:
        if task['phase'] not in ('implement', 'verify', 'review'):
            errors.append(f"阶段 {task['phase']} 不允许修改业务代码")
        if not matches(rel, task['allow']):
            errors.append(f'超出任务允许范围: {rel}')
        if matches(rel, policy['protected_paths']) and task['kind'] != 'maintenance':
            errors.append(f'基础设施需要 maintenance 任务: {rel}')
    if Path(rel).suffix.lower() in ('.md', '.mdx', '.rst', '.txt'):
        if not matches(rel, policy['document_paths']):
            errors.append(f'文档路径不在白名单: {rel}')
    return errors


def inspect(root, task=None, state=None):
    policy, project = config(root)
    files = inventory(root, policy)
    errors = []
    for rel, info in files.items():
        if 'link' in info:
            try:
                relative(root, rel)
            except WorkflowError as exc:
                errors.append(str(exc))
            errors.append(f'演练仓库不接受符号链接，请使用普通文件: {rel}')
            continue
        errors.extend(path_errors(root, policy, rel))
        if Path(rel).suffix in policy['source_extensions']:
            count = len((root / rel).read_text().splitlines())
            allowed = max(policy['max_source_lines'], policy['legacy_source_lines'].get(rel, 0))
            if count > allowed:
                errors.append(f'文件超限: {rel}: {count} > {allowed} 行')
    if task and state:
        current = source_snapshot(root, policy, task['id'])
        changed = changes(state['baseline'], current)
        # Inspection is also used in blocked/ready states; editing phase is a pre-tool rule.
        inspecting = dict(task, phase='implement')
        for rel in changed:
            errors.extend(path_errors(root, policy, rel, inspecting))
        for rel, baseline in state.get('initial_lines', {}).items():
            if rel in changed and (root / rel).is_file():
                count = len((root / rel).read_text().splitlines())
                if count > policy['max_source_lines'] and count > baseline:
                    errors.append(f'旧大文件不得增长: {rel}: {baseline} → {count}')
        if task['kind'] != 'maintenance' and digest([policy, project]) != state['config_digest']:
            errors.append('任务执行中策略或验证配置发生变化；不能自行放宽规则')
    return sorted(set(errors))


def fingerprint(root, task):
    policy, project = config(root)
    contract = {key: task[key] for key in ('id', 'goal', 'acceptance', 'allow', 'kind', 'profile', 'review_required')}
    return digest({'files': source_snapshot(root, policy, task['id']), 'contract': contract, 'config': [policy, project]})
