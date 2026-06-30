from flask_login import LoginManager

from drawbridge.db import get_session
from drawbridge.queries import get_user_by_id
from drawbridge.utils import error_response

login_manager = LoginManager()


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
