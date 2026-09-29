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
    "023_seed_demo.sql",
    # SPEC-013 se cerro sin migracion; esta la anade al final, despues de
    # `account_plan` (001) que es de donde salen las FKs de `cuenta_id`.
    "024_conciliacion.sql",
    # Columna que el modelo de SPEC-027 declara y `018_cashflow.sql` no creo,
    # porque la 018 ya estaba aplicada. Es un ALTER TABLE sobre una tabla existente.
    "025_prevision_plan_manual.sql",
    # El default que le falta a `manifiesto_exportacion.n_bloques`. Va despues de 020
    # (que crea la columna) y **antes** que 027-031, que no dependen de ella: el numero
    # esta elegido por legibilidad del historial, no por dependencia.
    "026_manifiesto_n_bloques.sql",
    # Grupo 1 de las 27. Va despues de 003 (`journal_entry`, FK de `factura.asiento_id`)
    # y de 015 (`tipo_retencion_irpf`, que comparte con `factura_linea`).
    "027_maestros_comerciales.sql",
    # Grupo 2 de las 27. No depende de nada de las 27 (las referencias a `tercero` y
    # `factura` quedan sueltas, ver tests/esquema_deuda.py), asi que el numero es
    # solo por orden de lectura, no por dependencias.
    "028_cobros_vencimientos.sql",
    # Grupo 3 de las 27 (remesas SEPA). No depende de 027/028: las referencias a
    # `tercero`, `factura` y `vencimiento` quedan sueltas (tests/esquema_deuda.py), y la
    # unica FK que cruza a otra migracion es a `journal_entry` (003).
    "029_remesas_complemento.sql",
    # Grupo 4 de las 27 (inmovilizado). Va despues de 001 (`account_plan`, las tres
    # FKs de cuentas del activo) y de 003 (`journal_entry`, FKs de asiento).
    "030_inmovilizado_completo.sql",
    # Grupo 5 de las 27 (informes anuales y libros de IVA), y ultima de las 27.
    # No declara ninguna FK, asi que no depende de nadie; el numero es por historial.
    "031_informes_iva.sql",
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
