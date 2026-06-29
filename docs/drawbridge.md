# Drawbridge — Project Context for Claude

## What This Project Is

A Zero Touch Provisioning (ZTP) system for Cisco IOS XE devices on an isolated
provisioning VLAN. It replaces manual Day 0 configuration by automatically
serving a Python provisioning script to devices when they first boot with no
startup config.

This is a hardened classic ZTP implementation, not Cisco's sZTP (RFC 8572).
The decision to avoid sZTP was deliberate — sZTP requires per-device Ownership
Vouchers from Cisco's MASA server, a Pinned Domain Certificate, and significant
PKI infrastructure. The security model here achieves comparable protection for
an internal, physically isolated provisioning VLAN through:

- Kea DHCP pre-authorisation gate (lease withheld until Drawbridge approves)
- Serial number / client-id allowlisting
- HTTPS script delivery with server certificate validation inside the script
- SHA-256 hash verification of images and config payloads
- Provisioning VLAN isolation — devices can only reach the Drawbridge server

## System Architecture

```
Provisioning VLAN
       │
       ▼
┌─────────────────────────────────────────────────────┐
│  Ubuntu host (dedicated provisioning machine)       │
│                                                     │
│  ┌─────────────────────┐                            │
│  │  Kea DHCPv4         │  native systemd service    │
│  │  port 67 (UDP)      │  runs as _kea user         │
│  │                     │                            │
│  │  leases4_committed  │──── PARK ──────────────┐  │
│  │  hook (host_cmds +  │                        │  │
│  │  custom callout)    │◄─── approve/deny ──────┘  │
│  └─────────────────────┘         │                  │
│  │  Kea Control Agent  │         │                  │
│  │  127.0.0.1:8081     │◄── reservation-add/del ─┐ │
│  └─────────────────────┘                          │ │
│                                                   │ │
│  ┌─────────────────────────────────────────────┐  │ │
│  │  Drawbridge container (rootless Podman)    │  │ │
│  │  user: drawbridge                           │  │ │
│  │  image: localhost/drawbridge:latest         │  │ │
│  │                                             │  │ │
│  │  Flask app, port 8080                       │──┘ │
│  │  published to 127.0.0.1:8080               │    │
│  │                                             │    │
│  │  /app/data/drawbridge.db   (SQLite)         │    │
│  │  /app/scripts/      (ZTP Python scripts)    │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  Host bind mounts:                                  │
│    /srv/drawbridge/data/    → /app/data/             │
│    /srv/drawbridge/scripts/ → /app/scripts/ (read-only)│
└─────────────────────────────────────────────────────┘
```

## DHCP Flow

1. IOS XE device boots with no startup config, sends DHCPDISCOVER
2. Kea receives it and fires `leases4_committed` callout, **parking** the packet
3. Callout POSTs to `http://127.0.0.1:8080/api/lease-event` with serial + MAC
4. Drawbridge checks SQLite allowlist — if known, returns 200; if unknown, 403
5. On 200: Kea unparks, sends DHCPACK with Option 67 URL pointing at Drawbridge
6. On 403 or timeout: Kea drops the packet (fail closed)
7. Device fetches the ZTP script over HTTPS, verifies server cert and payload hash
8. Script provisions the device, POSTs completion status back to Drawbridge
9. Drawbridge calls Kea Control Agent `reservation-del` to remove the device
   from the allowlist, preventing accidental re-provisioning

Note: IOS XE alternates DHCP Client Identifier (Option 61) between the device
serial number and the management port MAC address across retries. The allowlist
should support matching on either. Serial numbers are preferred as they are
meaningful to inventory systems.

## Repository Layout

```
drawbridge/
├── CLAUDE.md                  ← this file
├── README.md
├── Containerfile              ← builds localhost/drawbridge:latest
├── quadlet/
│   └── drawbridge.container   ← Podman Quadlet for the drawbridge user
├── kea/
│   ├── kea-dhcp4.conf         ← Kea DHCPv4 configuration
│   ├── kea-ctrl-agent.conf    ← Kea Control Agent (REST API, 127.0.0.1:8081)
│   └── hook/                  ← C++ or Python leases4_committed callout
│       └── ...
├── drawbridge/
│   ├── __init__.py
│   ├── main.py                ← Flask app factory and entry point
│   ├── api/
│   │   ├── lease.py           ← POST /api/lease-event (called by Kea hook)
│   │   ├── devices.py         ← CRUD for device allowlist
│   │   └── scripts.py         ← ZTP script management endpoints
│   ├── db.py                  ← SQLite connection and schema init
│   ├── models.py              ← Device, ProvisioningEvent data classes
│   └── kea.py                 ← Kea Control Agent client (reservation-add/del)
├── scripts/
│   └── ztp-base.py            ← Base ZTP script served to IOS XE devices
├── tests/
│   ├── conftest.py
│   ├── test_lease_api.py
│   ├── test_devices_api.py
│   └── test_kea_client.py
└── requirements.txt
```

## Flask Application

**Entry point:** `drawbridge/main.py` — creates the Flask app via factory function
`create_app()`. Gunicorn is used as the WSGI server inside the container.

