import os
from datetime import datetime, timezone

import polars as pl
import pytest

from tidewatch import snapshot

FRAME = pl.DataFrame({'ts': [datetime(2024, 1, 2, tzinfo=timezone.utc)], 'symbol': ['AUSDT'], 'close': [1.5]})


def manifest(snap, **changes):
    return {'snapshot': snap, 'definition': {'factor': 'momentum', 'window': 5}, 'time_policy': {'lag': 1},
            'execution': {'taker_bp': 5, 'slippage_bp': 0}, 'trials': [{'window': 5}, {'window': 10}], **changes}


def test_snapshot_round_trips_and_is_content_addressed(tmp_path):
    sid = snapshot.save(FRAME, tmp_path)
    assert snapshot.load(sid, tmp_path).equals(FRAME)
    assert dict(snapshot.load(sid, tmp_path).schema) == dict(FRAME.schema)  # 时区等类型不丢
    assert snapshot.save(FRAME, tmp_path) == sid  # 同内容同 id，不新增文件
    other = snapshot.save(FRAME.with_columns(pl.lit(1.6).alias('close')), tmp_path)  # 补数 → 新快照
    assert other != sid and snapshot.load(sid, tmp_path).equals(FRAME)  # 旧快照仍可读
    assert len(list((tmp_path / 'snapshots').iterdir())) == 2


def test_snapshot_load_rejects_tampered_missing_or_bad_id(tmp_path):
    sid = snapshot.save(FRAME, tmp_path)
    path = tmp_path / 'snapshots' / f'{sid}.parquet'
    path.write_bytes(path.read_bytes() + b'x')
    with pytest.raises(ValueError):
        snapshot.load(sid, tmp_path)
    with pytest.raises(FileNotFoundError):
        snapshot.load('0' * 64, tmp_path)
    for bad in ('../x', 'A' * 64, sid[:10]):
        with pytest.raises(ValueError):
            snapshot.load(bad, tmp_path)


def test_existing_snapshot_is_not_overwritten_and_is_verified(tmp_path):
    sid = snapshot.save(FRAME, tmp_path)
    path = tmp_path / 'snapshots' / f'{sid}.parquet'
    path.write_bytes(b'tampered')
    with pytest.raises(ValueError):  # 同名坏文件：报错而不是假装成功
        snapshot.save(FRAME, tmp_path)
    assert path.read_bytes() == b'tampered'  # 也不改写
    with pytest.raises(ValueError):  # 清单不能引用坏快照
        snapshot.record_experiment(manifest(sid), tmp_path)


def test_failed_write_leaves_nothing_behind(tmp_path, monkeypatch):
    def boom(src, dst):
        raise OSError('disk full')
    monkeypatch.setattr(os, 'replace', boom)  # 在改名这一步失败
    with pytest.raises(OSError):
        snapshot.save(FRAME, tmp_path)
    assert list((tmp_path / 'snapshots').iterdir()) == []  # 目标与临时文件都不存在


def test_experiment_manifest_is_immutable_and_revisions_get_new_ids(tmp_path):
    s1 = snapshot.save(FRAME, tmp_path)
    e1 = snapshot.record_experiment(manifest(s1), tmp_path)
    assert snapshot.record_experiment(manifest(s1), tmp_path) == e1  # 同一清单同一 id
    # 键顺序不影响 id
    assert snapshot.record_experiment(dict(reversed(list(manifest(s1).items()))), tmp_path) == e1
    s2 = snapshot.save(FRAME.with_columns(pl.lit(1.6).alias('close')), tmp_path)
    e2 = snapshot.record_experiment(manifest(s2), tmp_path)  # 只换输入
    e3 = snapshot.record_experiment(manifest(s1, execution={'taker_bp': 4, 'slippage_bp': 0}), tmp_path)
    assert len({e1, e2, e3}) == 3
    assert snapshot.load_experiment(e1, tmp_path) == manifest(s1)  # 旧清单不变
    assert snapshot.load_experiment(e2, tmp_path)['snapshot'] == s2


def test_experiment_manifest_rejects_incomplete_input(tmp_path):
    s1 = snapshot.save(FRAME, tmp_path)
    full = manifest(s1)
    for field in snapshot.MANIFEST_FIELDS:
        with pytest.raises(ValueError):
            snapshot.record_experiment({k: v for k, v in full.items() if k != field}, tmp_path)
    with pytest.raises(ValueError):  # NaN 不是标准 JSON
        snapshot.record_experiment(manifest(s1, execution={'slippage_bp': float('nan')}), tmp_path)
    for trials in ([], {'window': 5}):
        with pytest.raises(ValueError):
            snapshot.record_experiment(manifest(s1, trials=trials), tmp_path)
    with pytest.raises(FileNotFoundError):
        snapshot.record_experiment(manifest('0' * 64), tmp_path)
    e1 = snapshot.record_experiment(full, tmp_path)
    path = tmp_path / 'experiments' / f'{e1}.json'
    path.write_text(path.read_text().replace('momentum', 'reversal'))
    with pytest.raises(ValueError):
        snapshot.load_experiment(e1, tmp_path)
