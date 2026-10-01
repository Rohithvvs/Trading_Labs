"""Encrypt / decrypt broker access tokens at rest.

Uses Fernet (AES-128-CBC + HMAC) with a key derived from TOKEN_ENCRYPTION_KEY
or JWT_SECRET. Ciphertext is stored as ``enc:v1:<base64>`` so legacy plaintext
rows can still be read until re-saved.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger("app.token_crypto")

_PREFIX = "enc:v1:"
_fernet = None


def _make_single_fernet(secret: str):
    from cryptography.fernet import Fernet
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    try:
        from cryptography.fernet import Fernet
        from cryptography.fernet import MultiFernet
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("cryptography package is required for token encryption") from exc

    candidates: list[str] = []
    for s in (
        os.getenv("TOKEN_ENCRYPTION_KEY"),
        os.getenv("JWT_SECRET"),
    ):
        if s and str(s).strip() and str(s).strip() not in candidates:
            candidates.append(str(s).strip())

    if not candidates:
        try:
            from pathlib import Path
            from dotenv import load_dotenv
            root_env = Path(__file__).resolve().parents[3] / ".env"
            if root_env.exists():
                load_dotenv(root_env, override=False)
                for s in (os.getenv("TOKEN_ENCRYPTION_KEY"), os.getenv("JWT_SECRET")):
                    if s and str(s).strip() and str(s).strip() not in candidates:
                        candidates.append(str(s).strip())
        except Exception:
            pass

    try:
        from ..config import settings
        jwt_s = getattr(settings, "jwt_secret", None)
        if jwt_s and str(jwt_s).strip() and str(jwt_s).strip() not in candidates:
            candidates.append(str(jwt_s).strip())
    except Exception:
        pass

    fallback = "yoursecretkey_must_be_changed_in_prod"
    if fallback not in candidates:
        candidates.append(fallback)

    fernets = [_make_single_fernet(key) for key in candidates]
    _fernet = MultiFernet(fernets)
    return _fernet


def encrypt_secret(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    text = str(plaintext)
    if not text:
        return text
    if text.startswith(_PREFIX):
        return text  # already encrypted
    try:
        token = _get_fernet().encrypt(text.encode("utf-8"))
        return f"{_PREFIX}{token.decode('utf-8')}"
    except Exception:
        logger.error("TOKEN_ENCRYPT_FAILED | encryption failed", exc_info=True)
        raise


def decrypt_secret(value: str | None) -> str | None:
    """Decrypt if prefixed; otherwise return as plaintext (legacy rows)."""
    if value is None:
        return None
    text = str(value)
    if not text.startswith(_PREFIX):
        return text
    blob = text[len(_PREFIX):]
    try:
        return _get_fernet().decrypt(blob.encode("utf-8")).decode("utf-8")
    except Exception:
        logger.error("TOKEN_DECRYPT_FAILED | ciphertext could not be decrypted")
        raise


def mask_secret(token: str | None, keep: int = 4, max_stars: int = 24) -> str | None:
    """Mask a secret for UI/DB display, e.g. ************************ABCD.

    Always returns a **short** fixed-size string (max 100 chars) so:
    - it fits ``token_masked VARCHAR(512)`` with large headroom
    - masking cost/size is O(1) even for multi-KB JWTs
    - middle/prefix of the secret is never exposed
    - never stores hundreds of '*' proportional to JWT length
    """
    if not token:
        return None
    t = str(token)
    if len(t) <= keep * 2:
        return ("*" * len(t))[:100]
    # Cap stars — never grow with secret length (Fyers JWTs are 500–900+ chars)
    stars = max(8, min(int(max_stars), 48))
    masked = f"{'*' * stars}{t[-keep:]}"
    return masked[:100]


def is_encrypted(value: str | None) -> bool:
    return bool(value and str(value).startswith(_PREFIX))
