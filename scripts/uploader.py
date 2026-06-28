"""Temporary media URL helpers."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class UploadError(RuntimeError):
    pass


class UguuUploader:
    def __init__(self, endpoint: str = "https://uguu.se/upload", timeout: int = 120):
        self.endpoint = endpoint
        self.timeout = timeout

    def upload(self, path: Path) -> str:
        boundary = f"----tiezhu-modelscope-{uuid.uuid4().hex}"
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        head = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files[]"; filename="{path.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
        tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = head + path.read_bytes() + tail
        req = Request(
            self.endpoint,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "tiezhu-modelscope-api-inference/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise UploadError(f"Uguu HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise UploadError(f"Uguu upload failed: {exc}") from exc
        return parse_uguu_url(data)


def parse_uguu_url(data: dict) -> str:
    files = data.get("files") or []
    if isinstance(files, list) and files:
        first = files[0] or {}
        url = first.get("url")
        if isinstance(url, str) and url.startswith("https://"):
            return url
    if data.get("success") is False:
        raise UploadError(f"Uguu upload rejected: {data}")
    raise UploadError(f"Uguu response did not include an HTTPS file URL: {data}")
