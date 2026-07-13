from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from collections import defaultdict, deque

from cryptography.fernet import Fernet, InvalidToken

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def totp_code(secret: str, timestamp: float | None = None) -> str:
    moment = time.time() if timestamp is None else timestamp
    counter = int(moment // 30)
    padding = "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(secret.upper() + padding)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def verify_totp(secret: str, code: str, timestamp: float | None = None) -> bool:
    moment = time.time() if timestamp is None else timestamp
    return len(code) == 6 and code.isdigit() and any(
        hmac.compare_digest(totp_code(secret, moment + offset * 30), code) for offset in (-1, 0, 1)
    )


def encrypt_secret(secret: str, key: bytes) -> str:
    return Fernet(key).encrypt(secret.encode()).decode()


def decrypt_secret(secret: str, key: bytes) -> str:
    try:
        return Fernet(key).decrypt(secret.encode()).decode()
    except InvalidToken as error:
        raise ValueError("sensitive setting cannot be decrypted") from error


class LoginRateLimiter:
    def __init__(self, attempts: int = 5, window_seconds: int = 300) -> None:
        self.attempts = attempts
        self.window_seconds = window_seconds
        self.failures: dict[str, deque[float]] = defaultdict(deque)

    def allowed(self, key: str) -> bool:
        self._prune(key)
        return len(self.failures[key]) < self.attempts

    def failed(self, key: str) -> None:
        self._prune(key)
        self.failures[key].append(time.monotonic())

    def succeeded(self, key: str) -> None:
        self.failures.pop(key, None)

    def _prune(self, key: str) -> None:
        oldest = time.monotonic() - self.window_seconds
        while self.failures[key] and self.failures[key][0] < oldest:
            self.failures[key].popleft()
