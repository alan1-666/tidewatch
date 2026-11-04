"""Acceptance-to-evidence links. These validate provenance, not semantic correctness."""
import time

from policy import WorkflowError, fingerprint


def acceptance_rows(root, state, task):
    stamp = fingerprint(root, task)
    verification = state.get('verification', {})
    rows = []
    for number, criterion in enumerate(task['acceptance'], 1):
        item = state.get('acceptance_evidence', {}).get(str(number))
        status = 'missing'
        if item:
            if item.get('fingerprint') != stamp:
                status = 'stale'
            elif item.get('kind') == 'check':
                checks = verification.get('checks', [])
                valid = (verification.get('passed') and verification.get('fingerprint') == stamp
                         and item.get('run_id') == verification.get('run_id')
                         and any(c['name'] == item['check'] and c['exit_code'] == 0 for c in checks))
                status = 'passed' if valid else 'stale'
            else:
                status = 'passed' if item.get('result') == 'pass' else 'failed'
        rows.append({'number': number, 'criterion': criterion, 'status': status, 'evidence': item})
    return rows


def acceptance_errors(root, state, task):
    labels = {'missing': '缺少证据', 'stale': '证据已过期', 'failed': '人工验收失败'}
    return [f"验收 #{row['number']} {labels[row['status']]}: {row['criterion']}"
            for row in acceptance_rows(root, state, task) if row['status'] != 'passed']


def record(root, state, task, args):
    if not 1 <= args.criterion <= len(task['acceptance']):
        raise WorkflowError('验收编号超出任务条件范围')
    if not args.note.strip():
        raise WorkflowError('证据说明不可为空：指出用例、观察方式或日志位置')
    stamp = fingerprint(root, task)
    item = {'fingerprint': stamp, 'note': args.note, 'recorded_at': time.time(),
            'recorded_by': state.get('owner'), 'kind': 'check' if args.check else 'manual'}
    if args.check:
        verification = state.get('verification', {})
        if not verification.get('passed') or verification.get('fingerprint') != stamp:
            raise WorkflowError('先获得当前代码的成功验证，才能绑定检查证据')
        check = next((c for c in verification.get('checks', []) if c['name'] == args.check), None)
        if not check or check['exit_code'] != 0:
            raise WorkflowError('引用的检查不存在或未通过')
        if args.result:
            raise WorkflowError('自动检查的结果来自退出码，不接受手填 --result')
        item.update(check=args.check, run_id=verification.get('run_id'), result='pass', log=check['log'])
    else:
        if args.result not in ('pass', 'fail'):
            raise WorkflowError('人工证据必须显式指定 --result pass 或 fail')
        item['result'] = args.result
    state.setdefault('acceptance_evidence', {})[str(args.criterion)] = item
    return item
