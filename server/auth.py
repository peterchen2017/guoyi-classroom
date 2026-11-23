# -*- coding: utf-8 -*-
"""教师登录与口令哈希。不在日志中打印口令。"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

PBKDF2_ROUNDS = 200000
SESSION_HOURS = 12
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def hash_password(password, salt=None):
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return "%s$%s" % (salt.hex(), dk.hex())


def verify_password(password, stored):
    try:
        salt_hex, dk_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return secrets.compare_digest(dk.hex(), dk_hex)


def new_token():
    return secrets.token_urlsafe(32)


def session_expiry():
    when = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    return when.isoformat()


def session_valid(expires_iso):
    try:
        when = datetime.fromisoformat(expires_iso)
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < when


def new_class_code(length=6):
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))
