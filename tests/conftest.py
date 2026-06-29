import pytest

from drawbridge import create_app


@pytest.fixture()
def app(tmp_path):
    """Per docs/testing.md: tests use a temporary SQLite file, never the
    production /app/data/drawbridge.db. Ported from the ZTP 1.0 backend's app
    fixture pattern (testing/conftest.py), swapped from Redis-clearing to a
    tmp_path DB file.
    """
    config_dict = {
        'TESTING': True,
        'DATABASE_PATH': str(tmp_path / 'drawbridge-test.db'),
    }

    app = create_app(config_dict)

    yield app


@pytest.fixture()
def client(app):
    return app.test_client()
