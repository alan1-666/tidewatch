import uuid

import clickhouse_connect
import pytest

# 与 docker-compose.yml 中的本地开发账号一致。
CONN = dict(host='127.0.0.1', port=8123, username='tidewatch', password='tidewatch')


@pytest.fixture
def client():
    """每个用例一个临时库，结束即删，不碰 tidewatch 库里的数据。"""
    name = f'tidewatch_test_{uuid.uuid4().hex[:12]}'
    admin = clickhouse_connect.get_client(**CONN)
    admin.command(f'CREATE DATABASE {name}')
    try:
        yield clickhouse_connect.get_client(**CONN, database=name)
    finally:
        admin.command(f'DROP DATABASE IF EXISTS {name}')
