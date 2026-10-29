"""Opt-in tests create and drop only random, dedicated jobpulse_test_* databases."""
import os
from uuid import uuid4

import psycopg2
from psycopg2 import sql
import pytest

import config


@pytest.fixture
def database(monkeypatch):
    if os.getenv('JOBPULSE_TEST_DATABASES') != '1':
        pytest.skip('Set JOBPULSE_TEST_DATABASES=1 with a disposable PostgreSQL admin connection')
    options = config.database_options()
    admin = psycopg2.connect(**{**options, 'dbname': 'postgres'})
    admin.autocommit = True
    name = 'jobpulse_test_' + uuid4().hex
    try:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        monkeypatch.setattr(config, 'DB_NAME', name)
        connection = psycopg2.connect(**config.database_options())
        try:
            yield connection
        finally:
            connection.close()
    finally:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))
        admin.close()
