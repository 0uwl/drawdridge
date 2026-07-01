from functools import wraps

from flask import current_app, request
from flask_login import LoginManager, current_user, login_required

from drawbridge.db import get_session
from drawbridge.queries import get_user_by_id
from drawbridge.utils import error_response

login_manager = LoginManager()


def admin_required(f):
    """Restricts access to admin-role operators. Stacks on top of
    @login_required — an unauthenticated caller still gets the standard 401,
    not a 403, since role isn't known until identity is."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != 'admin':
            return error_response('Admin role required', 'forbidden', code=403, silent=True)
        return f(*args, **kwargs)
    return decorated


def kea_endpoint(f):
    """Restricts access to Kea-facing endpoints (e.g. /api/lease-event).

    Local callers (127.0.0.1, ::1) are always allowed — same-host Kea needs
    no key. Non-local callers must present a matching Bearer token via
    KEA_HOOK_API_KEY; if the key is unset in config, non-local requests are
    rejected outright (fail closed rather than silently open)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_app.config.get('KEA_SKIP_AUTH'):
            return f(*args, **kwargs)

        if request.remote_addr in ('127.0.0.1', '::1'):
            return f(*args, **kwargs)

        api_key = current_app.config.get('KEA_HOOK_API_KEY')
        if not api_key:
            return error_response('Forbidden', 'forbidden', code=403, silent=True)

        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer ') or auth[7:] != api_key:
            return error_response('Forbidden', 'forbidden', code=403, silent=True)

        return f(*args, **kwargs)
    return decorated


def init_login_manager(app):
    """Registers Flask-Login against this app. Called once per worker from
    create_app(), same lifecycle as init_db(app) in drawbridge/db.py."""
    login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id: str):
    return get_user_by_id(get_session(), int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    """Drawbridge is a JSON API behind a Vue SPA, not server-rendered pages
    — override Flask-Login's default redirect-to-login-view behavior with
    the standard error envelope. The SPA's axios interceptor (alpha.md step
    8) handles redirecting to /login on a 401."""
    return error_response('Authentication required', 'unauthorized', code=401, silent=True)
