"""Apply ``backend/migrations/*.sql`` in dependency order (PostgreSQL).

Usage (from ``backend/``, with ``src`` on the path):

    $env:PYTHONPATH="src"; ..\\.venv\\Scripts\\python.exe -m db.migrate

The numeric filename order does not match the FK dependencies: the SPEC-001
migrations (``001_account_plan``, ``002_seed_pgc``) reference ``companies``,
defined by SPEC-003 in ``004_iam.sql``. ``ORDEN_PREFERENTE`` fixes that order;
any file not listed is appended in filename order.

Statements are executed inside a single transaction; any failure rolls the whole
batch back. The SQL files are idempotent, so re-running is safe.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from database import engine

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

ORDEN_PREFERENTE: tuple[str, ...] = (
    "000_audit_log.sql",
    "004_iam.sql",
    "001_account_plan.sql",
    "002_seed_pgc.sql",
    "003_journal.sql",
    "005_fiscal_invoice.sql",
    "006_apertura.sql",
    "007_rbac.sql",
    "008_forex.sql",
    "009_costcenters.sql",
    "010_templates.sql",
    "011_ngo.sql",
    "012_efectos.sql",
    "013_anticipos.sql",
    "014_impuesto_sociedades.sql",
    "015_retenciones_irpf.sql",
    "016_catalogo.sql",
    "017_presupuestos.sql",
    "018_cashflow.sql",
    "019_cierres.sql",
    "020_export.sql",
    "021_adjuntos_asiento.sql",
    # 022 depende de `user_companies`, que crea 004_iam.sql (ya aplicado antes), asi
    # que va al final sin hueco que reservar.
    "022_favoritos.sql",
)


def archivos_ordenados() -> list[Path]:
    """Return migration files in dependency order, extras by filename."""
    existentes = {p.name: p for p in MIGRATIONS_DIR.glob("*.sql")}
    ordenados = [existentes[nombre] for nombre in ORDEN_PREFERENTE if nombre in existentes]
    ya_incluidos = {p.name for p in ordenados}
    ordenados.extend(
        sorted(
            (p for nombre, p in existentes.items() if nombre not in ya_incluidos),
            key=lambda p: p.name,
        )
    )
    return ordenados


async def aplicar_migraciones() -> list[str]:
    aplicadas: list[str] = []
    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        driver = raw.driver_connection
        if driver is None:
            raise RuntimeError("conexión asyncpg no disponible para migraciones")

        # Tabla de control de versiones de esquema
        await driver.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )

        filas = await driver.fetch("SELECT version FROM schema_migrations;")
        ya_registradas = {fila["version"] for fila in filas}

        for archivo in archivos_ordenados():
            if archivo.name in ya_registradas:
                continue

            await driver.execute(archivo.read_text(encoding="utf-8"))
            await driver.execute(
                "INSERT INTO schema_migrations (version) VALUES ($1) ON CONFLICT DO NOTHING;",
                archivo.name,
            )
            aplicadas.append(archivo.name)
    return aplicadas


def main() -> None:
    for nombre in asyncio.run(aplicar_migraciones()):
        print(f"aplicada: {nombre}")


if __name__ == "__main__":
    main()
