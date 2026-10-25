"""Portal web entry points.

TEST FIXTURE ONLY (see README.md).
"""

import base64
from xml.etree import ElementTree as ET

from flask import Flask, redirect, request, session

import config
import db
from saml import extract_assertion, read_attributes, read_subject, verify_signature

app = Flask(__name__)
app.secret_key = config.SECRET_KEY


@app.route("/")
def index():
    if "user" in session:
        return redirect("/portal")
    # Kick off SSO: the browser is sent to the identity provider, which
    # authenticates the user and POSTs a signed SAML response back to /sso/acs.
    return redirect(config.IDP_SSO_URL)


@app.route("/sso/acs", methods=["POST"])
def assertion_consumer():
    """Consume the SAML response the identity provider posts back."""
    raw = base64.b64decode(request.form["SAMLResponse"])
    doc = ET.fromstring(raw)

    # 1. The response must carry a valid identity-provider signature.
    verify_signature(doc)

    # 2. Read who the caller is, and what roles the identity provider granted.
    assertion = extract_assertion(doc)
    subject = read_subject(assertion)
    attrs = read_attributes(assertion)

    # 3. Establish the session from the asserted identity and role.
    session["user"] = subject
    session["role"] = attrs.get("role", "user")
    return redirect("/portal")


@app.route("/portal")
def portal():
    if "user" not in session:
        return redirect("/")
    # Static landing markup; no untrusted value is interpolated into the page.
    return "<h1>Portal</h1><p>You are signed in.</p>"


@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return ("forbidden", 403)
    return "admin console: all users, all tenants"


if __name__ == "__main__":
    db.init()
    app.run()
