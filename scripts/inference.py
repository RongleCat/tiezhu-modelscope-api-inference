"""OpenAI-compatible ModelScope API-Inference client and payload builders."""

from __future__ import annotations

import base64
from http.client import RemoteDisconnected
import json
import mimetypes
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import api_key, base_url


class InferenceError(RuntimeError):
    pass


def data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def text_messages(prompt: str) -> list[dict[str, Any]]:
    return [{"role": "user", "content": prompt}]


def media_url(value: Path | str) -> str:
    if isinstance(value, Path):
        return data_url(value)
    if value.startswith(("http://", "https://", "data:")):
        return value
    return data_url(Path(value))


def image_messages(prompt: str, image: Path | str) -> list[dict[str, Any]]:
    return [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": media_url(image)}}]}]


def video_messages(prompt: str, video: Path | str, *, fps: float | None = 1.0) -> list[dict[str, Any]]:
    video_url: dict[str, Any] = {"url": media_url(video)}
    if fps is not None:
        video_url["fps"] = fps
    return [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "video_url", "video_url": video_url}]}]


def audio_messages(prompt: str, audio: Path | str) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "audio_url", "audio_url": {"url": media_url(audio)}},
            ],
        }
    ]


class ModelScopeInferenceClient:
    def __init__(self, token: str | None = None, base: str | None = None, timeout: int = 120):
        self.token = token if token is not None else api_key()
        self.base = (base or base_url()).rstrip("/")
        self.timeout = timeout

    def chat(self, model: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        stream = bool(kwargs.pop("stream", False))
        auto_stream_fallback = bool(kwargs.pop("auto_stream_fallback", True))
        if stream:
            return self.chat_stream(model, messages, **kwargs)
        payload = {"model": model, "messages": messages, **kwargs}
        response = self._request("/chat/completions", payload)
        if auto_stream_fallback and not _has_chat_content(response):
            return self.chat_stream(model, messages, **kwargs)
        return response

    def chat_stream(self, model: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        payload = {"model": model, "messages": messages, "stream": True, **kwargs}
        return self._stream_request("/chat/completions", payload)

    def image(self, model: str, prompt: str, *, size: str = "1024x1024", wait: bool = True, **kwargs: Any) -> dict[str, Any]:
        payload = {"model": model, "prompt": prompt, "size": size, **kwargs}
        response = self._request(
            "/images/generations",
            payload,
            extra_headers={
                "X-ModelScope-Async-Mode": "true",
                "X-ModelScope-Task-Type": "image_generation",
            },
        )
        task_id = response.get("task_id") or response.get("id")
        if wait and task_id and not response.get("data"):
            return {"task_id": task_id, "result": self.poll_task(str(task_id), task_type="image_generation")}
        return response

    def poll_task(self, task_id: str, *, task_type: str, interval: float = 2.0, timeout: int = 180) -> dict[str, Any]:
        deadline = time.time() + timeout
        last: dict[str, Any] = {}
        last_error = ""
        while time.time() < deadline:
            req = Request(
                f"{self.base}/tasks/{task_id}",
                headers=self._headers({"X-ModelScope-Task-Type": task_type}),
                method="GET",
            )
            try:
                with urlopen(req, timeout=self.timeout) as resp:
                    last = json.loads(resp.read().decode("utf-8"))
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                raise InferenceError(f"HTTP {exc.code}: {detail}") from exc
            except (URLError, TimeoutError, RemoteDisconnected) as exc:
                last_error = str(exc)
                time.sleep(interval)
                continue
            status = str(last.get("task_status") or last.get("status") or "").lower()
            if status in {"succeeded", "success", "completed", "done", "succeed"} or last.get("output") or last.get("outputs") or last.get("output_images") or last.get("data"):
                return last
            if status in {"failed", "error", "canceled", "cancelled"}:
                raise InferenceError(f"task {task_id} failed: {last}")
            time.sleep(interval)
        detail = f"; last_error={last_error}" if last_error else ""
        raise InferenceError(f"task {task_id} timed out; last={last}{detail}")

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        if not self.token:
            raise InferenceError("MODELSCOPE_API_KEY is not set")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        if extra:
            headers.update(extra)
        return headers

    def _request(self, path: str, payload: dict[str, Any], *, extra_headers: dict[str, str] | None = None) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(
            self.base + path,
            data=body,
            headers=self._headers(extra_headers),
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise InferenceError(f"HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, RemoteDisconnected, json.JSONDecodeError) as exc:
            raise InferenceError(str(exc)) from exc

    def _stream_request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(
            self.base + path,
            data=body,
            headers=self._headers({"Accept": "text/event-stream"}),
            method="POST",
        )
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        finish_reason: str | None = None
        usage: dict[str, Any] | None = None
        chunk_count = 0
        last_event: dict[str, Any] = {}
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        line = line.split(":", 1)[1].strip()
                    if line == "[DONE]":
                        break
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    chunk_count += 1
                    last_event = event
                    if isinstance(event.get("usage"), dict):
                        usage = event["usage"]
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0] or {}
                    if choice.get("finish_reason") is not None:
                        finish_reason = choice.get("finish_reason")
                    delta = choice.get("delta") or choice.get("message") or {}
                    _append_text(content_parts, delta.get("content"))
                    _append_text(reasoning_parts, delta.get("reasoning_content"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise InferenceError(f"HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, RemoteDisconnected) as exc:
            raise InferenceError(str(exc)) from exc
        return {
            "id": last_event.get("id"),
            "object": "chat.completion",
            "created": last_event.get("created"),
            "model": last_event.get("model") or payload.get("model"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "".join(content_parts),
                        "reasoning_content": "".join(reasoning_parts),
                    },
                    "finish_reason": finish_reason,
                }
            ],
            "usage": usage,
            "stream": {"chunks": chunk_count},
        }


def _append_text(parts: list[str], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        parts.append(value)
        return
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])


def _has_chat_content(response: dict[str, Any]) -> bool:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return False
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message") or {}
        delta = choice.get("delta") or {}
        if isinstance(message, dict) and (message.get("content") or message.get("reasoning_content")):
            return True
        if isinstance(delta, dict) and (delta.get("content") or delta.get("reasoning_content")):
            return True
    return False
