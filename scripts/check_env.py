#!/usr/bin/env python3
"""Check local runtime prerequisites for tiezhu-modelscope."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import api_key


def main() -> int:
    checks = {
        "python": sys.version.split()[0],
        "package_import": False,
        "modelscope_token_present": bool(api_key()),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
    }
    try:
        import scripts.cli  # noqa: F401

        checks["package_import"] = True
    except Exception as exc:
        checks["package_import_error"] = str(exc)
    ok = checks["package_import"] and checks["ffmpeg"] and checks["ffprobe"]
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
