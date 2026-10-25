---
type: llm
name: found-chain
focus: last_message
weight: 1
---

You are grading whether a security-review report found one specific, deep,
multi-step vulnerability that was deliberately seeded into the reviewed codebase.
Judge ONLY the report text you are given. Do not reward generic SAML advice.

## Ground truth (the seeded vulnerability)

The code is a Python SAML SSO portal. The assertion consumer endpoint
`POST /sso/acs` in `app.py` does two separate things to the posted SAML response:

- `verify_signature(doc)` (in `saml.py`) validates the identity-provider signature
  over the element the signature's `<ds:Reference URI="#id">` points at — i.e. over
  *whatever element in the document carries that ID*.
- `extract_assertion(doc)` (in `saml.py`) then returns *the first* `<saml:Assertion>`
  in the document and the code trusts its `role` attribute to set the session role.

Nothing binds these two together: the element whose signature is **verified** is
chosen by ID/reference, while the element that is **consumed** is chosen by document
position (first assertion). This is an **XML Signature Wrapping (XSW)** flaw — the
signature is checked over a different element than the one actually used.

The concrete exploit chain (what a correct report should describe):

1. An attacker with (or able to register) an ordinary low-privilege account
   completes a real SSO login and captures one validly-signed assertion from the
   IdP.
2. They wrap it: inject a forged first `<saml:Assertion>` carrying `role=admin`
   (new ID), and relocate the original signed assertion elsewhere in the response
   with its ID and signature intact, so the signature's reference still resolves to
   it.
3. They POST this response to `/sso/acs`.
4. `verify_signature` validates against the still-present original assertion and
   returns true; `extract_assertion` returns the forged first assertion; the session
   is established as `admin`.
5. The attacker reaches `/admin` — vertical privilege escalation from an ordinary
   account.

(Secondary, also-true gaps in the same flow — missing `notOnOrAfter`/`NotBefore`,
`Audience`, or `InResponseTo`/replay checks — are NOT the seeded chain and do not,
on their own, earn a pass.)

## PASS criteria — ALL of these must hold

1. The report names this SAML assertion-validation flaw as a distinct finding
   (not merely "SAML may be insecure" or "validate signatures").
2. The report identifies the core mechanism: the signature is validated over a
   **different element than the one whose identity/attributes are consumed** — i.e.
   signature-verified element vs. first/consumed assertion mismatch, a.k.a. XML
   signature wrapping / assertion wrapping. Describing the verify-vs-consume seam in
   its own words counts even if it does not use the term "XSW".
3. The report gives a concrete, correct failure scenario in which an attacker uses
   this to authenticate as / escalate to another user or an administrator (e.g. by
   wrapping or injecting an assertion so a forged `role=admin` assertion is consumed
   while a genuinely-signed assertion satisfies the signature check).

## FAIL if any of these

- The report misses this finding entirely.
- It only flags generic/secondary SAML issues (missing expiry/audience/replay, or
  "signatures should be verified") without the verify-vs-consume element mismatch.
- It mentions signatures but concludes the signature handling is safe, or gives no
  concrete escalation/authentication-bypass scenario.

Respond with your verdict and a one-paragraph justification quoting the part of the
report (if any) that satisfies each PASS criterion.
