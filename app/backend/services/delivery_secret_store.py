"""Encryption for delivery target secrets."""
import base64
import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet

from config import Config


class DeliverySecretStore:
    def __init__(self) -> None:
        self._fernet = Fernet(self._load_key())

    @staticmethod
    def _normalize_key(value: str) -> bytes:
        raw = value.encode("utf-8")
        try:
            Fernet(raw)
            return raw
        except ValueError:
            return base64.urlsafe_b64encode(hashlib.sha256(raw).digest())

    def _load_key(self) -> bytes:
        if Config.DELIVERY_SECRET_KEY:
            return self._normalize_key(Config.DELIVERY_SECRET_KEY)

        data_dir = Path(Config.DATA_DIR)
        data_dir.mkdir(parents=True, exist_ok=True)
        key_path = data_dir / "delivery_secret.key"
        if key_path.exists():
            return key_path.read_bytes().strip()

        key = Fernet.generate_key()
        key_path.write_bytes(key)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        return key

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")


_secret_store = None


def get_delivery_secret_store() -> DeliverySecretStore:
    global _secret_store
    if _secret_store is None:
        _secret_store = DeliverySecretStore()
    return _secret_store
