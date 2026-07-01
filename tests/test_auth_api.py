import pytest
from werkzeug.security import generate_password_hash

from drawbridge.db import get_session
from drawbridge.models import User


PASSWORD = 'test-password-123'


@pytest.fixture()
def user(app):
    with app.app_context():
        session = get_session()
        u = User(
            username='operator',
            role='operator',
            auth_source='local',
            password_hash=generate_password_hash(PASSWORD),
        )
        session.add(u)
        session.commit()
    return u


@pytest.fixture()
def saml_user(app):
    with app.app_context():
        session = get_session()
        u = User(
            username='saml-operator',
            role='operator',
            auth_source='saml',
            password_hash=None,
        )
        session.add(u)
        session.commit()
    return u


@pytest.fixture()
def logged_in_client(app, user, client):
    client.post('/api/auth/login', json={'username': user.username, 'password': PASSWORD})
    return client


# POST /api/auth/login

def test_login_returns_200_and_user_payload_on_correct_credentials(client, user):
    response = client.post('/api/auth/login', json={'username': user.username, 'password': PASSWORD})
    assert response.status_code == 200
    payload = response.get_json()['payload']
    assert payload['username'] == user.username
    assert payload['role'] == 'operator'
    assert payload['auth_source'] == 'local'
    assert 'id' in payload


def test_login_returns_401_on_wrong_password(client, user):
    response = client.post('/api/auth/login', json={'username': user.username, 'password': 'wrong'})
    assert response.status_code == 401
    assert response.get_json()['success'] is False


def test_login_returns_401_on_unknown_username(client):
    response = client.post('/api/auth/login', json={'username': 'nobody', 'password': 'x'})
    assert response.status_code == 401


def test_login_returns_401_for_saml_only_account(client, saml_user):
    response = client.post('/api/auth/login', json={'username': saml_user.username, 'password': 'anything'})
    assert response.status_code == 401


def test_login_returns_400_when_username_missing(client):
    response = client.post('/api/auth/login', json={'password': PASSWORD})
    assert response.status_code == 400


def test_login_returns_400_when_password_missing(client):
    response = client.post('/api/auth/login', json={'username': 'operator'})
    assert response.status_code == 400


def test_login_returns_400_on_empty_body(client):
    response = client.post('/api/auth/login', json={})
    assert response.status_code == 400


def test_login_updates_last_login_at(app, client, user):
    client.post('/api/auth/login', json={'username': user.username, 'password': PASSWORD})
    with app.app_context():
        updated = get_session().get(User, user.id)
        assert updated.last_login_at is not None


# POST /api/auth/logout

def test_logout_returns_200_when_logged_in(logged_in_client):
    response = logged_in_client.post('/api/auth/logout')
    assert response.status_code == 200
    assert response.get_json()['success'] is True


def test_logout_returns_401_when_not_logged_in(client):
    response = client.post('/api/auth/logout')
    assert response.status_code == 401


def test_logout_ends_session(logged_in_client):
    logged_in_client.post('/api/auth/logout')
    response = logged_in_client.get('/api/auth/me')
    assert response.status_code == 401


# GET /api/auth/me

def test_me_returns_current_user_when_logged_in(logged_in_client, user):
    response = logged_in_client.get('/api/auth/me')
    assert response.status_code == 200
    payload = response.get_json()['payload']
    assert payload['username'] == user.username


def test_me_returns_401_when_not_logged_in(client):
    response = client.get('/api/auth/me')
    assert response.status_code == 401
