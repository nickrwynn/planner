from __future__ import annotations

import base64
import hashlib
import hmac
import os

from app.core.config import get_settings


def _secret_bytes() -> bytes:
    settings = get_settings()
    raw = (settings.integrations_secret or settings.auth_jwt_secret or "dev-integrations-secret").strip()
    return hashlib.sha256(raw.encode("utf-8")).digest()


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a short secret for at-rest storage (solo/dev)."""
    key = _secret_bytes()
    data = plaintext.encode("utf-8")
    nonce = os.urandom(16)
    stream = bytearray()
    counter = 0
    while len(stream) < len(data):
        stream.extend(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    cipher = bytes(a ^ b for a, b in zip(data, stream))
    mac = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + mac + cipher).decode("ascii")


def decrypt_secret(token: str) -> str:
    key = _secret_bytes()
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    if len(raw) < 48:
        raise ValueError("Invalid encrypted token")
    nonce, mac, cipher = raw[:16], raw[16:48], raw[48:]
    expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Invalid encrypted token MAC")
    stream = bytearray()
    counter = 0
    while len(stream) < len(cipher):
        stream.extend(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    plain = bytes(a ^ b for a, b in zip(cipher, stream))
    return plain.decode("utf-8")
