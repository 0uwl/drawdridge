"""Thin client for Kea's Control Agent REST API (the `host_cmds` hook's
reservation-add/reservation-del commands) — see docs/kea.md.

Callers (the API blueprints) decide what HTTP response to send their own
caller on failure, so nothing here swallows an error: every failure mode
raises KeaError rather than returning a falsy value, per the fail-closed
posture in docs/decisions.md.
"""
import requests


class KeaError(Exception):
    """Kea Control Agent was unreachable, errored, or returned a
    non-success result for a command."""


def reservation_add(ctrl_url: str, subnet_id: str, mac: str, ip: str, timeout: float = 2.0) -> dict:
    """Reserve `ip` for `mac` in `subnet_id`. Reservations are keyed on
    hw-address (not serial) because Kea's host-reservation/classification
    system is natively MAC-keyed; `mac` is present on every
    /api/lease-event payload."""
    return _post_command(ctrl_url, 'reservation-add', {
        'reservation': {
            'subnet-id': int(subnet_id),
            'hw-address': mac,
            'ip-address': ip,
        },
    }, timeout)


def reservation_del(ctrl_url: str, subnet_id: str, mac: str, timeout: float = 2.0) -> dict:
    """Remove the reservation keyed on `mac` in `subnet_id`."""
    return _post_command(ctrl_url, 'reservation-del', {
        'subnet-id': int(subnet_id),
        'identifier-type': 'hw-address',
        'identifier': mac,
    }, timeout)


def _post_command(ctrl_url: str, command: str, arguments: dict, timeout: float) -> dict:
    body = {'command': command, 'service': ['dhcp4'], 'arguments': arguments}

    try:
        response = requests.post(ctrl_url, json=body, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise KeaError(f'Kea Control Agent unreachable: {exc}') from exc

    try:
        results = response.json()
    except ValueError as exc:
        raise KeaError('Kea Control Agent returned a non-JSON response') from exc

    # The Control Agent wraps each targeted service's reply in a list;
    # dhcp4 is the only service ever targeted here, so always read index 0.
    result = results[0] if isinstance(results, list) else results

    if result.get('result') != 0:
        raise KeaError(f"Kea command '{command}' failed: {result.get('text')}")

    return result.get('arguments', {})
