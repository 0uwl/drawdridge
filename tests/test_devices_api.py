import pytest

from drawbridge.db import get_session
from drawbridge.models import UnprovisionedDevice

BASE = '/api/v1'


@pytest.fixture()
def device(app):
    with app.app_context():
        session = get_session()
        d = UnprovisionedDevice(
            serial='FJC2517X0AB',
            mac='aa:bb:cc:dd:ee:ff',
            description='Test device',
            added_by='operator',
        )
        session.add(d)
        session.commit()
    return d


# GET /api/v1/devices

def test_list_devices_returns_401_when_not_logged_in(client):
    response = client.get(f'{BASE}/devices/')
    assert response.status_code == 401


def test_list_devices_returns_empty_list_when_no_devices(logged_in_client):
    response = logged_in_client.get(f'{BASE}/devices/')
    assert response.status_code == 200
    assert response.get_json()['payload'] == []


def test_list_devices_returns_registered_devices(logged_in_client, device):
    response = logged_in_client.get(f'{BASE}/devices/')
    assert response.status_code == 200
    payload = response.get_json()['payload']
    assert len(payload) == 1
    assert payload[0]['serial'] == device.serial


# POST /api/v1/devices

def test_add_device_returns_401_when_not_logged_in(client):
    response = client.post(f'{BASE}/devices/', json={'serial': 'FJC2517X0AB'})
    assert response.status_code == 401


def test_add_device_returns_422_when_serial_missing(logged_in_client):
    response = logged_in_client.post(f'{BASE}/devices/', json={'mac': 'aa:bb:cc:dd:ee:ff'})
    assert response.status_code == 422


def test_add_device_returns_422_on_empty_body(logged_in_client):
    response = logged_in_client.post(f'{BASE}/devices/', json={})
    assert response.status_code == 422


def test_add_device_returns_200_with_serial_only(logged_in_client):
    response = logged_in_client.post(f'{BASE}/devices/', json={'serial': 'FJC2517X0AB'})
    assert response.status_code == 200


def test_add_device_persists_to_db(app, logged_in_client):
    logged_in_client.post(f'{BASE}/devices/', json={
        'serial': 'FJC2517X0AB',
        'mac': 'aa:bb:cc:dd:ee:ff',
        'description': 'Edge router',
    })
    with app.app_context():
        d = get_session().get(UnprovisionedDevice, 'FJC2517X0AB')
        assert d is not None
        assert d.mac == 'aa:bb:cc:dd:ee:ff'
        assert d.description == 'Edge router'


def test_add_device_sets_added_by_to_current_user(app, logged_in_client, user):
    logged_in_client.post(f'{BASE}/devices/', json={'serial': 'FJC2517X0AB'})
    with app.app_context():
        d = get_session().get(UnprovisionedDevice, 'FJC2517X0AB')
        assert d.added_by == user.username


def test_add_device_is_idempotent_on_serial(app, logged_in_client, device):
    logged_in_client.post(f'{BASE}/devices/', json={
        'serial': device.serial,
        'mac': '11:22:33:44:55:66',
        'description': 'Updated description',
    })
    with app.app_context():
        d = get_session().get(UnprovisionedDevice, device.serial)
        assert d.mac == '11:22:33:44:55:66'
        assert d.description == 'Updated description'
    response = logged_in_client.get(f'{BASE}/devices/')
    assert len(response.get_json()['payload']) == 1


# GET /api/v1/devices/<serial>

def test_get_device_returns_401_when_not_logged_in(client, device):
    response = client.get(f'{BASE}/devices/{device.serial}')
    assert response.status_code == 401


def test_get_device_returns_404_when_not_found(logged_in_client):
    response = logged_in_client.get(f'{BASE}/devices/NOSUCHSERIAL')
    assert response.status_code == 404
    assert response.get_json()['error'] == 'device_not_found'


def test_get_device_returns_device_payload(logged_in_client, device):
    response = logged_in_client.get(f'{BASE}/devices/{device.serial}')
    assert response.status_code == 200
    payload = response.get_json()['payload']
    assert payload['serial'] == device.serial
    assert payload['mac'] == device.mac


# DELETE /api/v1/devices/<serial>

def test_delete_device_returns_401_when_not_logged_in(client, device):
    response = client.delete(f'{BASE}/devices/{device.serial}')
    assert response.status_code == 401


def test_delete_device_returns_404_when_not_found(logged_in_client):
    response = logged_in_client.delete(f'{BASE}/devices/NOSUCHSERIAL')
    assert response.status_code == 404
    assert response.get_json()['error'] == 'device_not_found'


def test_delete_device_returns_200_on_success(logged_in_client, device):
    response = logged_in_client.delete(f'{BASE}/devices/{device.serial}')
    assert response.status_code == 200
    assert response.get_json()['success'] is True


def test_delete_device_removes_from_db(app, logged_in_client, device):
    logged_in_client.delete(f'{BASE}/devices/{device.serial}')
    with app.app_context():
        assert get_session().get(UnprovisionedDevice, device.serial) is None
