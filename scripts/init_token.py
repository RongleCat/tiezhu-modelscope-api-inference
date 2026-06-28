#!/usr/bin/env python3
"""Initialize a local ModelScope token in an ignored .env file."""

from __future__ import annotations

import getpass
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import api_key


ENV_PATH = Path(".env")


def main() -> int:
    if api_key():
        print("ModelScope token is already configured.")
        return 0

    print("ModelScope token is required for real API-Inference calls.")
    print("Create one in ModelScope, then paste it below. Input is hidden.")
    token = getpass.getpass("MODELSCOPE_API_KEY: ").strip()
    if not token:
        print("No token provided. You can rerun: python3 scripts/init_token.py")
        return 1

    lines = [
        "# Local token for tiezhu-modelscope. This file is ignored by git.",
        f"MODELSCOPE_API_KEY={token}",
        "MODELSCOPE_BASE_URL=https://api-inference.modelscope.cn/v1",
        "TIEZHU_MODELSCOPE_CACHE_DIR=cache",
        "",
    ]
    ENV_PATH.write_text("\n".join(lines), encoding="utf-8")
    os.chmod(ENV_PATH, stat.S_IRUSR | stat.S_IWUSR)
    print("Token saved to local .env with 0600 permissions.")
    print("Run: python3 scripts/check_env.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
