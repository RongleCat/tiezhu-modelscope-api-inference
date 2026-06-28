#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
. .venv/bin/activate
pip install -e .

echo "Installed tiezhu-modelscope."
python3 scripts/init_token.py || true
python3 -m scripts.cli refresh || true
python3 scripts/check_env.py || true
echo "Run: tiezhu-modelscope --help"
