# Ground truth for the deep-chain fixture (ANSWER KEY)

This file is the answer key for the `deep-chain` eval. **It is deliberately kept
out of the copy of the fixture the reviewer sees** (the scaffold script copies
every fixture file except this one), so the review is judged against ground truth
it never read. Do not point the reviewer at this file.

## The seeded deep, multi-step vulnerability (the one that must be found)

**XML Signature Wrapping (XSW) in the SAML assertion consumer: the signature is
validated over a different element than the one whose identity and attributes are
consumed.** This is an authentication / privilege-escalation flaw, not a one-line
pattern.

The signature itself is sound: `verify_signature()` recomputes a keyed MAC
(HMAC under the IdP's out-of-band signing key, which the attacker does not have)
over the referenced element and compares it to the `<ds:SignatureValue>`. So an
attacker cannot forge a signature over content of their choosing — the ONLY way
through is to reuse a genuinely-signed element while getting a different element
consumed. That is the wrapping.

### Where it lives

- `saml.py` `verify_signature()` — follows the signature's
  `<ds:Reference URI="#id">` and validates the keyed MAC over *the element in the
  document that carries that ID, wherever it sits in the tree*. It confirms only
  that *some* element with the referenced ID is validly signed by the IdP.
- `saml.py` `extract_assertion()` — returns *the first* `<saml:Assertion>` in the
  document (`doc.find(".//saml:Assertion")`), with no link back to which element
  the signature actually covered.
- `app.py` `assertion_consumer()` (`POST /sso/acs`) — calls `verify_signature(doc)`
  and then, separately, `extract_assertion(doc)`, and trusts the `role` attribute
  of whatever that returns to set `session["role"]`.

The two steps use **different selectors against the same document**: one validates
the *referenced* element, the other consumes the *first* assertion. Nothing
enforces that they are the same element. That seam is the vulnerability.

### The concrete failure scenario (what the grader must see matched)

1. The attacker owns, or can register, a normal low-privilege account, so they can
   complete a genuine SSO login and **capture one validly-signed assertion** from
   the identity provider (role `user`, with its real `ID` and IdP signature).
2. They rebuild the SAML response: they **inject a forged `<saml:Assertion>` as
   the first assertion** in the response, carrying
   `<saml:Attribute Name="role"><saml:AttributeValue>admin</saml:AttributeValue>`
   and a new `ID`. They **relocate the original, still-intact signed assertion**
   (its original `ID` and `<ds:Signature>` untouched) to a nested/sibling position
   so the signature's `<ds:Reference URI="#originalID">` still resolves to it.
3. They base64-encode this response and **POST it to `/sso/acs`**.
4. `verify_signature()` finds the signature, resolves the reference to the
   original assertion (still present, digest still matches, cert still the IdP's)
   and returns `True`.
5. `extract_assertion()` returns the *forged first* assertion;
   `read_attributes()` reads `role=admin`; the session is created as an
   administrator.
6. The attacker loads `/admin` and reaches the admin console — full vertical
   privilege escalation from an ordinary account.

### Why a pattern-matcher misses it

Grepping `saml.py` shows a signature check that resolves a reference, recomputes a
digest, and compares a certificate fingerprint — it reads as "signature verified".
The flaw is only visible by tracing the trust boundary across two functions and
noticing that the element that is *verified* is selected by ID while the element
that is *consumed* is selected by document position, with no binding between them.
Related, also-true gaps in the same flow (no `notOnOrAfter`/`NotBefore` check, no
`Audience`, no `InResponseTo`/replay protection) are secondary; the headline is
the verify-vs-consume element mismatch (XSW).

## The benign noise (should be dropped or ranked low, not reported as real vulns)

These look scary to a scanner but have no attacker-reachable trigger path or no
real security value. A good report drops them or keeps them clearly low and few:

1. **`db.py` `seed_demo_users()`** — an f-string `INSERT` that looks like SQL
   injection, but the id is a loop counter and the name/role come from the fixed
   `_DEMO_USERS` list; nothing is request-derived. No trigger path
   (`exploitability: none`). `get_user()` right above it is correctly
   parameterized.
2. **`config.py` `SECRET_KEY`** — a hardcoded-looking secret, but it is a labelled
   development-only fallback used solely when `FLASK_ENV=development`; the app
   raises and refuses to start in any other environment. No production trigger
   path.
3. **`utils.py` `thumbnail_cache_key()`** — MD5, which trips "weak hash" scanners,
   but it only names a cache file and guards nothing. Informational at most.
4. **`utils.py` `make_thumbnail()`** — a `subprocess.run` that looks like command
   execution, but it uses a fixed binary, list-form arguments (no shell), and
   server-chosen temp paths, never request strings. Safe.
5. **`session.py`** — uses `secrets.token_urlsafe` and `hmac.compare_digest`
   correctly; a scanner may flag "token"/"compare" but there is nothing here.

## Expected discrimination

- A thorough trust-boundary review (the plugin) should name the XSW / verify-vs-
  consume mismatch with the escalation scenario, and should not present the five
  noise items as real vulnerabilities.
- A quick ad-hoc review tends to accept `verify_signature()` as "signatures are
  checked" and miss the cross-function seam, and/or spend its findings on the
  MD5/subprocess/secret pattern hits.
