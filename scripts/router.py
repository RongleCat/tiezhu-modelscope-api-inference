"""Model routing and fallback behavior."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .catalog import ModelRecord, sort_models


QUOTA_MARKERS = (
    "quota",
    "insufficient",
    "rate limit",
    "too many requests",
    "429",
    "exceed",
    "超限",
    "额度",
    "限流",
)


class PreferenceStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, list[str]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def remember(self, capability: str, model_id: str) -> None:
        data = self.load()
        values = [m for m in data.get(capability, []) if m != model_id]
        data[capability] = [model_id, *values]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_quota_error(exc: BaseException | str) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in QUOTA_MARKERS)


def route_models(
    models: Iterable[ModelRecord],
    *,
    capability: str,
    preferences: dict[str, list[str]] | None = None,
    exclude: set[str] | None = None,
) -> list[ModelRecord]:
    exclude = exclude or set()
    prefs = (preferences or {}).get(capability, [])
    by_id = {m.model_id: m for m in models if m.model_id not in exclude}
    preferred = [by_id.pop(model_id) for model_id in prefs if model_id in by_id]
    return preferred + sort_models(list(by_id.values()))
