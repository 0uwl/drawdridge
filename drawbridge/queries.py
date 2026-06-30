"""Query helpers for the models in drawbridge/models.py, called from the API
blueprints.

These functions only stage changes (add/delete) on the Session passed in —
they don't commit. Committing is the caller's responsibility, so a route
that needs several of these in one transaction (e.g. /api/lease-event
checking a device then writing a ProvisioningLog row) can do so atomically.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from drawbridge.models import Device, ProvisioningLog, Setting, User, utcnow_iso

# Device queries

def get_device(session: Session, serial: str) -> Device | None:
    return session.get(Device, serial)


def list_devices(session: Session) -> list[Device]:
    return list(session.scalars(select(Device).order_by(Device.added_at)).all())


def add_device(
    session: Session,
    *,
    serial: str,
    mac: str | None = None,
    description: str | None = None,
    added_by: str | None = None,
) -> Device:
    """Idempotent on serial: re-registering an existing serial updates its
    mutable fields instead of raising on the primary-key collision."""
    device = session.get(Device, serial)
    if device is not None:
        device.mac = mac
        device.description = description
        device.added_by = added_by
        return device

    device = Device(serial=serial, mac=mac, description=description, added_by=added_by)
    session.add(device)
    return device


def delete_device(session: Session, serial: str) -> bool:
    device = session.get(Device, serial)
    if device is None:
        return False
    session.delete(device)
    return True


# User queries

def get_user_by_username(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def get_user_by_id(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def list_users(session: Session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.username)).all())


# Setting queries

def get_setting(session: Session, key: str) -> Setting | None:
    return session.get(Setting, key)


def set_setting(session: Session, key: str, value: str, updated_by: str | None = None) -> Setting:
    setting = session.get(Setting, key)
    if setting is None:
        setting = Setting(key=key, value=value, updated_by=updated_by)
        session.add(setting)
    else:
        setting.value = value
        setting.updated_by = updated_by
        setting.updated_at = utcnow_iso()
    return setting


# ProvisioningLog queries

def add_log_entry(
    session: Session,
    *,
    serial: str,
    event: str,
    ip: str | None = None,
    image: str | None = None,
    config_file: str | None = None,
    detail: str | None = None,
) -> ProvisioningLog:
    """Writes one ProvisioningLog row, purging expired rows first per the
    lazy-retention policy in docs/database.md."""
    retention = get_setting(session, 'log_retention_days')
    if retention is not None:
        purge_expired_logs(session, retention.value)

    entry = ProvisioningLog(
        serial=serial,
        event=event,
        ip=ip,
        image=image,
        config_file=config_file,
        detail=detail,
    )
    session.add(entry)
    return entry


def purge_expired_logs(session: Session, retention_days: str) -> None:
    """Deletes ProvisioningLog rows older than retention_days. A no-op when
    retention is the literal string 'indefinite' (see docs/database.md,
    "Log Retention & Data Minimisation")."""
    if retention_days == 'indefinite':
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(days=int(retention_days))).isoformat(timespec='microseconds')
    session.execute(delete(ProvisioningLog).where(ProvisioningLog.ts < cutoff))
