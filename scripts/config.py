"""Runtime configuration helpers."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_BASE_URL = "https://api-inference.modelscope.cn/v1"
DEFAULT_CATALOG_URL = "https://modelscope.cn/api/v1/dolphin/models"


def api_key() -> str | None:
    """Return a ModelScope token from environment variables or local .env."""

    return os.getenv("MODELSCOPE_API_KEY") or os.getenv("MODELSCOPE_TOKEN") or local_env().get("MODELSCOPE_API_KEY") or local_env().get("MODELSCOPE_TOKEN")


def base_url() -> str:
    return (os.getenv("MODELSCOPE_BASE_URL") or local_env().get("MODELSCOPE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def cache_dir() -> Path:
    return Path(os.getenv("TIEZHU_MODELSCOPE_CACHE_DIR") or local_env().get("TIEZHU_MODELSCOPE_CACHE_DIR") or "cache")


def preference_path() -> Path:
    return cache_dir() / "preferences.json"


def local_env(path: Path = Path(".env")) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values
