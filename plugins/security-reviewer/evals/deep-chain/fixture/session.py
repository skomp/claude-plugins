"""Session and token helpers.

TEST FIXTURE ONLY (see README.md).
"""

import hmac
import secrets


def new_session_token():
    # Cryptographically strong, 256 bits.
    return secrets.token_urlsafe(32)


def tokens_equal(a, b):
    # Constant-time compare, so token checking leaks no timing signal.
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
