from datetime import datetime, timedelta, timezone

from drawbridge import queries
from drawbridge.models import ProvisioningLog


def test_add_device_creates_a_new_device(session):
    queries.add_device(session, serial='SN1', mac='aa:bb', description='switch', added_by='admin')
    session.commit()

    device = queries.get_device(session, 'SN1')
    assert device is not None
    assert device.mac == 'aa:bb'
    assert [d.serial for d in queries.list_devices(session)] == ['SN1']


def test_add_device_is_idempotent_on_serial(session):
    queries.add_device(session, serial='SN1', mac='aa:bb', description='first')
    session.commit()

    queries.add_device(session, serial='SN1', mac='cc:dd', description='second')
    session.commit()

    devices = queries.list_devices(session)
    assert len(devices) == 1
    assert devices[0].mac == 'cc:dd'
    assert devices[0].description == 'second'


def test_delete_device(session):
    queries.add_device(session, serial='SN1')
    session.commit()

    assert queries.delete_device(session, 'SN1') is True
    session.commit()
    assert queries.get_device(session, 'SN1') is None
    assert queries.delete_device(session, 'SN1') is False


def test_get_user_by_username_and_id(session):
    # the bootstrapped admin user already exists from init_db()
    admin = queries.get_user_by_username(session, 'admin')

    assert admin is not None
    assert queries.get_user_by_id(session, admin.id) is admin
    assert queries.get_user_by_username(session, 'nobody') is None


def test_set_setting_creates_then_updates(session):
    created = queries.set_setting(session, 'log_retention_days', '45', updated_by='admin')
    session.commit()
    assert created.value == '45'
    first_updated_at = created.updated_at

    updated = queries.set_setting(session, 'log_retention_days', '60', updated_by='admin')
    session.commit()
    assert updated.value == '60'
    assert updated.updated_at >= first_updated_at


def test_add_log_entry_writes_a_row(session):
    entry = queries.add_log_entry(session, serial='SN1', event='lease_approved', ip='10.0.0.5')
    session.commit()

    assert entry.id is not None
    rows = session.query(ProvisioningLog).all()
    assert len(rows) == 1
    assert rows[0].event == 'lease_approved'
    assert rows[0].ip == '10.0.0.5'


def test_purge_expired_logs_removes_rows_older_than_retention(session):
    old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec='microseconds')
    session.add(ProvisioningLog(serial='SN1', event='lease_approved', ts=old_ts))
    session.commit()

    queries.purge_expired_logs(session, '5')
    session.commit()

    assert session.query(ProvisioningLog).count() == 0


def test_purge_expired_logs_is_a_noop_when_retention_is_indefinite(session):
    old_ts = (datetime.now(timezone.utc) - timedelta(days=9999)).isoformat(timespec='microseconds')
    session.add(ProvisioningLog(serial='SN1', event='lease_approved', ts=old_ts))
    session.commit()

    queries.purge_expired_logs(session, 'indefinite')
    session.commit()

    assert session.query(ProvisioningLog).count() == 1


def test_add_log_entry_purges_expired_rows_before_inserting(session):
    old_ts = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(timespec='microseconds')
    session.add(ProvisioningLog(serial='SN1', event='lease_approved', ts=old_ts))
    session.commit()
    # default retention seeded from LOG_RETENTION_DAYS config ('30')

    queries.add_log_entry(session, serial='SN1', event='provision_complete')
    session.commit()

    rows = session.query(ProvisioningLog).all()
    assert len(rows) == 1
    assert rows[0].event == 'provision_complete'
