import pytest

from drawbridge import create_app
from drawbridge.db import get_session


@pytest.fixture()
def app(tmp_path):
    """Tests use a temporary SQLite file, never the
    production /app/data/drawbridge.db
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


@pytest.fixture()
def session(app):
    """Request-scoped session, same lifecycle as a real request: opened on
    first use within the app context, closed when the context pops."""
    with app.app_context():
        yield get_session()
