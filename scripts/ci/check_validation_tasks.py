"""Guard validation task markers behind the CI quality gates."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

TASKS = Path("specs/020-remesas-sepa-cobros/tasks.md")
VALIDATION_TASKS = ("T054", "T055", "T056", "T062")
TASK_PATTERN = re.compile(r"^\s*- \[(?P<status>[ X])\] (?P<task>T\d+)")


def read_statuses() -> dict[str, str]:
    statuses: dict[str, str] = {}
    for line in TASKS.read_text(encoding="utf-8").splitlines():
        match = TASK_PATTERN.match(line)
        if match and match.group("task") in VALIDATION_TASKS:
            task = match.group("task")
            if task in statuses:
                raise ValueError(f"{task} aparece más de una vez en {TASKS}")
            statuses[task] = match.group("status")
    missing = [task for task in VALIDATION_TASKS if task not in statuses]
    if missing:
        raise ValueError(f"Faltan tareas de validación: {', '.join(missing)}")
    return statuses


def check_marked_evidence(marked: set[str]) -> list[str]:
    errors: list[str] = []
    if "T054" in marked:
        service_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in Path("backend/src/services").rglob("*.py")
        )
        if "async_session.begin" not in service_sources and "session.begin" not in service_sources:
            errors.append("T054 está marcada, pero no hay evidencia de session.begin() en los servicios")
    if "T055" in marked and not Path("backend/tests/integration/test_ejercicios_cerrados.py").exists():
        errors.append("T055 está marcada, pero falta test_ejercicios_cerrados.py")
    if "T062" in marked:
        contract_tests = list(Path("backend/tests/contract").glob("test_*.py"))
        if not contract_tests:
            errors.append("T062 está marcada, pero no existen tests contractuales")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-gates", action="store_true")
    args = parser.parse_args()

    if not TASKS.exists():
        print(f"No existe {TASKS}", file=sys.stderr)
        return 1

    try:
        statuses = read_statuses()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    marked = {task for task, status in statuses.items() if status == "X"}
    pending = [task for task in VALIDATION_TASKS if task not in marked]
    print(f"Tareas de validación marcadas: {', '.join(sorted(marked)) or 'ninguna'}")
    print(f"Tareas de validación pendientes: {', '.join(pending) or 'ninguna'}")

    if args.require_gates and os.getenv("CI_VALIDATION_GATES") != "passed":
        print("Las puertas CI no están confirmadas", file=sys.stderr)
        return 1

    errors = check_marked_evidence(marked)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
