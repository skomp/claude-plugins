"""SAML response handling for the portal SSO flow.

Signatures use a keyed MAC (HMAC-SHA256) over the canonicalized referenced
element, under the identity provider's signing key, which is provisioned out of
band and read from the environment rather than from this source or the response.
This is a compact stand-in for asymmetric XML-DSig; the surrounding trust
relationships match a real deployment.
"""

import hashlib
import hmac
import os
from xml.etree import ElementTree as ET

NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}

# The identity provider's signing key, provisioned out of band and read from the
# environment.
_IDP_SIGNING_KEY = os.environ.get("PORTAL_IDP_SIGNING_KEY", "").encode("utf-8")


class SamlError(Exception):
    pass


def _find_by_id(doc, elem_id):
    """Return the first element anywhere in the document whose ID/AssertionID
    attribute equals elem_id, or None."""
    for elem in doc.iter():
        if elem.get("ID") == elem_id or elem.get("AssertionID") == elem_id:
            return elem
    return None


def _strip_signature(elem):
    """Return a copy of elem with any enveloped <ds:Signature> removed, so the
    MAC is taken over the element without its own signature (as an enveloped
    signature requires)."""
    clone = ET.fromstring(ET.tostring(elem, encoding="utf-8"))
    for sig in clone.findall("ds:Signature", NS):
        clone.remove(sig)
    return clone


def _signature_over(elem):
    """The keyed MAC the identity provider would produce over this element: an
    HMAC over its canonical form, with the enveloped signature stripped."""
    canon = ET.canonicalize(ET.tostring(_strip_signature(elem), encoding="unicode"))
    return hmac.new(_IDP_SIGNING_KEY, canon.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(doc):
    """Return True if the response carries an identity-provider signature that
    validates over the element the signature references.

    It finds the first <ds:Signature>, follows its single <ds:Reference URI="#id">
    to the element in the document carrying that ID, recomputes the keyed MAC over
    that element, and compares it to the signed <ds:SignatureValue>. If they match
    under the IdP's key, the signature is accepted.
    """
    if not _IDP_SIGNING_KEY:
        raise SamlError("identity-provider signing key is not configured")

    sig = doc.find(".//ds:Signature", NS)
    if sig is None:
        raise SamlError("response is not signed")

    ref = sig.find(".//ds:Reference", NS)
    uri = (ref.get("URI") if ref is not None else "") or ""
    if not uri.startswith("#"):
        raise SamlError("only same-document signature references are supported")
    signed_id = uri[1:]

    signed_elem = _find_by_id(doc, signed_id)
    if signed_elem is None:
        raise SamlError("signed element not found")

    sigval_node = sig.find(".//ds:SignatureValue", NS)
    sigval = sigval_node.text if sigval_node is not None else None
    expected = _signature_over(signed_elem)
    if sigval is None or not hmac.compare_digest(
        sigval.encode("utf-8"), expected.encode("utf-8")
    ):
        raise SamlError("signature invalid")

    return True


def extract_assertion(doc):
    """Return the assertion the portal will trust: the first <saml:Assertion> in
    the response."""
    assertion = doc.find(".//saml:Assertion", NS)
    if assertion is None:
        raise SamlError("response carries no assertion")
    return assertion


def read_subject(assertion):
    nid = assertion.find("saml:Subject/saml:NameID", NS)
    return nid.text if nid is not None else None


def read_attributes(assertion):
    attrs = {}
    stmt = assertion.find("saml:AttributeStatement", NS)
    if stmt is None:
        return attrs
    for attr in stmt.findall("saml:Attribute", NS):
        name = attr.get("Name")
        value = attr.find("saml:AttributeValue", NS)
        attrs[name] = value.text if value is not None else None
    return attrs
