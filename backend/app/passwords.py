"""Password hashing for locally stored accounts.

Uses PBKDF2-HMAC-SHA256 from the standard library so we do not add a native bcrypt
dependency. Passwords are never stored in plaintext.
"""

from __future__ import annotations

import hashlib
import secrets

SCHEME = "pbkdf2_sha256"
ITERATIONS = 600_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"{SCHEME}${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iter_s, salt_hex, digest_hex = stored.split("$", 3)
        if scheme != SCHEME:
            return False
        iterations = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return secrets.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False
