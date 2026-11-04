#!/usr/bin/env python3
"""Local task controller. Run `python3 scripts/workflow/workflow.py --help`."""
import argparse
import ast
from contextlib import contextmanager, nullcontext
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

from policy import SELFCHECK, WorkflowError, changes, config, digest, fingerprint, inspect, inventory, read_json, source_snapshot
from evidence import acceptance_errors, acceptance_rows, record

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
MARKER = re.compile(r'\A<!-- workflow-task\n(.*?)\n-->\n', re.S)
PHASES = ('explore', 'implement', 'verify', 'review', 'blocked', 'ready')
READ_ONLY = ('check', 'syntax', 'selfcheck', 'status', 'brief', 'doctor', 'snapshot')


def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.pending-')
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def lock(root):
    runtime = root / '.workflow/runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / 'controller.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WorkflowError('另一检查器正在更新此工作区，请稍后重试') from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def active(root):
    path = root / '.workflow/runtime/active.json'
    return read_json(path) if path.exists() else None


def save_state(root, state):
    atomic(root / '.workflow/runtime/active.json', json.dumps(state, ensure_ascii=False, indent=2) + '\n')


def task_path(root, task_id):
    if not isinstance(task_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', task_id):
        raise WorkflowError('任务 ID 只允许小写字母、数字和连字符，最多 64 字符')
    return root / 'docs/tasks' / (task_id + '.md')


def read_task(root, state):
    path = task_path(root, state['id'])
    match = MARKER.match(path.read_text())
    if not match:
        raise WorkflowError('任务卡缺少合法的 workflow-task 元数据')
    try:
        task = json.loads(match[1])
    except ValueError as exc:
        raise WorkflowError('任务卡元数据不是有效 JSON') from exc
    if task.get('id') != state['id'] or task.get('phase') not in PHASES:
        raise WorkflowError('任务 ID 或阶段无效')
    for key in ('goal', 'profile'):
        if not isinstance(task.get(key), str) or not task[key].strip():
            raise WorkflowError(f'任务缺少 {key}')
    for key in ('acceptance', 'allow'):
        if not isinstance(task.get(key), list) or not task[key] or not all(isinstance(x, str) and x for x in task[key]):
            raise WorkflowError(f'任务缺少 {key}')
    if task.get('kind') not in ('feature', 'maintenance') or type(task.get('review_required')) is not bool:
        raise WorkflowError('任务 kind/review_required 无效')
    if task['profile'] not in config(root)[1]['profiles']:
        raise WorkflowError('任务引用未知验证 profile')
    if state.get('contract_digest') != contract_digest(task):
        raise WorkflowError('任务范围或验收被直接修改；请交接并另建任务，不可静默改约定')
    return task


def contract_digest(task):
    return digest({key: task[key] for key in ('id', 'goal', 'acceptance', 'allow', 'kind', 'profile', 'review_required')})


def save_task(root, task, note=''):
    path = task_path(root, task['id'])
    old = path.read_text() if path.exists() else ''
    body = MARKER.sub('', old) if old else f"# {task['id']}\n\n目标：{task['goal']}\n\n## 验收条件\n\n" + ''.join(f'- {x}\n' for x in task['acceptance'])
    if note:
        body += f'\n- {time.strftime("%Y-%m-%d %H:%M:%S")}: {note}\n'
    atomic(path, '<!-- workflow-task\n' + json.dumps(task, ensure_ascii=False, indent=2) + '\n-->\n' + body)


def require_active(root):
    state = active(root)
    if not state:
        raise WorkflowError('未绑定实现任务；先 start。问答/源码阅读无需绑定任务')
    return state, read_task(root, state)


def readiness(root, state, task):
    errors = inspect(root, task, state)
    if task['phase'] in ('explore', 'blocked'):
        errors.append(f"阶段 {task['phase']} 不可交付；先明确计划或解除阻塞")
    stamp = fingerprint(root, task)
    evidence = state.get('verification')
    if not evidence or not evidence.get('passed'):
        errors.append('缺少成功验证；执行 verify')
    elif evidence['fingerprint'] != stamp:
        errors.append('验证已过期：源码、关键配置或任务约定发生变化')
    errors.extend(acceptance_errors(root, state, task))
    if task['review_required']:
        review = state.get('review')
        if not review or review.get('result') != 'pass':
            errors.append('缺少通过的独立审查记录')
        elif review.get('fingerprint') != stamp:
            errors.append('审查已过期，需要复查受影响改动')
    return errors


def stop_check(process):
    # Each check owns a process group, so cancellation also removes its children.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_check(root, check, log):
    argv = [sys.executable if value == '{python}' else value for value in check['argv']]
    started = time.time()
    result = {'name': check['name'], 'argv': argv, 'cwd': str(root), 'started_at': started}
    with log.open('w') as out:
        try:
            process = subprocess.Popen(argv, cwd=root, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                result['exit_code'] = process.wait(timeout=check['timeout'])
            except subprocess.TimeoutExpired:
                stop_check(process)
                result.update(exit_code=124, error='timeout')
            except BaseException:
                stop_check(process)
                raise
        except OSError as exc:
            result.update(exit_code=127, error=str(exc))
    result.update(duration_seconds=round(time.time() - started, 3), log=str(log.relative_to(root)))
    return result


def perform(root, args):
    policy, project = config(root)
    if args.action == 'doctor':
        from diagnostics import doctor
        return doctor(root)
    if args.action == 'snapshot':
        state = active(root)
        task = read_task(root, state) if state else None
        stamp = fingerprint(root, task) if task else digest({'files': source_snapshot(root, policy),
                                                            'config': [policy, project]})
        return {'fingerprint': stamp, 'task': task['id'] if task else None,
                'scope': 'working tree including untracked; runtime and current task prose excluded'}
    if args.action == 'start':
        if active(root):
            raise WorkflowError('已有活动任务；先 finish 或 release --note 交接归档')
        path = task_path(root, args.id)
        if path.exists():
            raise WorkflowError('任务卡已存在，请使用新的任务 ID；不会覆盖旧记录')
        if args.profile is None:
            # 只有一个 profile 时没有歧义；多个时让建卡者明确选择，不按顺序猜。
            if len(project['profiles']) != 1:
                raise WorkflowError('有多个验证 profile，请用 --profile 指定：' + ', '.join(project['profiles']))
            args.profile = next(iter(project['profiles']))
        if args.profile not in project['profiles']:
            raise WorkflowError('未知验证 profile')
        for allowed in args.allow:
            if Path(allowed).is_absolute() or '..' in Path(allowed).parts or allowed in ('*', '**'):
                raise WorkflowError('允许范围必须是明确的仓库相对路径或模块 glob')
        task = dict(id=args.id, goal=args.goal, acceptance=args.accept, allow=args.allow,
                    profile=args.profile, phase='explore', kind=args.kind, review_required=not args.no_review)
        initial = inspect(root)
        if initial:
            raise WorkflowError('基线检查失败:\n' + '\n'.join(initial))
        state = {'id': args.id, 'baseline': source_snapshot(root, policy, args.id), 'owner': None,
                 'config_digest': digest([policy, project]), 'contract_digest': contract_digest(task),
                 'initial_lines': {p: len((root / p).read_text().splitlines()) for p in inventory(root, policy)
                                   if Path(p).suffix in policy['source_extensions'] and not (root / p).is_symlink()}}
        save_task(root, task, '已建立任务；明确事实、未知项和计划后进入 implement。')
        save_state(root, state)
        return {'task': args.id, 'phase': 'explore', 'card': str(path)}
    if args.action == 'check':
        state = active(root)
        task = read_task(root, state) if state else None
        errors = inspect(root, task, state)
        if errors:
            raise WorkflowError('\n'.join(errors))
        return {'check': 'pass', 'scope': 'entire working tree, including untracked files'}
    if args.action == 'syntax':
        for rel in inventory(root, policy):
            if rel.endswith('.py'):
                ast.parse((root / rel).read_text(), filename=rel)
        return {'python_syntax': 'pass', 'typecheck': 'not configured; this is syntax only'}
    if args.action == 'selfcheck':
        # 与业务语言无关的工作流自检；verify 固定先跑，项目 profile 无法省略。
        from adapters import expected
        state = active(root)
        errors = inspect(root, read_task(root, state) if state else None, state)
        for rel in inventory(root, policy):
            if rel.endswith('.py'):
                try:
                    ast.parse((root / rel).read_text(), filename=rel)
                except SyntaxError as exc:
                    errors.append(f'Python 语法错误: {rel}:{exc.lineno}')
        errors += [f'适配器漂移: {path}' for path, content in expected(root).items()
                   if not (root / path).is_file() or (root / path).read_text() != content]
        if errors:
            raise WorkflowError('\n'.join(errors))
        return {'selfcheck': 'pass', 'scope': 'policy, checker syntax, adapter consistency'}
    if args.action in ('status', 'brief') and not active(root):
        return {'active_task': None, 'mode': 'read/design; no delivery gate'}
    state, task = require_active(root)
    if args.action in ('status', 'brief'):
        errors = readiness(root, state, task)
        handoff = state.get('handoff')
        if handoff:
            handoff = dict(handoff, stale=handoff['fingerprint'] != fingerprint(root, task))
        return {'task': task, 'owner': state.get('owner'), 'ready': not errors, 'remaining': errors,
                'changed_files': changes(state['baseline'], source_snapshot(root, policy, task['id'])),
                'acceptance': acceptance_rows(root, state, task), 'verification': state.get('verification'),
                'review': state.get('review'), 'handoff': handoff}
    if args.action == 'phase':
        task['phase'] = args.phase
        state['delivery_requested'] = False
        save_task(root, task, args.note)
    elif args.action == 'claim':
        if state.get('owner') not in (None, args.owner):
            raise WorkflowError(f"工作区已有写入者 {state['owner']}，先 handoff")
        state['owner'] = args.owner
    elif args.action == 'handoff':
        if not args.note.strip() or not all(s.strip() for s in args.next):
            raise WorkflowError('交接说明和下一步不可为空')
        state['handoff'] = {'from': state.get('owner'), 'note': args.note, 'next': args.next,
                            'blockers': args.blocker, 'time': time.time(), 'fingerprint': fingerprint(root, task)}
        state['owner'] = None
        state['delivery_requested'] = False
        save_task(root, task, '交接：' + args.note + '；下一步：' + '；'.join(args.next)
                  + '；阻塞：' + ('；'.join(args.blocker) or '无已记录阻塞'))
    elif args.action == 'evidence':
        item = record(root, state, task, args)
        save_task(root, task, f"验收 #{args.criterion} 证据：{item['kind']} / {item['result']} / {args.note}")
    elif args.action == 'verify':
        run_id = f"verify-{task['id']}-{time.time_ns()}"
        # Persist first: even an uncatchable termination must not resurrect a prior green run.
        state['verification'] = {'run_id': run_id, 'passed': False, 'status': 'running', 'started_at': time.time()}
        save_state(root, state)
        try:
            errors = inspect(root, task, state)
            if errors:
                raise WorkflowError('\n'.join(errors))
            if task['phase'] not in ('implement', 'verify', 'review'):
                raise WorkflowError('先进入 implement/verify/review 阶段')
            task['phase'] = 'verify'
            save_task(root, task)
            stamp = fingerprint(root, task)
            logdir = root / '.workflow/runtime' / run_id
            logdir.mkdir()
            selfcheck = {'name': SELFCHECK, 'timeout': 60,
                         'argv': ['{python}', str(Path(__file__).resolve()), '--root', str(root), 'selfcheck']}
            profile = [selfcheck] + project['profiles'][task['profile']]
            checks = [run_check(root, c, logdir / f'{i}.log') for i, c in enumerate(profile)]
            passed = stamp == fingerprint(root, task) and all(c['exit_code'] == 0 for c in checks)
            state['verification'].update(fingerprint=stamp, checks=checks, passed=passed,
                                         status='passed' if passed else 'failed')
            save_task(root, task, f"验证 passed={passed}；日志 {logdir.relative_to(root)}")
            if not passed:
                raise WorkflowError('验证失败或运行期间源码变化；查看 status 和日志')
        except BaseException as exc:
            state['verification'].update(passed=False, error=str(exc) or type(exc).__name__,
                                         status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed')
            save_state(root, state)
            raise
    elif args.action == 'review':
        # This records a named reviewer's evidence; it does not run or impersonate that reviewer.
        if args.fingerprint != fingerprint(root, task):
            raise WorkflowError('审查快照已过期：当前代码与被审版本不同，请复查后再记录')
        if not args.reviewer.strip() or not args.note.strip():
            raise WorkflowError('审查身份与结论不可为空')
        state['review'] = {'reviewer': args.reviewer, 'result': args.result,
                           'note': args.note, 'fingerprint': args.fingerprint, 'time': time.time()}
        task['phase'] = 'review'
        save_task(root, task, f'审查记录：{args.reviewer} / {args.result} / {args.note}')
    elif args.action == 'ready':
        state['delivery_requested'] = True
        save_state(root, state)
        errors = readiness(root, state, task)
        if errors:
            raise WorkflowError('\n'.join(errors))
        task['phase'] = 'ready'
        save_task(root, task, '当前代码的配置内检查与所需审查已通过；不代表发布授权。')
    elif args.action in ('release', 'finish'):
        if args.action == 'finish':
            errors = readiness(root, state, task)
            if errors:
                raise WorkflowError('\n'.join(errors))
        save_task(root, task, ('完成归档：' if args.action == 'finish' else '未完成归档：') + args.note)
        archive = root / '.workflow/runtime/archive' / f"{task['id']}-{time.time_ns()}.json"
        atomic(archive, json.dumps(state, ensure_ascii=False, indent=2))
        (root / '.workflow/runtime/active.json').unlink()
        return {'archived': task['id'], 'completed': args.action == 'finish'}
    save_state(root, state)
    return {'task': task['id'], 'phase': task['phase'], 'owner': state.get('owner')}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    sub = p.add_subparsers(dest='action', required=True)
    start = sub.add_parser('start')
    start.add_argument('id')
    start.add_argument('--goal', required=True)
    start.add_argument('--accept', action='append', required=True)
    start.add_argument('--allow', action='append', required=True)
    start.add_argument('--profile', help='project.json 只有一个 profile 时可省略')
    start.add_argument('--kind', choices=('feature', 'maintenance'), default='feature')
    start.add_argument('--no-review', action='store_true', help='only for low-risk tasks; recorded in task contract')
    for name in ('check', 'syntax', 'selfcheck', 'status', 'brief', 'doctor', 'snapshot', 'verify', 'ready'):
        sub.add_parser(name)
    phase = sub.add_parser('phase')
    phase.add_argument('phase', choices=PHASES[:-1])
    phase.add_argument('--note', required=True)
    claim = sub.add_parser('claim')
    claim.add_argument('owner')
    handoff = sub.add_parser('handoff')
    handoff.add_argument('--note', required=True)
    handoff.add_argument('--next', action='append', required=True)
    handoff.add_argument('--blocker', action='append', default=[])
    for name in ('release', 'finish'):
        sub.add_parser(name).add_argument('--note', required=True)
    evidence = sub.add_parser('evidence')
    evidence.add_argument('--criterion', type=int, required=True)
    kind = evidence.add_mutually_exclusive_group(required=True)
    kind.add_argument('--check')
    kind.add_argument('--manual', action='store_true')
    evidence.add_argument('--result', choices=('pass', 'fail'))
    evidence.add_argument('--note', required=True)
    review = sub.add_parser('review')
    review.add_argument('--reviewer', required=True)
    review.add_argument('--fingerprint', required=True, help='snapshot returned by the reviewer for the version actually read')
    review.add_argument('--result', choices=('pass', 'fail'), required=True)
    review.add_argument('--note', required=True)
    return p


def main():
    args = parser().parse_args()
    root = args.root.resolve()
    if args.action == 'verify':
        def interrupt(signum, frame):
            raise KeyboardInterrupt(f'验证被信号 {signum} 中断')
        signal.signal(signal.SIGTERM, interrupt)
    try:
        # Validation commands may call read-only checks while verify holds the mutation lock.
        with nullcontext() if args.action in READ_ONLY else lock(root):
            result = perform(root, args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(args.action == 'doctor' and not result['passed'])
    except KeyboardInterrupt:
        print(json.dumps({'error': '验证被中断；本批次不通过，已清理活动检查进程'}, ensure_ascii=False), file=sys.stderr)
        return 130
    except (WorkflowError, OSError, ValueError, SyntaxError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
