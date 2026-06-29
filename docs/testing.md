# Testing Approach

Tests live in `tests/` and use pytest. The Flask app must be testable without
a running Kea instance — use `unittest.mock.patch` to mock `drawbridge/kea.py`
calls.

The SQLite database for tests uses a temporary file via a `tmp_path` fixture,
never the production `/srv/drawbridge/data/drawbridge.db`.

Key test cases to cover:
- `POST /api/lease-event` with known serial → 200
- `POST /api/lease-event` with unknown serial → 403
- `POST /api/lease-event` when Kea Control Agent unreachable → 500 (fail closed)
- `POST /api/devices` idempotency (re-registering same serial)
- `DELETE /api/devices/<serial>` calls `reservation-del` on Kea
- `ProvisioningLog` row written correctly on each lease decision
- `POST /api/provision-complete` deletes the `devices` row and writes a `ProvisioningLog` row with image/config_file set
- `ProvisioningLog` rows older than the retention setting are purged on next insert; rows are kept when retention is `indefinite`
- `PUT /api/settings/log-retention` as admin updates the setting; as non-admin → 403
- `POST /api/auth/login` with correct/incorrect credentials → 200 / 401
- Accessing `/api/devices`, `/api/log`, or `/api/users` without a session → 401
- `POST /api/users` as a non-admin operator → 403
- Concurrent writes from multiple sessions (simulating multiple workers) don't raise unhandled `database is locked` errors

Run with:
```bash
pytest -v
pytest tests/test_lease_api.py   # single file
pytest --tb=short                # brief tracebacks
```
