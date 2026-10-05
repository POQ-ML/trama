"""Config — helper de env vars (stdlib)."""
from __future__ import annotations

import os


def get_env(key: str, default: str = "") -> str:
    """Retorna `os.environ[key]` ou `default` se ausente/vazio não exigido."""
    return os.environ.get(key, default)
