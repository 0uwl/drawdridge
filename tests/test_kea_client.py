from unittest.mock import patch

import pytest
import requests

from drawbridge.kea import KeaError, reservation_add, reservation_del

CTRL_URL = 'http://keahost:8081'
SUBNET_ID = '1'
MAC = 'aa:bb:cc:dd:ee:ff'
IP = '192.168.100.15'


def _mock_response(json_body, status=200):
    response = requests.Response()
    response.status_code = status
    response.json = lambda: json_body
    return response


def test_reservation_add_sends_expected_command_envelope():
    with patch('drawbridge.kea.requests.post', return_value=_mock_response([{'result': 0, 'text': 'ok'}])) as post:
        reservation_add(CTRL_URL, SUBNET_ID, MAC, IP)

    args, kwargs = post.call_args
    assert args[0] == CTRL_URL
    assert kwargs['json'] == {
        'command': 'reservation-add',
        'service': ['dhcp4'],
        'arguments': {
            'reservation': {'subnet-id': 1, 'hw-address': MAC, 'ip-address': IP},
        },
    }


def test_reservation_del_sends_expected_command_envelope():
    with patch('drawbridge.kea.requests.post', return_value=_mock_response([{'result': 0, 'text': 'ok'}])) as post:
        reservation_del(CTRL_URL, SUBNET_ID, MAC)

    args, kwargs = post.call_args
    assert args[0] == CTRL_URL
    assert kwargs['json'] == {
        'command': 'reservation-del',
        'service': ['dhcp4'],
        'arguments': {'subnet-id': 1, 'identifier-type': 'hw-address', 'identifier': MAC},
    }


def test_reservation_add_returns_command_arguments_on_success():
    payload = [{'result': 0, 'text': 'ok', 'arguments': {'reservation': {'ip-address': IP}}}]
    with patch('drawbridge.kea.requests.post', return_value=_mock_response(payload)):
        result = reservation_add(CTRL_URL, SUBNET_ID, MAC, IP)

    assert result == {'reservation': {'ip-address': IP}}


def test_raises_keaerror_on_connection_failure():
    with patch('drawbridge.kea.requests.post', side_effect=requests.ConnectionError('refused')):
        with pytest.raises(KeaError):
            reservation_add(CTRL_URL, SUBNET_ID, MAC, IP)


def test_raises_keaerror_on_timeout():
    with patch('drawbridge.kea.requests.post', side_effect=requests.Timeout('timed out')):
        with pytest.raises(KeaError):
            reservation_del(CTRL_URL, SUBNET_ID, MAC)


def test_raises_keaerror_on_non_2xx_http_status():
    response = _mock_response({}, status=500)
    with patch('drawbridge.kea.requests.post', return_value=response):
        with pytest.raises(KeaError):
            reservation_add(CTRL_URL, SUBNET_ID, MAC, IP)


def test_raises_keaerror_on_non_json_body():
    response = _mock_response({})
    response.json = lambda: (_ for _ in ()).throw(ValueError('not json'))
    with patch('drawbridge.kea.requests.post', return_value=response):
        with pytest.raises(KeaError):
            reservation_add(CTRL_URL, SUBNET_ID, MAC, IP)


def test_raises_keaerror_on_kea_command_failure_result():
    payload = [{'result': 1, 'text': 'Reservation already exists'}]
    with patch('drawbridge.kea.requests.post', return_value=_mock_response(payload)):
        with pytest.raises(KeaError, match='Reservation already exists'):
            reservation_add(CTRL_URL, SUBNET_ID, MAC, IP)
