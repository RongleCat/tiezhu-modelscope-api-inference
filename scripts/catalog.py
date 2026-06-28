"""ModelScope public model catalog client.

The model list page currently uses a public PUT endpoint at
``/api/v1/dolphin/models``. Earlier snapshots used the same path but callers
often guessed GET/POST; this client keeps the request shape explicit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import DEFAULT_CATALOG_URL


TASK_PRESETS: dict[str, list[str]] = {
    "text": ["text-generation"],
    "text-generation": ["text-generation"],
    "audio": [
        "auto-speech-recognition",
        "speech-language-recognition",
        "audio-visual-speech-recognition",
        "audio-classification",
    ],
    "video": [
        "video-captioning",
        "video-question-answering",
        "video-summarization",
        "language-guided-video-summarization",
        "image-text-to-text",
    ],
    "multimodal": ["image-text-to-text"],
    "image": ["text-to-image-synthesis"],
    "text-to-image": ["text-to-image-synthesis"],
}


@dataclass(slots=True)
class ModelRecord:
    model_id: str
    task: str
    downloads: int = 0
    stars: int = 0
    model_size: float | None = None
    support_inference: str = ""
    support_api_inference: bool = False
    model_type: str = ""
    license: str = ""
    updated_at: int | None = None
    url: str = ""
    raw: dict[str, Any] | None = None

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_raw:
            data.pop("raw", None)
        return data


class CatalogError(RuntimeError):
    pass


def task_values(task_or_preset: str) -> list[str]:
    return TASK_PRESETS.get(task_or_preset, [task_or_preset])


def model_size_value(model: dict[str, Any]) -> float | None:
    info = model.get("ModelInfos") or {}
    safetensor = info.get("safetensor") or {}
    value = safetensor.get("model_size") or safetensor.get("modelSize")
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace(",", "")
    multiplier = 1.0
    if text.endswith("b"):
        multiplier = 1.0
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1 / 1000
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def normalize_model(model: dict[str, Any], task: str) -> ModelRecord:
    path = model.get("Path") or model.get("path") or ""
    name = model.get("Name") or model.get("name") or ""
    model_id = model.get("model_id") or model.get("ModelId") or "/".join(x for x in [path, name] if x)
    tasks = model.get("Tasks") or []
    task_name = task
    if isinstance(tasks, list) and tasks:
        first = tasks[0]
        task_name = first.get("Name") if isinstance(first, dict) else str(first)
    return ModelRecord(
        model_id=model_id,
        task=task_name,
        downloads=int(model.get("Downloads") or model.get("downloads") or 0),
        stars=int(model.get("Stars") or model.get("stars") or 0),
        model_size=model_size_value(model),
        support_inference=str(model.get("SupportInference") or model.get("support_inference") or ""),
        support_api_inference=bool(model.get("SupportApiInference") or model.get("SupportDashInference")),
        model_type=str(model.get("ModelType") or model.get("model_type") or ""),
        license=str(model.get("License") or model.get("license") or ""),
        updated_at=model.get("LastUpdatedTime"),
        url=f"https://modelscope.cn/models/{model_id}" if model_id else "",
        raw=model,
    )


class ModelScopeCatalog:
    def __init__(self, endpoint: str = DEFAULT_CATALOG_URL, timeout: int = 30):
        self.endpoint = endpoint
        self.timeout = timeout

    def build_request(
        self,
        task: str,
        *,
        page: int = 1,
        page_size: int = 30,
        sort_by: str = "DownloadsCount",
        api_inference_only: bool = True,
        target: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "PageSize": page_size,
            "PageNumber": page,
            "SortBy": sort_by,
            "Target": target,
            "Criterion": [
                {
                    "category": "tasks",
                    "predicate": "contains",
                    "values": [task],
                    "sub_values": [],
                }
            ],
        }
        if api_inference_only:
            payload["SingleCriterion"] = [
                {
                    "category": "inference_type",
                    "DateType": "int",
                    "predicate": "equal",
                    "IntValue": 1,
                }
            ]
        return payload

    def fetch_task(
        self,
        task: str,
        *,
        page_size: int = 30,
        pages: int = 1,
        sort_by: str = "DownloadsCount",
        api_inference_only: bool = True,
    ) -> dict[str, Any]:
        all_models: list[ModelRecord] = []
        total = 0
        request_ids: list[str] = []
        for page in range(1, pages + 1):
            payload = self.build_request(
                task,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                api_inference_only=api_inference_only,
            )
            data = self._put(payload)
            request_ids.append(str(data.get("RequestId", "")))
            model_data = ((data.get("Data") or {}).get("Model") or {})
            total = int(model_data.get("TotalCount") or total or 0)
            all_models.extend(normalize_model(m, task) for m in (model_data.get("Models") or []))
        return {
            "task": task,
            "total": total,
            "request_ids": [x for x in request_ids if x],
            "models": all_models,
        }

    def fetch_preset(self, preset: str, *, page_size: int = 30, pages: int = 1) -> dict[str, Any]:
        results = []
        for task in task_values(preset):
            try:
                results.append(self.fetch_task(task, page_size=page_size, pages=pages))
            except CatalogError as exc:
                results.append({"task": task, "total": 0, "error": str(exc), "models": []})
        models = [m for r in results for m in r.get("models", [])]
        return {
            "preset": preset,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "tasks": results,
            "models": sort_models(models),
        }

    def _put(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="PUT",
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise CatalogError(f"catalog request failed: {exc}") from exc
        if str(parsed.get("Code")) not in {"200", "0"} and parsed.get("Success") is not True:
            raise CatalogError(f"catalog returned non-success: {parsed.get('Code')} {parsed.get('Message')}")
        return parsed


def sort_models(models: list[ModelRecord]) -> list[ModelRecord]:
    return sorted(models, key=lambda m: (m.model_size is not None, m.model_size or -1, m.downloads), reverse=True)


def write_cache(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = _jsonable(data)
    path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def read_cache(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["models"] = [ModelRecord(**m) for m in raw.get("models", [])]
    return raw


def _jsonable(value: Any) -> Any:
    if isinstance(value, ModelRecord):
        return value.to_dict()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value
