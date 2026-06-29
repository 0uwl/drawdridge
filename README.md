# Drawbridge

A hardened, classic Zero Touch Provisioning (ZTP) system for Cisco IOS XE
devices — without relying on Cisco's PKI/Secure ZTP infrastructure.

## Why

Classic ZTP is simple but insecure. Cisco's Secure ZTP (RFC 8572) fixes that,
but requires trusting Cisco's MASA service and PKI as a third party —
incompatible with a fully airgapped deployment. Drawbridge takes a third
path: it hardens classic ZTP using infrastructure the organization already
controls.

- Kea DHCP pre-authorisation gate (lease withheld until Drawbridge approves)
- Serial number / client-id allowlisting
- HTTPS script delivery with server certificate validation inside the script
- SHA-256 hash verification of images and config payloads

Drawbridge is **not** an inventory management system — device serials/MACs
are only tracked for the brief window between registration and
provisioning, then dropped in favor of a retention-bounded provisioning log.

## Documentation

| Topic | Covers |
|---|---|
| [Architecture](docs/architecture.md) | What this is, why not sZTP, system diagram, DHCP flow, repo layout |
| [Web API](docs/api.md) | Flask endpoints, the `/api/lease-event` contract, auth requirements |
| [Database](docs/database.md) | SQLAlchemy schema, multi-worker SQLite concurrency, log retention |
| [Authentication](docs/authentication.md) | Flask-Login, password hashing, planned SAML SP integration |
| [Frontend](docs/frontend.md) | Vue/Vite admin UI, dev-server proxy workflow, how it's baked into the container |
| [Kea Configuration](docs/kea.md) | Control Agent, DHCPv4 config, the `leases4_committed` hook |
| [Deployment](docs/deployment.md) | Containerfile, Quadlet, dev setup, environment variables |
| [Testing](docs/testing.md) | Testing approach and key cases |
| [Decisions & Constraints](docs/decisions.md) | Design tradeoffs and the reasoning behind each |

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
```

See [docs/deployment.md](docs/deployment.md) for running the app locally,
building the container, and the full list of environment variables.
