# Alpha Implementation Plan

## Scope

Alpha is "done" when:
- The full backend (DB, auth, all API blueprints) is implemented and tested per
  [docs/testing.md](docs/testing.md), runnable via `flask run` against SQLite —
  no container required.
- `/api/lease-event` is fully implemented and verified via direct HTTP calls
  (pytest + curl/Postman simulating what the Kea hook would send), not against
  a live Kea instance. The `kea/` configs and the hook callout are written as
  code so they're ready to test against real Kea later, but a working Kea box
  is not a gate for alpha sign-off.
- A minimal Vue admin UI exists: login, device list/add/remove, provisioning
  log view. Users and settings management can be bare-bones (a working form is
  enough; polish is a follow-up).
- Auth is local username/password only via Flask-Login. SAML fields stay on
  the `User` model (already documented) but SP integration is not built.
- Containerfile/Quadlet are out of scope for alpha sign-off — validated in a
  later phase.

Everything below follows the schema, contracts, and decisions already
recorded in `docs/`. This plan does not redesign anything — it sequences the
implementation.

## Current state (as of this plan)

Implemented: `drawbridge/main.py` (app factory, `/health`, static-serving
catch-all route), `drawbridge/utils.py` (response envelopes, file hashing),
`tests/conftest.py` (app/client fixtures), frontend scaffolding (Vite config,
placeholder `App.vue`).

Not yet implemented: `drawbridge/db.py`, `drawbridge/models.py`,
`drawbridge/auth.py`, `drawbridge/kea.py`, all of `drawbridge/api/`, all
`kea/*` config files and the hook callout, `scripts/ztp-base.py`, all real
test files, all real frontend views.

## Step-by-step

### 1. Database layer (DONE)
- `drawbridge/models.py`: `Device`, `ProvisioningLog`, `Setting`, `User`
  exactly per [docs/database.md](docs/database.md) schema.
- `drawbridge/db.py`: SQLAlchemy `Engine`/`sessionmaker`, `init_db(app)`
  (`Base.metadata.create_all()` + seed `Setting(log_retention_days)` from
  `LOG_RETENTION_DAYS` env var on first run), WAL + `busy_timeout` connect
  event listener, request-scoped session via `app.teardown_appcontext`.
- Wire `init_db(app)` into `create_app()` in `main.py` (the TODO already
  marks where).
- Engine must be created inside `create_app()`, not at module import time
  (post-fork safety under Gunicorn — see decisions.md).

### 2. Auth foundation (DONE)
- `drawbridge/auth.py`: `LoginManager` setup, `user_loader`, password hashing
  via Werkzeug (`generate_password_hash`/`check_password_hash`).
- **First-admin bootstrap**, triggered from `init_db(app)` in `db.py`: check
  whether `DATABASE_PATH` exists on disk *before* `create_all()` runs. If it
  doesn't (first run), after creating the schema, insert
  `User(username='admin', role='admin', auth_source='local')` with a
  randomly generated 12-character password (`secrets.choice` over
  letters+digits — cryptographically random, not `random`), hash it with
  Werkzeug, and print the plaintext password to stdout once:
  `Drawbridge: created initial admin user 'admin', password: <pw> — record this now, it will not be shown again.`
  This only ever fires on the missing-DB-file path, never on subsequent
  starts against an existing DB.

