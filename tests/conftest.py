import pytest

from drawbridge import create_app


@pytest.fixture()
def app(tmp_path):
    """Tests use a temporary SQLite file, never the
    production /app/drawbridge.db
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
