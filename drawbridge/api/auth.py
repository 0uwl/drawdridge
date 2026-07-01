from flask import Blueprint, request
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from drawbridge.db import get_session
from drawbridge.models import utcnow_iso
from drawbridge.queries import get_user_by_username
from drawbridge.utils import error_response, success_response


def create_blueprint():
    bp = Blueprint('auth', __name__)

    @bp.post('/auth/login')
    def login():
        data = request.get_json(silent=True) or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return error_response('Username and password are required', 'invalid_request', code=400)

        session = get_session()
        user = get_user_by_username(session, username)

        # Treat "user not found", "SAML-only account" (no password_hash), and
        # "wrong password" identically — no username enumeration via error text.
        if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
            return error_response('Invalid credentials', 'unauthorized', code=401, silent=True)

        user.last_login_at = utcnow_iso()
        session.commit()

        login_user(user)
        return success_response('Logged in', payload=_user_payload(user))

    @bp.post('/auth/logout')
    @login_required
    def logout():
        logout_user()
        return success_response('Logged out')

    @bp.get('/auth/me')
    @login_required
    def me():
        return success_response('Authenticated', payload=_user_payload(current_user))

    return bp


def _user_payload(user):
    return {
        'id': user.id,
        'username': user.username,
        'role': user.role,
        'auth_source': user.auth_source,
    }
