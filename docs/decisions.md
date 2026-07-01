# Decisions and Constraints

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

- **SQLAlchemy ORM.** `Device`, `ProvisioningLog`, `Setting`, and `User` are
  SQLAlchemy models (`drawbridge/models.py`) rather than plain SQL. Sessions
  are request-scoped and short-lived to keep `/api/lease-event` inside Kea's
  2 s park timeout. See [database.md](database.md).

- **Drawbridge is not an inventory system — serials/MACs don't persist.**
  `devices` rows are deleted the moment provisioning completes; only
  `ProvisioningLog` (timestamp, image, config file) survives, and even that
  is subject to a retention window. This is a deliberate scope boundary, not
  an oversight — asset/inventory tracking is a different problem with
  different data-retention requirements, and bolting it on here would push
  Drawbridge toward holding data it has no operational need for.

- **Log retention is an admin-configurable DB setting, default 30 days,
  purged lazily.** `Setting(key='log_retention_days')` is changeable at
  runtime via `/api/settings/log-retention` rather than requiring a
  redeploy; an admin can explicitly opt into `indefinite` retention. Purging
  happens inline on the next `ProvisioningLog` insert rather than via a
  separate scheduled job — no new background process, consistent with "no
  external message queue" below, at the cost of expired rows lingering
  briefly on idle deployments.

- **SQLite concurrency via WAL + busy_timeout, not a switch to a
  client/server database.** Gunicorn runs 4 worker processes
  (`gunicorn.conf.py`), all hitting the same `drawbridge.db` file, so
  multi-worker race conditions on the DB are a real risk, not theoretical.
  Rather than move to Postgres/MySQL — more infrastructure for a
  single-host, physically isolated deployment — concurrency is handled with
  WAL journal mode, a `busy_timeout` tuned under the lease-event 2 s budget,
  app-level retry on `database is locked`, short transactions, and
  per-worker (post-fork) `Engine` creation. See [database.md](database.md)
  ("Concurrency under multiple Gunicorn workers").

- **Flask-Login over Flask-Security-Too.** Flask-Login only tracks the
  current session (`current_user`, `login_user()`, `@login_required`) and
  has no opinion on how a user is authenticated. That seam is deliberate:
  local password login and the planned SAML SP integration both just call
  `login_user()` after validating credentials differently. A
  batteries-included extension would assume password auth as the primary
  flow and fight the SAML addition later.

- **`User` schema is SAML-ready ahead of SAML being built.** `auth_source`,
  `saml_issuer`, and `saml_subject` are on the `users` table now, and
  `password_hash` is nullable, so local and SAML accounts coexist
  indefinitely without a future migration. The actual SAML SP (`python3-saml`,
  new routes in `drawbridge/api/auth.py`) is not implemented yet. See
  [authentication.md](authentication.md).

- **No external message queue.** The Kea hook calls the ZTP server directly
  over HTTP. The PARK mechanism handles the synchronisation. A message queue
  would add complexity with no benefit at this scale.

- **Rootless Podman for the Drawbridge container.** Kea cannot run rootless
  (requires raw socket for DHCP broadcast) so it runs as a native systemd
  service. The Drawbridge container has no such constraint and runs rootless
  under the `drawbridge` user with lingering enabled.

- **Kea Control Agent on 127.0.0.1:8081.** Default Kea port is 8080, which
  conflicts with Drawbridge. Control Agent is bound to loopback only.

- **Facts-first provisioning is deferred, not rejected.** An idea was raised
  for a two-phase flow: a small facts-collector script fetched first, which
  reports device facts (e.g. version/platform) to Drawbridge and gets back
  the appropriate provisioning script to hand off to, rather than one static
  script for all devices. This is a reasonable pattern for heterogeneous
  fleets, but it's real Day-0 provisioning logic — the same category the
  alpha `ztp-base.py` stub deliberately excludes (see alpha.md step 5) — and
  it requires schema/API additions alpha doesn't have: a version/platform
  field on `Device`, and a new endpoint (or facts parameter) for the
  fetch-then-select round trip, plus a second HTTPS/cert-validation hop.
  Scope this once real per-device provisioning logic is built and tested
  against hardware, not before.

- **C9200CX network stack isolation — `/api/provision-complete` accepts PUT.**
  Python scripts running on the C9200CX are entirely isolated from the device's
  own network stack; direct socket calls from the ZTP script fail. The
  workaround is to write the JSON payload to the device filesystem and issue
  `copy flash:status.json http://<drawbridge>/api/provision-complete` from IOS
  XE CLI (via `cli.execute()` in the script). IOS XE's `copy` command issues a
  PUT request, so the endpoint accepts PUT as its primary method. POST is also
  accepted for development and testing. The `Content-Type` header is not
  guaranteed to be set by `copy`, so the endpoint parses the body regardless of
  content type (`force=True`). This constraint applies to all network I/O in the
  ZTP script on C9200CX — image and config downloads must similarly be triggered
  via `cli.execute("copy http://... flash:")` rather than Python's `urllib` or
  `requests`.
