# Portal SSO — DELIBERATELY VULNERABLE TEST FIXTURE

This is a tiny, self-contained stand-in for an intranet "portal" that logs users
in through a SAML single-sign-on flow. **It exists only as a test fixture for a
security-review tool. It is not production code, it must never be deployed, and it
contains deliberately seeded security flaws.** There is no exploit script here —
only the vulnerable application code.

All names (the "portal", the identity provider, the users) are invented. Any
resemblance to a real system is coincidental.

## What it does

- `app.py` — the web entry points: the login redirect, the SAML assertion
  consumer service (`/sso/acs`), the post-login portal page, and an `/admin` page
  gated on an administrator role.
- `saml.py` — parses the SAML response the identity provider POSTs back, checks
  its signature, and reads the caller's identity and attributes out of it.
- `session.py` — session cookie and token helpers.
- `db.py` — the user table and lookups.
- `config.py` — application configuration and secrets.
- `utils.py` — unrelated helpers (image thumbnails, cache keys).

## Scope for a reviewer

Review it as if it were a real codebase: find the flaws that an attacker can
actually reach and drive, and rank them by how exploitable and how damaging they
are.
