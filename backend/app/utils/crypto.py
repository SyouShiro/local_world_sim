from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretCipher:
    """Encrypt and decrypt sensitive strings using a derived key."""

    def __init__(self, secret: str) -> None:
        if not secret:
            raise ValueError("APP_SECRET_KEY is required for encryption.")
        key = self._derive_key(secret)
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        """Encrypt a plain string into a URL-safe token."""

        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, token: str) -> str:
        """Decrypt a previously encrypted token."""

        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:  # noqa: BLE001
            raise ValueError("Failed to decrypt provider secret.") from exc

    @staticmethod
    def _derive_key(secret: str) -> bytes:
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)
