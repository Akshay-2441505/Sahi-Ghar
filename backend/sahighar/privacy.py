"""One-way tokens for personal identifiers (PAN, personal names), so they can be matched but never shown or recovered.

The database stores tokens, never the raw value. A token is an HMAC of the normalised value under a secret key
(SAHIGHAR_PII_KEY): the same person gets the same token everywhere, so two records can be linked, but a leaked
database cannot be reversed by guessing PANs (there are few enough that unkeyed hashes would fall to brute force).
Keep the key out of the repository; changing it invalidates every stored token (re-import to regenerate).
"""
import hashlib
import hmac
import os
import re


class PrivacyKeyMissing(RuntimeError):
    pass


def _normalise(kind: str, value: str) -> str:
    if kind == "pan":
        return re.sub(r"\s+", "", value).upper()
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()  # names: case, spacing and punctuation do not matter


def tokenize(kind: str, value: str) -> str:
    key = os.environ.get("SAHIGHAR_PII_KEY")
    if not key:
        raise PrivacyKeyMissing("set SAHIGHAR_PII_KEY (any long random string, kept secret) before loading personal identifiers")
    digest = hmac.new(key.encode(), f"{kind}\0{_normalise(kind, value)}".encode(), hashlib.sha256).hexdigest()
    return f"{kind}:{digest[:24]}"
