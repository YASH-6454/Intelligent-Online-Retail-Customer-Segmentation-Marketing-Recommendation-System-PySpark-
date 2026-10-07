#!/usr/bin/env bash
# One-time environment setup (macOS): Java 21 + Python 3.12 venv with all dependencies.
set -euo pipefail
cd "$(dirname "$0")/.."

brew list openjdk@21 >/dev/null 2>&1 || brew install openjdk@21
export JAVA_HOME="/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"

uv venv --python 3.12 .venv
UV_HTTP_TIMEOUT=300 uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m ipykernel install --user --name bda-retail --display-name "Python (BDA Retail)"

.venv/bin/python -c "from src.spark_session import get_spark; s=get_spark(); print('Spark', s.version, 'OK, count =', s.range(10).count())"
