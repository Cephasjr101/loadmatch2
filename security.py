"""Stdlib-only auth: PBKDF2 password hashing + HS256 JWT. No external crypto deps."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

SECRET_KEY = os.getenv("LOADMATCH_SECRET", secrets.token_hex(32))
ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 60 * 60 * 24  # 24h

PBKDF2_ITERATIONS = 120_000


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def create_access_token(user_id: int, role: str) -> str:
    header = {"alg": ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    signing_input = (
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    )
    signature = hmac.new(
        SECRET_KEY.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    return signing_input + "." + _b64url_encode(signature)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        expected = hmac.new(
            SECRET_KEY.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except (ValueError, json.JSONDecodeError):
        return None
