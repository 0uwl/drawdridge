# Web API

**Entry point:** `drawbridge/main.py` — creates the Flask app via factory function
`create_app()`. Gunicorn is used as the WSGI server inside the container (see
[deployment.md](deployment.md)).

**Key endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/lease-event` | Called by Kea hook; approves or denies lease |
| GET | `/api/devices` | List devices currently pending provisioning |
| POST | `/api/devices` | Register a new device (serial + optional metadata) |
| DELETE | `/api/devices/<serial>` | Remove a device from the allowlist |
| GET | `/api/devices/<serial>` | Get a pending device's status (not history — see `/api/log`) |
| GET | `/scripts/<filename>` | Serve ZTP scripts to devices (HTTPS) |
| POST | `/api/provision-complete` | Device reports provisioning outcome; deletes the `devices` row, writes a `ProvisioningLog` row |
| GET | `/api/log` | List provisioning log entries (time, image, config file, outcome) within the retention window |
| POST | `/api/auth/login` | Local username/password login, starts session |
| POST | `/api/auth/logout` | Ends the current session |
| GET | `/api/auth/me` | Current authenticated operator (id, username, role, auth_source) |
| GET | `/api/users` | List operator accounts (admin only) |
| POST | `/api/users` | Create an operator account (admin only) |
| DELETE | `/api/users/<id>` | Remove an operator account (admin only) |
| GET | `/api/settings/log-retention` | Current log retention setting (days, or indefinite) |
| PUT | `/api/settings/log-retention` | Update log retention setting (admin only) |

Every `/api/devices`, `/api/log`, `/api/users`, `/api/settings/*`, and
`/scripts/<filename>` (management, not the device's own fetch) route
requires an authenticated session via `@login_required` — see
[authentication.md](authentication.md). `/api/lease-event` and
`/api/provision-complete` are called by Kea/devices, not operators. The
primary security boundary is network isolation (provisioning VLAN/loopback —
see [architecture.md](architecture.md)). `/api/lease-event` additionally
enforces origin-based access control via the `kea_endpoint` decorator:
loopback callers are always allowed; non-loopback callers require a Bearer
token matching `KEA_HOOK_API_KEY` unless `KEA_SKIP_AUTH` is set. See
[deployment.md](deployment.md) for configuration.

## `/api/lease-event` contract

Kea's hook POSTs JSON:
```json
{
  "serial": "FJC2517X0AB",
  "mac": "aa:bb:cc:dd:ee:ff",
  "ip": "192.168.100.15"
}
```

Response must be fast (< 2 s — Kea's park timeout). Return:
- `200 OK` → Kea sends DHCPACK
- Any non-200 → Kea drops the packet (fail closed)

On approval, this endpoint also calls Kea's Control Agent to confirm the
reservation exists. On error reaching Kea Control Agent, fail closed (return
non-200) rather than partially approving.
