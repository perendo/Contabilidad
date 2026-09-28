#!/usr/bin/env bash
set -e

# Detectar python del venv
if [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="python"
fi

echo "Iniciando ContabilidadV1 con $PYTHON_CMD..."
exec "$PYTHON_CMD" scripts/dev_start.py "$@"
