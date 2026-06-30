import pytest
from flask_login import login_required

from drawbridge import create_app
from drawbridge.auth import load_user
from drawbridge.db import get_session
from drawbridge import queries


def test_load_user_returns_matching_user(app):
    with app.app_context():
        admin = queries.get_user_by_username(get_session(), 'admin')

        assert load_user(str(admin.id)) is admin


def test_load_user_returns_none_for_unknown_id(app):
    with app.app_context():
        assert load_user('999999') is None


def test_testing_app_gets_an_ephemeral_secret_key(app):
    assert app.config['SECRET_KEY']


def test_secret_key_required_outside_testing(tmp_path, monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)

    with pytest.raises(RuntimeError):
        create_app({'TESTING': False, 'DATABASE_PATH': str(tmp_path / 'drawbridge.db')})


def test_protected_route_without_session_returns_json_401(app):
    @app.route('/_test/protected')
    @login_required
    def _protected():
        return 'ok'

    client = app.test_client()
    response = client.get('/_test/protected')

    assert response.status_code == 401
    assert response.get_json()['success'] is False
