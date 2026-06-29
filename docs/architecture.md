# Architecture

## What This Project Is

A Zero Touch Provisioning (ZTP) system for Cisco IOS XE devices. It replaces manual Day 0 configuration by automatically
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

Drawbridge is **not** an inventory management system. It is not the source
of truth for "what devices does this org own" — it only needs to know about
a device for the brief window between registration and provisioning. Serial
numbers and MAC addresses are deliberately not retained long-term; see
[database.md](database.md) ("Log Retention & Data Minimisation").

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
│  │  leases4_committed  │────  PARK ──────────────┐  │
│  │  hook (host_cmds +  │                         │  │
│  │  custom callout)    │◄───  approve/deny ──────┘  │
│  └─────────────────────┘         │                  │
│  │  Kea Control Agent  │         │                  │
│  │  127.0.0.1:8081     │◄──  reservation-add/del ─┐ │
│  └─────────────────────┘                          │ │
│                                                   │ │
│  ┌─────────────────────────────────────────────┐  │ │
│  │  Drawbridge container (rootless Podman)     │  │ │
│  │  user: drawbridge                           │  │ │
│  │  image: localhost/drawbridge:latest         │  │ │
│  │                                             │  │ │
│  │  Flask app, port 8080                       │──┘ │
│  │  published to 127.0.0.1:8080                │    │
│  │                                             │    │
│  │  /app/drawbridge.db   (SQLite)         │    │
│  │  /app/scripts/      (ZTP Python scripts)    │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  Host bind mounts:                                  │
│    /srv/drawbridge/data/    → /app/data/            │
│    /srv/drawbridge/scripts/ → /app/scripts/ (ro)    │
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
   from the allowlist, preventing accidental re-provisioning, and deletes
   the device's row from the SQLite `devices` table in the same request —
   the serial/MAC don't persist past this point; a `ProvisioningLog` row
   (time, image, config file) is written in its place

Note: IOS XE alternates DHCP Client Identifier (Option 61) between the device
serial number and the management port MAC address across retries. The allowlist
should support matching on either. Serial numbers are preferred as they are
meaningful to inventory systems.

## Repository Layout

```
drawbridge/
├── CLAUDE.md                  ← project index, links into docs/
├── README.md
├── docs/                      ← detailed design docs (this file and siblings)
├── Containerfile              ← builds localhost/drawbridge:latest
├── quadlet/
│   └── drawbridge.container   ← Podman Quadlet for the drawbridge user
├── kea/
│   ├── kea-dhcp4.conf         ← Kea DHCPv4 configuration
│   ├── kea-ctrl-agent.conf    ← Kea Control Agent (REST API, 127.0.0.1:8081)
│   └── hook/                  ← Python leases4_committed callout
│       └── ...
├── drawbridge/
│   ├── __init__.py
│   ├── main.py                ← Flask app factory and entry point
│   ├── api/
│   │   ├── lease.py           ← POST /api/lease-event (called by Kea hook)
│   │   ├── devices.py         ← CRUD for device allowlist
│   │   ├── scripts.py         ← ZTP script management endpoints
│   │   ├── auth.py            ← login/logout, current-user endpoints
│   │   ├── users.py           ← admin CRUD for operator accounts
│   │   └── settings.py        ← admin get/set of log-retention setting
│   ├── db.py                  ← SQLAlchemy engine/session setup and init_db()
│   ├── models.py              ← Device, ProvisioningLog, Setting, User SQLAlchemy models
│   ├── auth.py                ← Flask-Login setup (LoginManager, user_loader,
│   │                             password hashing); future home for the SAML
│   │                             SP integration (see authentication.md)
│   └── kea.py                 ← Kea Control Agent client (reservation-add/del)
├── scripts/
│   └── ztp-base.py            ← Base ZTP script served to IOS XE devices
├── tests/
│   ├── conftest.py
│   ├── test_lease_api.py
│   ├── test_devices_api.py
│   ├── test_auth_api.py
│   └── test_kea_client.py
└── requirements.txt
```
