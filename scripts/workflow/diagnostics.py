"""Read-only environment checks. No installs, network probes, or client trust writes."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

from adapters import expected
from policy import config


def runnable(root, command):
    # verify 以 cwd=root 启动检查，带路径的命令（如 .venv/bin/python）须按仓库根解析，不能看 doctor 的当前目录。
    if '/' in command:
        path = root / command
        return path.is_file() and os.access(path, os.X_OK)
    return shutil.which(command) is not None


def doctor(root):
    _, project = config(root)
    checks = []
    def add(name, passed, detail):
        checks.append({'name': name, 'passed': passed, 'detail': detail})

    add('python', sys.version_info >= (3, 11), sys.version.split()[0])
    # 业务运行时（Node、Go 等）只由 project.json 的检查命令决定，见 configured-executables。
    git = shutil.which('git')
    if git:
        result = subprocess.run([git, 'rev-parse', '--show-toplevel'], cwd=root,
                                capture_output=True, text=True, timeout=5)
        actual = result.stdout.strip()
        add('repository-root', result.returncode == 0 and Path(actual).resolve() == root,
            actual or '不是独立 Git 仓库，Codex Hook 无法按当前配置定位')
    else:
        add('repository-root', False, '缺少 Git')
    missing_commands = sorted({c['argv'][0] for checks_ in project['profiles'].values() for c in checks_
                               if c['argv'][0] != '{python}' and not runnable(root, c['argv'][0])})
    add('configured-executables', not missing_commands, missing_commands)
    drift = [path for path, content in expected(root).items()
             if not (root / path).exists() or (root / path).read_text() != content]
    add('adapter-consistency', not drift, drift)
    invalid = []
    for path in (root / '.codex/agents').glob('*.toml'):
        try:
            data = tomllib.loads(path.read_text())
            if not all(data.get(key) for key in ('name', 'description', 'developer_instructions')):
                invalid.append(path.name)
        except ValueError:
            invalid.append(path.name)
    add('agent-toml', not invalid, invalid)
    return {'passed': all(c['passed'] for c in checks), 'checks': checks,
            'clients': {client: {'cli_available': bool(shutil.which(client)), 'live_hook_status': 'unverified'}
                        for client in ('codex', 'claude')},
            'limits': ['静态配置存在不代表客户端已加载或信任',
                       '不运行客户端、不安装工具、不读取密钥；真实触发需新会话逐项验收']}
