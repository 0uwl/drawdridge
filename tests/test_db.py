from sqlalchemy import text

from drawbridge import create_app
from drawbridge.db import _database_url, get_session
from drawbridge.models import Setting, User


def test_init_db_seeds_log_retention_from_config(app):
    with app.app_context():
        session = get_session()
        setting = session.get(Setting, 'log_retention_days')

        assert setting is not None
        assert setting.value == app.config['LOG_RETENTION_DAYS']


def test_init_db_bootstraps_exactly_one_admin_user(app):
    with app.app_context():
        session = get_session()
        admins = session.query(User).filter_by(username='admin').all()

        assert len(admins) == 1
        assert admins[0].role == 'admin'
        assert admins[0].auth_source == 'local'
        assert admins[0].password_hash


def test_admin_bootstrap_password_is_printed_once(tmp_path, capsys):
    # built directly (not via the `app` fixture) so the bootstrap print
    # happens during this test's capsys-captured call phase, not fixture setup
    create_app({'TESTING': True, 'DATABASE_PATH': str(tmp_path / 'drawbridge.db')})

    assert "created initial admin user 'admin'" in capsys.readouterr().out


def test_init_db_does_not_rebootstrap_an_existing_database(tmp_path, capsys):
    db_path = str(tmp_path / 'drawbridge.db')

    create_app({'TESTING': True, 'DATABASE_PATH': db_path})
    capsys.readouterr()  # discard the first run's printed password

    app2 = create_app({'TESTING': True, 'DATABASE_PATH': db_path})

    assert "created initial admin user" not in capsys.readouterr().out
    with app2.app_context():
        session = get_session()
        assert session.query(User).filter_by(username='admin').count() == 1


def test_sqlite_pragmas_are_set_on_connect(app):
    with app.app_context():
        session = get_session()
        journal_mode = session.execute(text('PRAGMA journal_mode')).scalar()
        busy_timeout = session.execute(text('PRAGMA busy_timeout')).scalar()

        assert journal_mode == 'wal'
        assert busy_timeout == app.config['SQLITE_BUSY_TIMEOUT_MS']


def test_database_url_wraps_a_bare_filesystem_path():
    assert _database_url('/tmp/drawbridge.db') == 'sqlite:////tmp/drawbridge.db'


def test_database_url_passes_through_an_existing_url():
    url = 'postgresql://user:pass@host/dbname'
    assert _database_url(url) == url
