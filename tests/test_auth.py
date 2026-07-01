import pytest
from flask_login import login_required
from werkzeug.security import generate_password_hash

from drawbridge import create_app
from drawbridge.auth import admin_required, kea_endpoint, load_user
from drawbridge.db import get_session
from drawbridge.models import User
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


# admin_required decorator — tests use a minimal /_test/admin route
# registered on the per-test app fixture so there are no cross-test route
# conflicts.

PASSWORD = 'test-password-123'


def _register_admin_test_route(app):
    @app.route('/_test/admin')
    @admin_required
    def _admin():
        return 'ok'
    return app.test_client()


def _create_and_login(app, client, *, role):
    with app.app_context():
        session = get_session()
        session.add(User(username=f'test-{role}', role=role, auth_source='local', password_hash=generate_password_hash(PASSWORD)))
        session.commit()
    client.post('/api/v1/auth/login', json={'username': f'test-{role}', 'password': PASSWORD})


def test_admin_required_returns_401_when_not_logged_in(app):
    client = _register_admin_test_route(app)
    response = client.get('/_test/admin')
    assert response.status_code == 401


def test_admin_required_returns_403_for_operator(app):
    client = _register_admin_test_route(app)
    _create_and_login(app, client, role='operator')
    response = client.get('/_test/admin')
    assert response.status_code == 403
    assert response.get_json()['success'] is False


def test_admin_required_allows_admin(app):
    client = _register_admin_test_route(app)
    _create_and_login(app, client, role='admin')
    response = client.get('/_test/admin')
    assert response.status_code == 200


# kea_endpoint decorator — tests use a minimal /_test/kea route registered
# on the per-test app fixture so there are no cross-test route conflicts.

def _register_kea_test_route(app):
    @app.route('/_test/kea', methods=['POST'])
    @kea_endpoint
    def _kea():
        return 'ok'
    return app.test_client()


def test_kea_endpoint_allows_localhost_without_api_key(app):
    client = _register_kea_test_route(app)
    response = client.post('/_test/kea')  # test client defaults to 127.0.0.1
    assert response.status_code == 200


def test_kea_endpoint_allows_ipv6_loopback_without_api_key(app):
    client = _register_kea_test_route(app)
    response = client.post('/_test/kea', environ_overrides={'REMOTE_ADDR': '::1'})
    assert response.status_code == 200


def test_kea_endpoint_blocks_non_local_when_no_api_key_configured(app):
    client = _register_kea_test_route(app)
    response = client.post('/_test/kea', environ_overrides={'REMOTE_ADDR': '10.0.0.5'})
    assert response.status_code == 403
    assert response.get_json()['success'] is False


def test_kea_endpoint_allows_non_local_with_correct_bearer_token(app):
    app.config['KEA_HOOK_API_KEY'] = 'correct-key'
    client = _register_kea_test_route(app)
    response = client.post(
        '/_test/kea',
        environ_overrides={'REMOTE_ADDR': '10.0.0.5'},
        headers={'Authorization': 'Bearer correct-key'},
    )
    assert response.status_code == 200


def test_kea_endpoint_blocks_non_local_with_wrong_bearer_token(app):
    app.config['KEA_HOOK_API_KEY'] = 'correct-key'
    client = _register_kea_test_route(app)
    response = client.post(
        '/_test/kea',
        environ_overrides={'REMOTE_ADDR': '10.0.0.5'},
        headers={'Authorization': 'Bearer wrong-key'},
    )
    assert response.status_code == 403


def test_kea_endpoint_blocks_non_local_with_missing_authorization_header(app):
    app.config['KEA_HOOK_API_KEY'] = 'correct-key'
    client = _register_kea_test_route(app)
    response = client.post('/_test/kea', environ_overrides={'REMOTE_ADDR': '10.0.0.5'})
    assert response.status_code == 403


def test_kea_endpoint_allows_non_local_when_skip_auth_is_set(app):
    app.config['KEA_SKIP_AUTH'] = True
    client = _register_kea_test_route(app)
    response = client.post('/_test/kea', environ_overrides={'REMOTE_ADDR': '10.0.0.5'})
    assert response.status_code == 200


def test_kea_endpoint_blocks_non_local_with_malformed_authorization_header(app):
    app.config['KEA_HOOK_API_KEY'] = 'correct-key'
    client = _register_kea_test_route(app)
    response = client.post(
        '/_test/kea',
        environ_overrides={'REMOTE_ADDR': '10.0.0.5'},
        headers={'Authorization': 'correct-key'},  # missing "Bearer " prefix
    )
    assert response.status_code == 403
