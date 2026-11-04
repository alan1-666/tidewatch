import clickhouse_connect
import pytest


# 与 docker-compose.yml 中的本地开发账号一致。
@pytest.mark.integration
def test_local_clickhouse_reachable():
    client = clickhouse_connect.get_client(host='127.0.0.1', port=8123, username='tidewatch',
                                           password='tidewatch', database='tidewatch')
    assert client.command('SELECT 1') == 1
