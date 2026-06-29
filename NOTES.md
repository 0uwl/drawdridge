# drawbridge starter package

Carried over from `../backend/` (ZTP 1.0) — everything here is generic Flask
boilerplate, not tied to the 1.0 Redis/device-self-registration model:

- `drawbridge/main.py` — `create_app()` factory: config loading, gunicorn
  logger wiring, `/health` check. Dropped the hardcoded `app.secret_key` from
  1.0 — it was dead code (no Flask session/flash usage anywhere in 1.0).
- `drawbridge/utils.py` — `success_response`/`error_response` envelope
  helpers, `allowed_file()` extension check, and a file-hash helper switched
  from MD5 to **SHA-256** to match the "SHA-256 hash verification"
  requirement in `docs/drawbridge.md`.
- `gunicorn.conf.py` — same worker config, bind port changed to `8080`
  per the architecture doc (1.0 used 5000).
- `Containerfile` — adapted to the doc's container spec: `python:3.12-slim`,
  non-root `appuser`, binds at 8080, `/app/data` + `/app/scripts` left as
  mount points rather than baked-in content.
- `requirements.txt` — dropped `redis` (Drawbridge uses SQLite, not Redis).
- `tests/conftest.py` — `app`/`client` fixture pattern from 1.0, swapped to
  use a `tmp_path`-based SQLite file per the doc's testing approach.

## Not included — still needs to be designed/written

Nothing in 1.0 implements the actual Drawbridge architecture, so none of
this exists yet (see `docs/drawbridge.md` for the target shape):

- `drawbridge/db.py` — SQLite schema + connection handling (`devices`,
  `provisioning_events` tables).
- `drawbridge/models.py` — `Device`, `ProvisioningEvent` dataclasses.
- `drawbridge/kea.py` — Kea Control Agent client (`reservation-add`/`reservation-del`).
- `drawbridge/api/lease.py`, `devices.py`, `scripts.py` — the actual endpoints
  (`/api/lease-event`, `/api/devices`, `/scripts/<filename>`, etc).
- The Kea `leases4_committed` hook/callout itself (C++ or Python) and the
  `kea-dhcp4.conf` / `kea-ctrl-agent.conf` configs — the DHCP park/unpark
  gate is the core of Drawbridge and has no equivalent in 1.0 at all.
- Quadlet unit for the rootless Podman deployment.

The 1.0 `cisco-ztp.py` device script's HTTP-via-guest-shell-`copy`-command
workaround is also worth re-reading before assuming the device side can do
real TLS cert validation "inside the script" as the architecture doc
currently states.