### 3. Kea Control Agent client (DONE)
- `drawbridge/kea.py`: thin client for `reservation-add`/`reservation-del`
  against `KEA_CTRL_URL`/`KEA_SUBNET_ID`. Fail closed on unreachable/error
  responses (raise, don't swallow) — callers decide the HTTP response.

### 4. API blueprints (`drawbridge/api/`)
Build and register in this order, each with its tests immediately after
(per [docs/testing.md](docs/testing.md)) rather than batching all routes
before any tests:

1. `auth.py` — `POST /api/auth/login`, `POST /api/auth/logout`,
   `GET /api/auth/me`.
2. `devices.py` — `GET/POST /api/devices`, `GET/DELETE /api/devices/<serial>`.
   POST is idempotent on re-registering the same serial. DELETE calls
   `reservation-del` via `drawbridge/kea.py`.
3. `lease.py` — `POST /api/lease-event`. The core security gate: known serial
   → 200 + `reservation-add` confirmation; unknown → 403; Kea Control Agent
   unreachable on approval path → fail closed (non-200). Must stay inside the
   2s `LEASE_EVENT_TIMEOUT` budget — keep the transaction short.
4. `scripts.py` — `GET /scripts/<filename>` (unauthenticated device-facing
   fetch) and the authenticated management variant for script upload/listing.
   `POST /api/provision-complete` (device reports outcome; deletes the
   `devices` row, writes `ProvisioningLog`).
5. `users.py` — admin-only CRUD for operator accounts.
6. `settings.py` — `GET/PUT /api/settings/log-retention`, admin-only on PUT.
   Wire the lazy-purge-on-insert logic here and into the `ProvisioningLog`
   insert path used by `lease.py`/`scripts.py`.

Register all blueprints in `create_app()` (the TODO already marks where) and
apply `@login_required` per the matrix in [docs/api.md](docs/api.md) — only
`/api/lease-event`, `/api/provision-complete`, and the device-facing
`/scripts/<filename>` stay open.

### 5. Base ZTP script
- `scripts/ztp-base.py`: a stub for alpha, not a real provisioning script.
  Purpose is to exercise the serve/fetch/callback contract end-to-end for
  testing — it emulates what a device would request and POST back, nothing
  more. Real Day-0 IOS XE provisioning logic (cert validation, hash
  verification, actual config push) is deliberately deferred to a later
  phase once this is tested against real hardware.
- Keep it to stdlib only (`urllib`/`http.client`/`ssl`, no `requests` or
  other third-party imports, no f-strings or other syntax assumptions) —
  IOS XE's onboard Python environment (Guestshell) is restrictive, and
  whatever gets written now should not need a rewrite later just to run
  there. Procedural, not class-based.

### 6. Kea-side artifacts (code, not validated live this phase)
- `kea/kea-dhcp4.conf`, `kea/kea-ctrl-agent.conf` per
  [docs/kea.md](docs/kea.md).
- `kea/hook/` — the `leases4_committed` callout: POST to
  `/api/lease-event`, CONTINUE on 200 / DROP otherwise, 2s timeout.
- Not gated by a live Kea instance for alpha sign-off, but should be
  internally consistent with the now-implemented `/api/lease-event` contract.

### 7. Test suite
Fill out `tests/` per [docs/testing.md](docs/testing.md)'s checklist:
`test_lease_api.py`, `test_devices_api.py`, `test_auth_api.py`,
`test_kea_client.py`, plus users/settings/provisioning-log coverage. Mock
`drawbridge/kea.py` calls — no live Kea dependency. Include the
multi-worker-style concurrent-write test.

### 8. Minimal frontend
Stack: Vue Router for navigation, **Pinia** for state, **axios** for HTTP.
API access is centralized in Pinia stores, not components — components call
store actions and read store state; they never import axios directly. This
keeps each domain's request/error/loading handling in one place regardless
of where in the tree a component sits.

- `frontend/src/api/client.js` — single configured axios instance
  (`withCredentials: true` for session cookies, a response interceptor that
  normalizes the `{success, message, payload/error}` envelope from
  `drawbridge/utils.py` and redirects to `/login` on a 401).
- `frontend/src/stores/` — one Pinia store per domain, each owning its own
  axios calls against `client.js`:
  - `auth.js` — `login()`, `logout()`, `fetchMe()`, holds `currentUser`.
  - `devices.js` — `list()`, `add()`, `remove()`.
  - `log.js` — `fetchLog()`.
  - `users.js`, `settings.js` — bare-bones CRUD/get-set, admin-only.
- Views: Login, Devices (list/add/remove), Log, Users, Settings — each thin,
  delegating to its store.
- Vue Router so the catch-all `index.html` fallback in `main.py` has routes
  to resolve on a hard refresh; a navigation guard redirects to `/login`
  when `auth.currentUser` is unset.
- Manual pass through `scripts/dev.sh` (Flask + Vite dev server) to confirm
  the golden path: log in as the bootstrapped admin, register a device,
  simulate a lease-event via curl, confirm it shows in the log, remove the
  device.

### 9. End-to-end manual verification (no live Kea)
- `pytest` green.
- `flask run` + curl sequence simulating the full DHCP flow against
  `/api/lease-event` and `/api/provision-complete` by hand, confirming DB
  state transitions (`devices` row created → deleted, `ProvisioningLog` rows
  appended) match [docs/architecture.md](docs/architecture.md)'s DHCP Flow.
- UI smoke test per step 8.

## Resolved decisions

1. **First admin bootstrap** — see step 2. Triggered by absence of the DB
   file at `DATABASE_PATH`, not an env var or CLI command. Username
   `admin`, password is a random 12-character string printed to stdout
   once, never persisted in plaintext.
2. **`scripts/ztp-base.py`** — stub only for alpha (see step 5). Real
   on-device provisioning logic is a later phase, scoped once tested
   against actual IOS XE hardware.
3. **Frontend stack** — Vue Router + Pinia + axios, with API calls
   centralized in Pinia stores rather than components (see step 8).
4. **`tests/dev-data`** — holding directory for the SQLite file
   `scripts/dev.sh` creates during a live dev session; reused as the
   location for test-suite fixtures/seed data once the test suite is built
   in step 7.