**Key endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/lease-event` | Called by Kea hook; approves or denies lease |
| GET | `/api/devices` | List all devices in the allowlist |
| POST | `/api/devices` | Register a new device (serial + optional metadata) |
| DELETE | `/api/devices/<serial>` | Remove a device from the allowlist |
| GET | `/api/devices/<serial>` | Get device status and provisioning history |
| GET | `/scripts/<filename>` | Serve ZTP scripts to devices (HTTPS) |
| POST | `/api/provision-complete` | Device reports successful provisioning |

**`/api/lease-event` contract:**

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

## SQLite Schema

Managed via plain SQL in `drawbridge/db.py`, initialised on first run. No ORM —
keep it simple.

```sql
CREATE TABLE IF NOT EXISTS devices (
    serial      TEXT PRIMARY KEY,
    mac         TEXT,
    description TEXT,
    added_at    TEXT NOT NULL,
    added_by    TEXT
);

CREATE TABLE IF NOT EXISTS provisioning_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    serial      TEXT NOT NULL,
    event       TEXT NOT NULL,   -- 'lease_approved', 'lease_denied',
                                 -- 'provision_complete', 'provision_failed'
    ip          TEXT,
    ts          TEXT NOT NULL,
    detail      TEXT             -- JSON blob for extra context
);
```

## Kea Configuration Notes

**Control Agent** (`kea/kea-ctrl-agent.conf`):
- Listens on `127.0.0.1:8081` — loopback only, not exposed externally
- The Drawbridge container reaches it via `http://keahost:8081` where `keahost`
  resolves to `host-gateway` via the Quadlet's `AddHost` directive

**DHCPv4** (`kea/kea-dhcp4.conf`):
- Provisioning subnet: `192.168.100.0/24`, pool `192.168.100.10–200`
- `deny-unknown-clients` equivalent via client class — unknown devices get
  no offer at all, not even a NAK
- Option 67 (`boot-file-name`) set to `https://<host-ip>:8080/scripts/ztp-base.py`
  only for devices in the `known` client class
- `leases4_committed` hook configured with the custom callout library
- `host_cmds` hook loaded to enable `reservation-add`/`reservation-del` via API

**`leases4_committed` hook behaviour:**
- POSTs to `http://127.0.0.1:8080/api/lease-event` synchronously
- On HTTP 200: sets next step to CONTINUE (unpark, send DHCPACK)
- On any other response or connection error: sets next step to DROP
- Timeout: 2 seconds — fail closed on timeout

## Container

**Containerfile** builds `localhost/drawbridge:latest`:
- Base image: `python:3.12-slim`
- Non-root user `appuser` (UID 1000) created in image
- Gunicorn as WSGI server, binding `0.0.0.0:8080`
- `/app/data` and `/app/scripts` are mount points — do not COPY content there
- Root filesystem is read-only at runtime; `/tmp` and `/run` are tmpfs

**Quadlet** at `~/.config/containers/systemd/drawbridge.container` (as
`drawbridge` user). See `quadlet/drawbridge.container` in this repo.

Host directories must exist before starting:
```bash
sudo mkdir -p /srv/drawbridge/{data,scripts}
sudo chown -R drawbridge:drawbridge /srv/drawbridge
```

## Development Setup

```bash
# Clone and set up a virtualenv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run Flask in dev mode (no container needed)
export FLASK_APP=drawbridge/main.py
export FLASK_DEBUG=1
export DATABASE_PATH=./dev-data/drawbridge.db
export SCRIPTS_PATH=./scripts
export KEA_CTRL_URL=http://localhost:8081   # or mock it
mkdir -p dev-data
flask run --port 8080

# Run tests
pytest

# Build the container image
podman build -t localhost/drawbridge:latest .
```

## Testing Approach

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
- Provisioning event log written correctly on each lease decision

Run with:
```bash
pytest -v
pytest tests/test_lease_api.py   # single file
pytest --tb=short                # brief tracebacks
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `/app/data/ztp.db` | SQLite database file path |
| `SCRIPTS_PATH` | `/app/scripts` | Directory containing ZTP scripts to serve |
| `KEA_CTRL_URL` | `http://keahost:8081` | Kea Control Agent base URL |
| `KEA_SUBNET_ID` | `1` | Kea subnet ID for reservation commands |
| `LEASE_EVENT_TIMEOUT` | `2` | Seconds before Kea hook times out (fail closed) |
| `FLASK_DEBUG` | `0` | Set to `1` in local dev only, never in container |

## Decisions and Constraints

- **No sZTP.** Cisco's RFC 8572 implementation requires MASA-issued Ownership
  Vouchers per device — too operationally complex for an internal provisioning
  VLAN. The threat model here (physically isolated VLAN, internal deployment)
  does not justify it.

- **Fail closed everywhere.** If Drawbridge is unreachable, Kea drops the
  lease. If Kea's Control Agent is unreachable when Drawbridge tries to
  add a reservation, the endpoint returns an error. Devices wait and retry —
  they are not provisioned with unvalidated config.

- **Serial number over MAC.** IOS XE alternates Option 61 between serial and
  MAC across DHCPDISCOVER retries. Serials are the canonical identifier.
  MACs are logged but not used as the primary allowlist key.

- **No ORM.** The schema is trivial and stable. Plain SQL keeps the dependency
  footprint small and the queries readable.

- **No external message queue.** The Kea hook calls the ZTP server directly
  over HTTP. The PARK mechanism handles the synchronisation. A message queue
  would add complexity with no benefit at this scale.

- **Rootless Podman for the Drawbridge container.** Kea cannot run rootless
  (requires raw socket for DHCP broadcast) so it runs as a native systemd
  service. The Drawbridge container has no such constraint and runs rootless
  under the `drawbridge` user with lingering enabled.

- **Kea Control Agent on 127.0.0.1:8081.** Default Kea port is 8080, which
  conflicts with Drawbridge. Control Agent is bound to loopback only.