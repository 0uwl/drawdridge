import logging
import os
import secrets
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from drawbridge.auth import init_login_manager
from drawbridge.db import init_db

DATABASE_PATH = '/app/data/drawbridge.db'
SCRIPTS_PATH = '/app/scripts'
KEA_CTRL_URL = 'http://keahost:8081'
KEA_SUBNET_ID = '1'
LEASE_EVENT_TIMEOUT = '2'
LOG_LEVEL = 'INFO'
SQLITE_BUSY_TIMEOUT_MS = '1000'
LOG_RETENTION_DAYS = '30'
KEA_HOOK_API_KEY = None
KEA_SKIP_AUTH = False

# Built Vue SPA (frontend/, baked in at image build time — see
# docs/frontend.md). static_folder is disabled below so Flask doesn't
# register its own implicit static route on the same URL pattern as the
# catch-all; this path is used directly instead.
FRONTEND_DIST = Path(__file__).resolve().parent / 'static'


def create_app(config_dict: dict = {}):
    """Flask app factory
    """

    app = Flask(__name__, static_folder=None)

    # Configuration (env vars per docs/deployment.md, overridable via config_dict for tests)
    app.config['DATABASE_PATH'] = os.getenv('DATABASE_PATH', DATABASE_PATH)
    app.config['SCRIPTS_PATH'] = os.getenv('SCRIPTS_PATH', SCRIPTS_PATH)
    app.config['KEA_CTRL_URL'] = os.getenv('KEA_CTRL_URL', KEA_CTRL_URL)
    app.config['KEA_SUBNET_ID'] = os.getenv('KEA_SUBNET_ID', KEA_SUBNET_ID)
    app.config['LEASE_EVENT_TIMEOUT'] = float(os.getenv('LEASE_EVENT_TIMEOUT', LEASE_EVENT_TIMEOUT))
    app.config['LOG_LEVEL'] = os.getenv('LOG_LEVEL', LOG_LEVEL)
    app.config['TESTING'] = os.getenv('TESTING', False)
    app.config['SQLITE_BUSY_TIMEOUT_MS'] = int(os.getenv('SQLITE_BUSY_TIMEOUT_MS', SQLITE_BUSY_TIMEOUT_MS))
    app.config['LOG_RETENTION_DAYS'] = os.getenv('LOG_RETENTION_DAYS', LOG_RETENTION_DAYS)
    app.config['KEA_HOOK_API_KEY'] = os.getenv('KEA_HOOK_API_KEY', KEA_HOOK_API_KEY)
    app.config['KEA_SKIP_AUTH'] = bool(os.getenv('KEA_SKIP_AUTH', ''))
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')  # no default — see check below

    if config_dict:
        app.config.update(config_dict)

    if app.testing:
        app.config['LOG_LEVEL'] = 'DEBUG'

    if app.config['SECRET_KEY'] is None:
        if app.testing:
            # Ephemeral, this-process-only key. Fine for tests (one app
            # instance, no other worker needs to agree on it). Production
            # must set SECRET_KEY explicitly: each Gunicorn worker calls
            # create_app() independently post-fork (see db.py), so without
            # a shared env var every worker would sign session cookies with
            # a different key and sessions would randomly invalidate
            # depending on which worker handles the next request.
            app.config['SECRET_KEY'] = secrets.token_hex(32)
        else:
            raise RuntimeError(
                'SECRET_KEY environment variable must be set — see docs/deployment.md'
            )

    # Logger — gunicorn owns the handlers in production
    gunicorn_logger = logging.getLogger('gunicorn.error')
    gunicorn_logger.setLevel(app.config['LOG_LEVEL'])
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

    @app.route('/health')
    def health_check():
        return jsonify({'status': 'healthy'}), 200

    # TODO(drawbridge): register blueprints once written, e.g.
    # from drawbridge.api import lease, devices, scripts
    # app.register_blueprint(lease.create_blueprint(), url_prefix='/api')
    # app.register_blueprint(devices.create_blueprint(), url_prefix='/api/devices')
    # app.register_blueprint(scripts.create_blueprint(), url_prefix='/scripts')

    init_login_manager(app)

    with app.app_context():
        init_db(app)

    # Serve the built Vue SPA. Registered last, but route order doesn't
    # matter here — Werkzeug matches literal/blueprint routes like
    # /api/lease-event ahead of this catch-all regardless of registration
    # order. Falls back to index.html for any unrecognised path so Vue
    # Router's client-side routes resolve on a hard refresh (see
    # docs/frontend.md).
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_frontend(path):
        target = FRONTEND_DIST / path
        if path and target.is_file():
            return send_from_directory(FRONTEND_DIST, path)
        return send_from_directory(FRONTEND_DIST, 'index.html')

    app.logger.info(f"Finished creating Drawbridge app instance with log level {app.config['LOG_LEVEL']}")

    return app
