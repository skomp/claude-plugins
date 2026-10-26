"""Portal configuration.

TEST FIXTURE ONLY (see README.md).
"""

import os

IDP_SSO_URL = os.environ.get(
    "PORTAL_IDP_SSO_URL", "https://idp.example-portal.test/sso"
)

SECRET_KEY = os.environ.get("PORTAL_SECRET_KEY")
if SECRET_KEY is None:
    if os.environ.get("FLASK_ENV") == "development":
        SECRET_KEY = "dev-only-insecure-placeholder-change-me"
    else:
        raise RuntimeError(
            "PORTAL_SECRET_KEY must be set outside the development environment"
        )
