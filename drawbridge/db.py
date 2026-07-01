import secrets
import string
from pathlib import Path

from flask import current_app, g
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from werkzeug.security import generate_password_hash

from drawbridge.models import Base, Setting, User

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD_LENGTH = 12


def init_db(app):
    """Create this worker's Engine/sessionmaker and prepare the schema.

    Must be called inside create_app(), after Gunicorn forks each worker —
    never at module import time, since a sqlite3 connection shared across
    fork() corrupts the database (see docs/decisions.md).
    """
    engine = _create_engine(app)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.extensions['db_engine'] = engine
    app.extensions['db_session_factory'] = session_factory

    is_first_run = _is_first_run(engine, app.config['DATABASE_PATH'])

    Base.metadata.create_all(engine)

    with session_factory() as session:
        _seed_log_retention(session, app)
        _seed_default_image(session, app)
        _seed_default_config_file(session, app)
        _seed_default_script(session, app)
        if is_first_run:
            _bootstrap_admin(session)
        session.commit()

    app.teardown_appcontext(_close_session)


def get_session() -> Session:
    """Request-scoped SQLAlchemy session, opened on first use within the
    current Flask app context and closed by the teardown callback that
    init_db() registers.
    """
    if 'db_session' not in g:
        g.db_session = current_app.extensions['db_session_factory']()
    return g.db_session


def _create_engine(app):
    url = _database_url(app.config['DATABASE_PATH'])
    connect_args = {}

    # check_same_thread=False: the gevent Gunicorn worker class can hand a
    # checked-out connection between greenlets within one process (see
    # docs/database.md, "Concurrency under multiple Gunicorn workers").
    # SQLite-only — meaningless for a client/server dialect.
    if url.startswith('sqlite'):
        connect_args['check_same_thread'] = False

    engine = create_engine(url, connect_args=connect_args)

    if engine.dialect.name == 'sqlite':
        busy_timeout_ms = app.config['SQLITE_BUSY_TIMEOUT_MS']

        @event.listens_for(engine, 'connect')
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute('PRAGMA journal_mode=WAL')
            cursor.execute(f'PRAGMA busy_timeout={busy_timeout_ms}')
            cursor.close()

    return engine


def _database_url(database_path: str) -> str:
    """DATABASE_PATH is a bare filesystem path for alpha's SQLite-only
    deployment, wrapped into a sqlite:/// URL here. A value that's already
    a SQLAlchemy URL (e.g. a future postgresql://...) is passed through
    unchanged — full Postgres support is out of scope for alpha, but
    nothing in this module needs to change to add it later.
    """
    if '://' in database_path:
        return database_path
    return f'sqlite:///{database_path}'


def _is_first_run(engine, database_path: str) -> bool:
    """Whether this is the first time init_db has run against this
    database — gates the admin bootstrap. Per the resolved decision in
    alpha.md, detected via absence of the SQLite file at DATABASE_PATH
    before create_all() runs, not an env var or CLI flag.
    """
    if engine.dialect.name != 'sqlite':
        # Not reachable in alpha (no non-sqlite driver in requirements.txt).
        # A future Postgres backend needs its own first-run signal here —
        # e.g. inspect(engine).has_table('users') before create_all(),
        # which works for both dialects and wouldn't need a file to check.
        return False
    return not Path(database_path).exists()


def _seed_log_retention(session, app):
    if session.get(Setting, 'log_retention_days') is None:
        session.add(Setting(
            key='log_retention_days',
            value=app.config['LOG_RETENTION_DAYS'],
        ))


def _seed_default_image(session, app):
    value = app.config['DEFAULT_IMAGE']
    if value is not None and session.get(Setting, 'default_image') is None:
        session.add(Setting(key='default_image', value=value))


def _seed_default_config_file(session, app):
    value = app.config['DEFAULT_CONFIG_FILE']
    if value is not None and session.get(Setting, 'default_config_file') is None:
        session.add(Setting(key='default_config_file', value=value))


def _seed_default_script(session, app):
    value = app.config['DEFAULT_SCRIPT']
    if value is not None and session.get(Setting, 'default_script') is None:
        session.add(Setting(key='default_script', value=value))


def _bootstrap_admin(session):
    alphabet = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(alphabet) for _ in range(ADMIN_PASSWORD_LENGTH))

    session.add(User(
        username=ADMIN_USERNAME,
        role='admin',
        auth_source='local',
        password_hash=generate_password_hash(password),
    ))

    print(
        f"Drawbridge: created initial admin user '{ADMIN_USERNAME}', "
        f"password: {password} — record this now, it will not be shown again."
    )


def _close_session(exception=None):
    session = g.pop('db_session', None)
    if session is not None:
        if exception:
            session.rollback()
        session.close()
