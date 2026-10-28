"""Remembered owner sessions for the dashboard's optional module visibility login."""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time

SESSION_SECONDS = 90 * 24 * 60 * 60


def encode(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def password_matches(candidate, password):
    return bool(password) and isinstance(candidate, str) and len(candidate) <= 256 and hmac.compare_digest(
        hashlib.sha256(candidate.encode()).digest(), hashlib.sha256(password.encode()).digest())


def issue_session(password):
    payload = encode(json.dumps({"exp": int(time.time()) + SESSION_SECONDS, "nonce": secrets.token_hex(16)},
                                separators=(",", ":")).encode())
    signature = encode(hmac.new(password.encode(), payload.encode(), hashlib.sha256).digest())
    return payload + "." + signature


def valid_session(token, password):
    if not password or not isinstance(token, str) or len(token) > 2048:
        return False
    try:
        payload, signature = token.split(".")
        expected = encode(hmac.new(password.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return False
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return time.time() < data["exp"] <= time.time() + SESSION_SECONDS
    except (ValueError, TypeError, KeyError, UnicodeError):
        return False


class LoginLimiter:
    def __init__(self):
        self.attempts = {}
        self.lock = threading.Lock()

    def allow(self, key):
        with self.lock:
            now = time.time()
            self.attempts = {k: v for k, v in self.attempts.items() if v[0] > now}
            until, count = self.attempts.get(key, (now + 60, 0))
            if count >= 5:
                return False
            self.attempts[key] = (until, count + 1)
            return True
