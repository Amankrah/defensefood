"""
UN Comtrade subscription key pool with automatic rotation on quota (HTTP 403).

Configure keys in ``backend/script/.env`` or ``backend/.env`` (or environment):

  COMTRADE_SUBSCRIPTION_KEYS=key_one,key_two,key_three

Legacy single key (still supported, used first if both are set):

  COMTRADE_SUBSCRIPTION_KEY=your_key_here
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load script-local .env first, then backend root (pipeline runs from backend/script/).
_SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "script"
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(_SCRIPT_DIR / ".env")
load_dotenv(_BACKEND_DIR / ".env")


class QuotaExhausted(Exception):
    """All configured Comtrade keys hit the call-volume quota (HTTP 403)."""


def _parse_key_list() -> list[str]:
    """Build ordered, de-duplicated key list from environment."""
    keys: list[str] = []
    single = os.getenv("COMTRADE_SUBSCRIPTION_KEY", "").strip()
    multi = os.getenv("COMTRADE_SUBSCRIPTION_KEYS", "").strip()

    if single:
        keys.append(single)
    if multi:
        for part in multi.replace("\n", ",").split(","):
            k = part.strip()
            if k and k not in keys:
                keys.append(k)

    return keys


def is_quota_http_error(status_code: int | None, body: str = "") -> bool:
    """True for Comtrade daily/volume cap (403), not generic forbidden."""
    if status_code != 403:
        return False
    text = (body or "").lower()
    return (
        "quota" in text
        or "call volume" in text
        or "out of call" in text
        or status_code == 403  # Comtrade uses 403 for volume cap
    )


def mask_key(key: str) -> str:
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


class ComtradeKeyPool:
    """Round-robin Comtrade API keys; rotate on quota exhaustion."""

    def __init__(self, keys: list[str] | None = None) -> None:
        self._keys = list(keys) if keys is not None else _parse_key_list()
        self._index = 0

    @property
    def keys(self) -> list[str]:
        return list(self._keys)

    @property
    def count(self) -> int:
        return len(self._keys)

    @property
    def index(self) -> int:
        return self._index

    def current_key(self) -> str:
        if not self._keys:
            raise RuntimeError(
                "No Comtrade API keys configured. Set COMTRADE_SUBSCRIPTION_KEYS "
                "(comma-separated) or COMTRADE_SUBSCRIPTION_KEY in backend/script/.env"
            )
        return self._keys[self._index]

    def headers(self) -> dict[str, str]:
        return {
            "Cache-Control": "no-cache",
            "Ocp-Apim-Subscription-Key": self.current_key(),
        }

    def rotate(self) -> bool:
        """Switch to the next key. Returns False when no keys remain."""
        if self._index + 1 >= len(self._keys):
            return False
        self._index += 1
        print(
            f"[Comtrade] Quota hit on key {self._index}/{len(self._keys)} "
            f"({mask_key(self._keys[self._index - 1])}); "
            f"switching to key {self._index + 1}/{len(self._keys)} "
            f"({mask_key(self.current_key())})"
        )
        return True

    def all_exhausted(self) -> bool:
        return not self._keys or self._index >= len(self._keys) - 1


_pool: ComtradeKeyPool | None = None


def get_key_pool() -> ComtradeKeyPool:
    global _pool
    if _pool is None:
        _pool = ComtradeKeyPool()
        if _pool.count:
            print(f"[Comtrade] Loaded {_pool.count} API key(s); active: {mask_key(_pool.current_key())}")
        else:
            print("[Comtrade] Warning: no API keys in environment (COMTRADE_SUBSCRIPTION_KEYS)")
    return _pool


def reset_key_pool() -> None:
    """Reset singleton (for tests)."""
    global _pool
    _pool = None
