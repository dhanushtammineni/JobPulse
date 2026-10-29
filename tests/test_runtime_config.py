from unittest.mock import patch

import pytest
import config
from fastapi.testclient import TestClient
import api


def test_database_settings_fail_early_without_exposing_values(monkeypatch):
    monkeypatch.setattr(config, 'DB_HOST', None)
    with pytest.raises(ValueError, match='Missing database settings: DB_HOST'):
        config.database_options()


@pytest.mark.parametrize('port', ['0', '65536', 'not-a-port'])
def test_invalid_database_port(monkeypatch, port):
    for key, value in {'DB_HOST': 'localhost', 'DB_NAME': 'test', 'DB_USER': 'test', 'DB_PORT': port}.items():
        monkeypatch.setattr(config, key, value)
    with pytest.raises(ValueError, match='DB_PORT'):
        config.database_options()


def test_liveness_does_not_require_database():
    with patch('api.assert_current', side_effect=AssertionError('must not connect')):
        assert TestClient(api.app).get('/health/live').json() == {'status': 'ok'}
