# Database

Managed via SQLAlchemy ORM models in `drawbridge/models.py`, against the same
SQLite file at `DATABASE_PATH`. `drawbridge/db.py` owns the `Engine`/
`sessionmaker` and an `init_db(app)` that calls `Base.metadata.create_all()`
on first run.

## Schema

```python
class Device(Base):
    """Operator-managed allowlist entry. Exists from registration through the
    full ZTP lifecycle — not deleted on provisioning so a failed run can be
    retried without re-registration. Operator must explicitly DELETE to remove."""
    __tablename__ = 'devices'

    serial: Mapped[str] = mapped_column(primary_key=True)
    mac: Mapped[str | None]
    description: Mapped[str | None]
    image: Mapped[str | None]        # falls back to default_image Setting on creation
    config_file: Mapped[str | None]  # falls back to default_config_file Setting on creation
    script: Mapped[str | None]       # falls back to default_script Setting on creation
    added_at: Mapped[str]
    added_by: Mapped[str | None]


class ProvisioningSession(Base):
    """Transient record of an in-progress ZTP run. Created when
    /api/lease-event approves a serial; deleted when /api/provision-complete
    fires (success or failure). The Device allowlist row is not touched."""
    __tablename__ = 'provisioning_sessions'

    serial: Mapped[str] = mapped_column(primary_key=True)
    mac: Mapped[str | None]
    ip: Mapped[str | None]
    image: Mapped[str | None]        # set when device reports at provision-complete
    config_file: Mapped[str | None]  # set when device reports at provision-complete
    state: Mapped[str]               # 'lease_approved', 'script_fetched', 'downloading',
                                     # 'updating_software', 'rebooting', 'configuring'
    approved_at: Mapped[str]


class ProvisioningLog(Base):
    """Archival record written when a device completes or fails provisioning
    and its ProvisioningSession row is deleted. Subject to the retention
    policy in Setting; purged once a row outlives it."""
    __tablename__ = 'provisioning_log'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    serial: Mapped[str]
    event: Mapped[str]               # 'provision_complete', 'provision_failed'
    image: Mapped[str | None]
    config_file: Mapped[str | None]
    ip: Mapped[str | None]
    timestamp: Mapped[str]
    detail: Mapped[str | None]


class Setting(Base):
    """Small admin-configurable key/value store. First row of interest:
    key='log_retention_days', value='30' (or 'indefinite')."""
    __tablename__ = 'settings'

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]
    updated_at: Mapped[str]
    updated_by: Mapped[str | None]


class User(Base, UserMixin):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(unique=True)
    email: Mapped[str | None]
    password_hash: Mapped[str | None]   # null for SAML-only operators
    role: Mapped[str]                   # 'admin' or 'operator'
    auth_source: Mapped[str]            # 'local' or 'saml'
    saml_issuer: Mapped[str | None]     # IdP entity ID, set once SAML lands
    saml_subject: Mapped[str | None]    # IdP NameID, set once SAML lands
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[str]
    last_login_at: Mapped[str | None]
```

`auth_source`, `saml_issuer`, and `saml_subject` exist now, ahead of the SAML
work, so that adding SAML later (see [authentication.md](authentication.md))
is additive — no migration to widen the `users` table when it happens.

A request-scoped session is opened per Flask request (e.g. via
`app.teardown_appcontext`) and closed/rolled back at the end of the request,
not held across the `/api/lease-event` call's Kea Control Agent round trip.

## Concurrency under multiple Gunicorn workers

`gunicorn.conf.py` runs `workers = 4` with the `gevent` worker class — four
separate OS processes, each handling many greenlets, all opening connections
to the same `drawbridge.db` file. SQLite allows only one writer at a time
regardless of journal mode, so the goal is to make workers wait their turn
safely instead of failing or corrupting state:

- `PRAGMA journal_mode=WAL` is set on every new connection (a SQLAlchemy
  `connect` event listener in `drawbridge/db.py`). WAL lets readers proceed
  without blocking on the one in-progress writer — the default rollback
  journal mode blocks readers too, which would stall `/api/devices` GETs
  behind a slow write from another worker.
- `PRAGMA busy_timeout=<SQLITE_BUSY_TIMEOUT_MS>` is set on every connection.
  Instead of raising `database is locked` immediately when another worker
  holds the write lock, SQLite retries internally up to the timeout. Default
  is `1000`ms — deliberately well under `LEASE_EVENT_TIMEOUT`'s 2 s, leaving
  headroom for the Kea Control Agent round trip rather than spending the
  whole park budget on lock contention.
- Application code still wraps write paths (`/api/lease-event` approval,
  `/api/devices` POST/DELETE, provisioning-event inserts) with a small
  bounded retry on `sqlite3.OperationalError: database is locked` — WAL and
  `busy_timeout` make lock waits the common case, not eliminate the
  possibility of exhausting the timeout under heavy contention.
- The SQLAlchemy `Engine` is created inside `create_app()`, i.e. after
  Gunicorn forks each worker — not at module import time. A `sqlite3`
  connection shared across a `fork()` corrupts the database; each of the 4
  worker processes must get its own `Engine`/connection pool. `connect_args`
  includes `check_same_thread=False` since gevent can hand a checked-out
  connection between greenlets within one process.
- WAL mode requires the database file on a local filesystem — true here
  (bind-mounted host directory on the same Ubuntu host), not network
  storage. WAL also produces `drawbridge.db-wal` and `drawbridge.db-shm`
  alongside the main file; any backup tooling must capture all three, not
  just `drawbridge.db`.
- Keep request-scoped transactions short (already required above) — the
  longer a writer holds the lock, the longer the other 3 workers sit inside
  their `busy_timeout`.

See [decisions.md](decisions.md) for why WAL + busy_timeout was chosen over
moving to a client/server database.

## Log Retention & Data Minimisation

Drawbridge is not an inventory system — `devices` rows (serial, MAC) are
deleted as soon as `/api/provision-complete` fires (see
[architecture.md](architecture.md), DHCP Flow step 9). What persists is
`ProvisioningLog`: when a device was provisioned and what image/config file
it received, for audit and troubleshooting, not asset tracking.

- Retention is controlled by the `Setting` row keyed `log_retention_days` —
  an **admin-configurable, DB-backed setting** via `GET`/`PUT
  /api/settings/log-retention`, not a fixed env var, so it can change
  without a container restart.
- Default is `30` days. `LOG_RETENTION_DAYS` (env var) seeds this row on
  first `init_db()` run only — after that, the DB value is authoritative.
- An admin can set the value to the literal string `indefinite`, which
  disables purging entirely. This is an explicit, visible override of the
  "don't keep this stuff" default, not a loophole — the schema and the UI
  should make clear that's what's happening.
- Purging is lazy, not a separate scheduled job: before inserting a new
  `ProvisioningLog` row, delete existing rows older than the current
  retention setting (skipped entirely when retention is `indefinite`). This
  needs no extra process or systemd timer, consistent with the project's
  preference for minimal moving parts — the tradeoff is that on a
  long-idle deployment, expired rows linger until the next provisioning
  event, which is acceptable for a log, not a security control.
- Only `provision_complete` and `provision_failed` events land in
  `ProvisioningLog` — lease decisions are not logged. The retention rule
  covers all device-identifying archival data.
