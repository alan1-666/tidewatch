"""研究输入的快照与实验清单：让一次实验用了哪份数据、做了哪些尝试可以事后重读和核对。

快照与清单都按内容哈希命名（内容寻址），写入后不改：补数或改参数只会产生新的 id，旧实验仍能读回原输入。
这解决的是"可复现"；"当时能否使用这份数据"由时点约定负责，两者分开验收。
"""
import hashlib
import io
import json
from pathlib import Path

import polars as pl

from tidewatch.binance_vision import _atomic_write

MANIFEST_FIELDS = ('snapshot', 'definition', 'time_policy', 'execution', 'trials')


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _write_once(path, data, item_id):
    """原子写入；同名文件已存在时不覆盖，但先校验它的内容，坏文件不能被当作成功。"""
    if path.exists():
        _read_verified(path, item_id)
        return
    _atomic_write(path, data)


def _path(root, kind, item_id):
    """id 只能是 sha256 十六进制串，顺带挡住路径穿越。"""
    if not isinstance(item_id, str) or len(item_id) != 64 or any(c not in '0123456789abcdef' for c in item_id):
        raise ValueError(f'id 应为 64 位小写十六进制：{item_id!r}')
    suffix = '.parquet' if kind == 'snapshots' else '.json'
    return Path(root) / kind / f'{item_id}{suffix}'


def _read_verified(path, item_id):
    if not path.exists():
        raise FileNotFoundError(f'不存在：{path.name}')
    data = path.read_bytes()
    if _sha256(data) != item_id:
        raise ValueError(f'内容与 id 不符，可能被改动：{path.name}')
    return data


def save(frame, root):
    """把 DataFrame 存为快照，返回快照 id（parquet 文件的 sha256）。"""
    buf = io.BytesIO()
    frame.write_parquet(buf)
    data = buf.getvalue()
    snapshot_id = _sha256(data)
    _write_once(_path(root, 'snapshots', snapshot_id), data, snapshot_id)
    return snapshot_id


def load(snapshot_id, root):
    """读回快照并校验内容哈希；文件被改动或不存在时报错，不返回可疑数据。"""
    return pl.read_parquet(_read_verified(_path(root, 'snapshots', snapshot_id), snapshot_id))


def record_experiment(manifest, root):
    """登记实验清单，返回清单 id（规范化 JSON 的 sha256）。

    trials 是全部尝试过的参数或候选，包括落选的：只留胜出者会掩盖选择偏差。
    """
    missing = [k for k in MANIFEST_FIELDS if k not in manifest]
    if missing:
        raise ValueError(f'实验清单缺少字段：{missing}')
    if not isinstance(manifest['trials'], list) or not manifest['trials']:
        raise ValueError('trials 必须是非空列表，记录全部尝试')
    # 引用的快照必须存在且完好，否则清单指向一份读不回的输入。
    _read_verified(_path(root, 'snapshots', manifest['snapshot']), manifest['snapshot'])
    # allow_nan=False：NaN/inf 不是标准 JSON，其他语言读不了，直接报 ValueError。
    data = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    experiment_id = _sha256(data)
    _write_once(_path(root, 'experiments', experiment_id), data, experiment_id)
    return experiment_id


def load_experiment(experiment_id, root):
    return json.loads(_read_verified(_path(root, 'experiments', experiment_id), experiment_id))
