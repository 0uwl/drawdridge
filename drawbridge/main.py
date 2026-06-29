import logging
import os

from flask import Flask, jsonify

DATABASE_PATH = '/app/data/drawbridge.db'
SCRIPTS_PATH = '/app/scripts'
KEA_CTRL_URL = 'http://keahost:8081'
KEA_SUBNET_ID = '1'
LEASE_EVENT_TIMEOUT = '2'
LOG_LEVEL = 'INFO'


def create_app(config_dict: dict = {}):
    """Flask app factory. Ported from the ZTP 1.0 backend's create_app() —
    config loading, gunicorn logger wiring, and the /health check carry over
    unchanged. Blueprint registration is intentionally empty: lease.py,
    devices.py, and scripts.py (see docs/api.md) are new for
    Drawbridge and still need to be designed/written.
    """

    app = Flask(__name__)

    # Configuration (env vars per docs/deployment.md, overridable via config_dict for tests)
    app.config['DATABASE_PATH'] = os.getenv('DATABASE_PATH', DATABASE_PATH)
    app.config['SCRIPTS_PATH'] = os.getenv('SCRIPTS_PATH', SCRIPTS_PATH)
    app.config['KEA_CTRL_URL'] = os.getenv('KEA_CTRL_URL', KEA_CTRL_URL)
    app.config['KEA_SUBNET_ID'] = os.getenv('KEA_SUBNET_ID', KEA_SUBNET_ID)
    app.config['LEASE_EVENT_TIMEOUT'] = float(os.getenv('LEASE_EVENT_TIMEOUT', LEASE_EVENT_TIMEOUT))
    app.config['LOG_LEVEL'] = os.getenv('LOG_LEVEL', LOG_LEVEL)
    app.config['TESTING'] = os.getenv('TESTING', False)

    if config_dict:
        app.config.update(config_dict)

    if app.testing:
        app.config['LOG_LEVEL'] = 'DEBUG'

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

    # TODO(drawbridge): initialize SQLite schema (see docs/database.md)
    # with app.app_context():
    #     init_db(app)

    app.logger.info(f"Finished creating Drawbridge app instance with log level {app.config['LOG_LEVEL']}")

    return app
