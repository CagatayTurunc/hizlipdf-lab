#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -n "${HIZLIPDF_PYTHON:-}" ]; then
  task_python="$HIZLIPDF_PYTHON"
elif [ -x "$project_dir/.venv/bin/python" ]; then
  task_python="$project_dir/.venv/bin/python"
elif [ -x "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" ]; then
  task_python="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
else
  task_python=python3
fi
exec "$task_python" "$project_dir/server.py" "$@"
