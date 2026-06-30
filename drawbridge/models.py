from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow_iso() -> str:
    """Fixed-width (timespec='microseconds') so timestamp columns remain
    lexicographically sortable — relied on by the log-retention purge query
    in queries.py, which compares ts strings directly rather than parsing
    them."""
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


class Device(Base):
    """Pre-provisioning allowlist only. A row exists from registration until
    /api/provision-complete fires, at which point it is deleted"""
    __tablename__ = 'devices'

    serial: Mapped[str] = mapped_column(primary_key=True)
    mac: Mapped[str | None]
    description: Mapped[str | None]
    added_at: Mapped[str] = mapped_column(default=utcnow_iso)
    added_by: Mapped[str | None]


class ProvisioningLog(Base):
    """The durable record once a device leaves the `devices` table — covers
    lease decisions and the eventual provisioning outcome. Subject to the
    retention policy in Setting; purged once a row outlives it."""
    __tablename__ = 'provisioning_log'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    serial: Mapped[str]
    event: Mapped[str]   # 'lease_approved', 'lease_denied',
                          # 'provision_complete', 'provision_failed'
    image: Mapped[str | None]         # image filename/version given (provision_complete only)
    config_file: Mapped[str | None]   # config filename given (provision_complete only)
    ip: Mapped[str | None]
    ts: Mapped[str] = mapped_column(default=utcnow_iso)
    detail: Mapped[str | None]   # JSON blob for extra context


class Setting(Base):
    """Small admin-configurable key/value store. First row of interest:
    key='log_retention_days', value='30' (or 'indefinite')."""
    __tablename__ = 'settings'

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]
    updated_at: Mapped[str] = mapped_column(default=utcnow_iso)
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
    created_at: Mapped[str] = mapped_column(default=utcnow_iso)
    last_login_at: Mapped[str | None]
