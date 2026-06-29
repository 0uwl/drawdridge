# Authentication

Drawbridge's management UI/API (device allowlist CRUD, script management,
user management) requires an authenticated operator session. Devices and Kea
are unaffected — `/api/lease-event`, `/api/provision-complete`, and the
device-facing `/scripts/<filename>` fetch stay unauthenticated, gated only by
network isolation per the threat model in [architecture.md](architecture.md).

**Flask-Login** owns session/identity (`LoginManager`, `current_user`,
`@login_required`, `UserMixin` on the `User` model — see
[database.md](database.md)). It was chosen over a batteries-included
extension like Flask-Security-Too because it has no opinion about *how* a
user is authenticated — it only tracks who is currently logged in. That
separation matters here: local logins call `check_password_hash()` against
`User.password_hash` and then `login_user()`; a future SAML login validates
the IdP assertion and then calls the same `login_user()`. Passwords are
hashed with Werkzeug's `generate_password_hash`/`check_password_hash`
(already a Flask dependency — no new password library needed).

Local and SAML authentication are intended to coexist indefinitely, not
SAML-replaces-local — `User.auth_source` distinguishes them and
`password_hash` stays nullable for SAML-only accounts.

## Planned: SAML SP integration

Not implemented yet. When added:
- `python3-saml` (OneLogin's toolkit) will handle SP metadata, the
  `AuthnRequest`, and assertion validation — there's no need for a
  Flask-specific SAML extension on top of Flask-Login.
- New routes in `drawbridge/api/auth.py`: `GET /saml/metadata` (SP metadata
  for IdP configuration), `GET /saml/login` (redirect to IdP), `POST
  /saml/acs` (Assertion Consumer Service — validates the assertion, upserts
  the `User` row keyed on `saml_issuer`+`saml_subject`, calls `login_user()`).
- SP certificate/key and IdP metadata will be config, not hardcoded, mounted
  similarly to how `/app/scripts` is mounted today.
- `requirements.txt` will pick up `python3-saml` only once this is actually
  built, not speculatively now.
