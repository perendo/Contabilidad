"""Migration inventory (SPEC-001/002/003/004).

El DDL PostgreSQL no se puede ejecutar sin una instancia PG; estos tests
protegen el inventario y el orden de dependencias que aplica `db.migrate`.

Y la parte de abajo vigila algo que el inventario **no** vigila por si solo: que
toda tabla del ORM tenga una migracion que la cree. Ver
`test_toda_tabla_del_orm_tiene_migracion`.
"""

from __future__ import annotations

import re
from pathlib import Path

from esquema_deuda import FK_CIEGAS_AL_TENANT, REFERENCIAS_SIN_FK
from esquema_deuda import TABLAS_SIN_MIGRACION as _TABLAS_SIN_MIGRACION

from db.migrate import MIGRATIONS_DIR, ORDEN_PREFERENTE, archivos_ordenados

MODELOS_DIR = Path(__file__).resolve().parents[2] / "src" / "models"

ESPERADAS = [
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
    "022_favoritos.sql",
    "023_seed_demo.sql",
    "024_conciliacion.sql",
    "025_prevision_plan_manual.sql",
    "026_manifiesto_n_bloques.sql",
    "027_maestros_comerciales.sql",
    "028_cobros_vencimientos.sql",
    "029_remesas_complemento.sql",
    "030_inmovilizado_completo.sql",
    "031_informes_iva.sql",
]


def test_migraciones_esperadas_existen():
    nombres = {p.name for p in MIGRATIONS_DIR.glob("*.sql")}
    assert set(ESPERADAS) <= nombres


def test_el_inventario_coincide_con_orden_preferente():
    """`ESPERADAS` y `ORDEN_PREFERENTE` son la misma lista escrita dos veces.

    Se duponen porque cada una responde a una pregunta distinta y ambas tienen que
    fallar: `ORDEN_PREFERENTE` la usa el runner de migraciones, y `ESPERADAS` la usan
    estos tests para afirmar el contenido de ficheros concretos. Duplicarlas sin
    sincronizarlas es exactamente lo que paso con `023_seed_demo.sql`: se anadio a
    `db.migrate` y se olvido aqui, con lo que la suite entera se caia en la recoleccion
    de `test_suggest_perf` por un fichero que no tiene nada que ver con las migraciones.

    Se comparan aqui, y no solo en `test_orden_por_dependencias`, porque este comprueba
    el resultado (ficheros aplicados en orden) y este comprueba que las dos declaraciones
    no se separen. Si alguien anade una migracion y olvida una de las dos, falla aqui y
    con un mensaje que senala la lista, no con un fallo de orden que hay que descifrar.
    """
    assert ESPERADAS == list(ORDEN_PREFERENTE), (
        "el inventario del test y el orden del runner de migraciones ya no son la misma "
        f"lista. Solo en ESPERADAS: {sorted(set(ESPERADAS) - set(ORDEN_PREFERENTE))}; "
        f"solo en ORDEN_PREFERENTE: {sorted(set(ORDEN_PREFERENTE) - set(ESPERADAS))}"
    )


def test_no_hay_migraciones_fuera_del_inventario():
    """Ningun `.sql` sin declarar.

    `db.migrate` anade al final lo que no figura en `ORDEN_PREFERENTE`, en orden de
    nombre, asi que una migracion olvidada se aplicaria en un sitio distinto del que su
    autora pretendia, y sin que nada lo indique. Aqui solo se reclama que este declarada;
    en que sitio va, lo decide el orden.
    """
    declaradas = set(ESPERADAS)
    huerfanas = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql") if p.name not in declaradas)
    assert huerfanas == [], f"migraciones en disco que no estan en el inventario: {huerfanas}"


def test_orden_por_dependencias():
    assert [p.name for p in archivos_ordenados()] == ESPERADAS


def test_migraciones_no_vacias():
    for nombre in ESPERADAS:
        contenido = (MIGRATIONS_DIR / nombre).read_text(encoding="utf-8")
        assert contenido.strip()


def test_migracion_diario_declara_trigger_balance_diferido():
    contenido = (MIGRATIONS_DIR / "003_journal.sql").read_text(encoding="utf-8")
    assert "chk_journal_entry_balance" in contenido
    assert "DEFERRABLE INITIALLY DEFERRED" in contenido


def test_migracion_retenciones_incluye_backfill_y_triggers() -> None:
    contenido = (MIGRATIONS_DIR / "015_retenciones_irpf.sql").read_text(
        encoding="utf-8"
    )
    assert "'4751'" in contenido
    assert "to_regclass('public.tercero')" in contenido
    assert "trg_liquidacion_retenciones_final_update" in contenido
    assert "trg_modelo_190_append_only_delete" in contenido
    assert "trg_companies_seed_retenciones_4751" in contenido
    assert "ADD COLUMN IF NOT EXISTS tipo_retencion" in contenido
    assert "ADD COLUMN IF NOT EXISTS direccion_inmueble" in contenido


def test_migracion_presupuestos_declara_unicidad_parcial_y_snapshot() -> None:
    contenido = (MIGRATIONS_DIR / "017_presupuestos.sql").read_text(encoding="utf-8")
    assert "uq_presupuesto_sin_centro" in contenido
    assert "uq_presupuesto_con_centro" in contenido
    assert "uq_periodo_seguimiento_abierto" in contenido
    assert "trg_desviacion_append_only_update" in contenido
    assert "trg_desviacion_append_only_delete" in contenido
    assert "REFERENCES account_plan (tenant_id, id)" in contenido
    assert "REFERENCES centro_coste (empresa_id, id)" in contenido


def test_migracion_cashflow_declara_correlatividad_y_snapshot_efe() -> None:
    contenido = (MIGRATIONS_DIR / "018_cashflow.sql").read_text(encoding="utf-8")
    assert "uq_prevision_tesoreria_numero" in contenido
    assert "uq_alerta_liquidez_prevision_fecha" in contenido
    assert "uq_informe_efe_ejercicio" in contenido
    assert "trg_informe_efe_append_only_update" in contenido
    assert "trg_linea_efe_append_only_delete" in contenido
    assert "REFERENCES account_plan (tenant_id, id)" in contenido
    assert "alerta_liquidez_saldo_negativo CHECK (saldo_proyectado < 0)" in contenido
    # `vencimiento` (SPEC-011) no tiene migracion propia: la FK se anade solo si
    # existe, igual que `tercero` en 015_retenciones_irpf.sql.
    assert "to_regclass('public.vencimiento')" in contenido
    assert "REFERENCES vencimiento (empresa_id, id)" in contenido


def test_migracion_cierres_declara_bloqueo_y_snapshots() -> None:
    """T009/T018/T044: bloqueo de periodos, snapshot inmutable y correlatividad."""
    contenido = (MIGRATIONS_DIR / "019_cierres.sql").read_text(encoding="utf-8")
    # Bloqueo de periodos a nivel de motor (FR-001, research D9).
    assert "chk_journal_entry_fecha_abierta" in contenido
    assert "p.estado IN ('cerrado', 'cerrado_ajustado')" in contenido
    # Snapshot del balance de comprobacion inmutable (constitucion II).
    assert "trg_balanza_periodo_append_only_update" in contenido
    assert "trg_balanza_periodo_linea_append_only_delete" in contenido
    # Partida doble en el propio CHECK (constitucion I).
    assert "CHECK (total_debe = total_haber)" in contenido
    # Clave natural del periodo y unicidad del balance por cierre.
    assert "uq_periodo_cerrado_natural" in contenido
    assert "uq_balanza_periodo_periodo" in contenido
    # Correlatividad de la solicitud de reapertura (constitucion IV).
    assert "secuencia_reapertura" in contenido
    assert "uq_solicitud_reapertura_numero" in contenido
    # FR-005: una sola solicitud activa por periodo (`periodo_id` es NULLABLE).
    assert "uq_solicitud_reapertura_activa" in contenido
    assert "chk_solicitud_reapertura_motivo" in contenido
    # Multi-tenancy: FKs compuestas y plan por `tenant_id` (SPEC-001).
    assert "REFERENCES account_plan (tenant_id, id)" in contenido
    assert "REFERENCES periodo_cerrado (empresa_id, id)" in contenido
    # T009: ampliacion del enum de tipos del motor de SPEC-002.
    assert "ADD VALUE IF NOT EXISTS 'REGULARIZACION'" in contenido
    assert "ADD VALUE IF NOT EXISTS 'CIERRE'" in contenido


def test_migracion_documentos_declara_inmutabilidad_y_huella() -> None:
    """T010: unicidad de huella, FK compuesta al diario e inmutabilidad real."""
    contenido = (MIGRATIONS_DIR / "021_adjuntos_asiento.sql").read_text(
        encoding="utf-8"
    )
    # FR-006 / research D6: unicidad incondicional, sin indice parcial.
    assert "uq_documento_asiento_huella UNIQUE" in contenido
    assert "(empresa_id, journal_entry_id, sha256)" in contenido
    # Constitucion III: la BD impide el anclaje cross-tenant.
    assert "fk_documento_asiento_entrada" in contenido
    assert "REFERENCES journal_entry (empresa_id, id)" in contenido
    # Constitucion II / research D3: contenido congelado y borrado fisico veto.
    assert "f_documento_asiento_inmutable_update" in contenido
    assert "trg_documento_asiento_contenido_inmutable_update" in contenido
    assert "trg_documento_asiento_inmutable_delete" in contenido
    # FR-012: la baja logica esta completa y trazada.
    assert "chk_documento_asiento_baja" in contenido
    # research D19: NUMERIC(18,4), jamas float.
    assert "importe_informativo   NUMERIC(18, 4)" in contenido
    # FR-020 / research D11: la adjuncion es opcional. La migracion no anade
    # ninguna columna ni restriccion al diario: no hay recuento de documentos
    # ni un NOT NULL que obligue a tenerlos.
    assert "ALTER TABLE journal_entry" not in contenido
    assert "ADD COLUMN" not in contenido


# ---------------------------------------------------------------------------
# Lo que el inventario NO vigila por si solo
# ---------------------------------------------------------------------------

#: La deuda vive en UN solo sitio, `tests/esquema_deuda.py`, y se importa aqui y
#: en `tests/integration/test_esquema_completo.py`.
#:
#: El motivo de que no sea una lista local: SPEC-013 se cerro con 54/54 tareas y
#: todas sus puertas en verde, y aun asi sus seis tablas vivian solo en el
#: `create_all` de los tests de SQLite. Contra PostgreSQL real no existian,
#: `POST /api/v1/extractos` devolvia 500 y **toda** la superficie de conciliacion
#: era inservible. El inventario de migraciones no lo ve porque comprueba que las
#: migraciones *declaradas* esten listadas, no que cada tabla del ORM tenga una. Un
#: modelo sin migracion es invisible para esa puerta.
#:
#: Y dos listas, una por test, se separan en cuanto una se actualiza y la otra no.
TABLAS_SIN_MIGRACION = _TABLAS_SIN_MIGRACION


def _tablas_del_orm() -> set[str]:
    nombres: set[str] = set()
    for p in MODELOS_DIR.rglob("*.py"):
        nombres.update(
            re.findall(r'__tablename__\s*=\s*"([a-z_0-9]+)"', p.read_text(encoding="utf-8"))
        )
    return nombres


def _tablas_creadas_por_migracion() -> set[str]:
    sql = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in MIGRATIONS_DIR.glob("*.sql")
    )
    return {
        nombre
        for nombre in _tablas_del_orm()
        if re.search(rf"CREATE TABLE IF NOT EXISTS\s+{nombre}\b", sql, re.IGNORECASE)
    }


def test_toda_tabla_del_orm_tiene_migracion() -> None:
    """Ninguna tabla nueva puede quedarse solo en el `create_all` de los tests.

    Es la puerta que faltaba para lo de SPEC-013. Un modelo se escribe, se prueba
    en SQLite y da verde; si nadie escribe la migracion, en PostgreSQL la
    funcionalidad **no existe**, y nada en la suite lo dice porque la puerta de
    migraciones no cruza modelo con esquema.
    """
    sin_migracion = _tablas_del_orm() - _tablas_creadas_por_migracion()
    nuevos = sin_migracion - TABLAS_SIN_MIGRACION
    assert not nuevos, (
        f"tablas del ORM sin migracion: {sorted(nuevos)}. Escribela en "
        "`backend/migrations/` y anadela a ORDEN_PREFERENTE y a ESPERADAS, o si "
        "no va a tenerla, declara aqui por que (la lista TABLAS_SIN_MIGRACION "
        "solo puede encogerse)"
    )


def test_la_lista_de_tablas_sin_migracion_no_miente() -> None:
    """Si una tabla de la lista ya tiene migracion, la lista esta mintiendo y deja
    de ser una lista: hay que borrarla para que el guard sea mas estricto."""
    ya_migradas = TABLAS_SIN_MIGRACION & _tablas_creadas_por_migracion()
    assert not ya_migradas, (
        f"ya tienen migracion, borralas de TABLAS_SIN_MIGRACION: {sorted(ya_migradas)}"
    )


def test_la_lista_de_tablas_sin_migracion_no_nombra_tablas_inventadas() -> None:
    """Lo mismo por el otro lado: si la lista nombra una tabla que ya no existe en
    los modelos, se ha borrado el modelo y la lista no se ha enterado."""
    inventadas = TABLAS_SIN_MIGRACION - _tablas_del_orm()
    assert not inventadas, (
        f"TABLAS_SIN_MIGRACION nombra tablas que ya no estan en los modelos: "
        f"{sorted(inventadas)}; borralas de la lista"
    )


# ---------------------------------------------------------------------------
# Las referencias que el modelo deja sueltas, y la decision de dejarlas sueltas
# ---------------------------------------------------------------------------


def _referencias_sueltas_del_orm() -> set[tuple[str, str]]:
    """Columnas que parecen una referencia y no declaran clave foranea.

    Se calculan importando el ORM, no leyendo el texto del modelo: un `re` sobre
    el codigo no distingue una FK de una columna que se parece a una FK, que es
    justo el caso que importa (una FK a una sola columna se lee igual que un
    UUID suelto).
    """
    import sqlalchemy as sa

    import models  # noqa: F401  (registra las tablas)
    from base import Base

    sueltas: set[tuple[str, str]] = set()
    for nombre, tabla in Base.metadata.tables.items():
        con_fk = {fk.parent.name for fk in tabla.foreign_keys}
        for columna in tabla.columns:
            if columna.name in con_fk or columna.name in ("id", "empresa_id"):
                continue
            if not isinstance(columna.type, (sa.Uuid, sa.Integer, sa.String)):
                continue
            if not columna.name.endswith("_id") and not columna.name.endswith("_id_"):
                continue
            sueltas.add((nombre, columna.name))
    return sueltas


def test_la_lista_de_referencias_sin_fk_no_miente() -> None:
    """Ninguna referencia suelta se queda fuera de la lista.

    La lista se decidio el 2026-09-29: migrar los modelos tal cual. Eso es una
    decision con fecha y con motivo, no un olvido, asi que tiene que seguir
    abanderada. Si aparece una referencia suelta nueva (una spec nueva, o un
    campo anadido a una tabla existente), este test falla.
    """
    sueltas = _referencias_sueltas_del_orm()
    sin_anotar = sueltas - REFERENCIAS_SIN_FK
    assert not sin_anotar, (
        f"referencias sin clave foranea que no estan en REFERENCIAS_SIN_FK: "
        f"{sorted(sin_anotar)}. Anadelas con su motivo, o declara la FK en el "
        "modelo y borralas de la lista"
    )


def test_ninguna_referencia_anotada_declara_ya_clave_foranea() -> None:
    """La otra mitad: si a `tercero_subcuenta.tercero_id` se le anade la FK, la
    lista tiene que decir que ya no es deuda."""
    sueltas = _referencias_sueltas_del_orm()
    ya_resueltas = REFERENCIAS_SIN_FK - sueltas
    assert not ya_resueltas, (
        f"ya tienen clave foranea, borralas de REFERENCIAS_SIN_FK: {sorted(ya_resueltas)}"
    )


def test_las_fk_compuestas_por_empresa_no_dejan_huecos() -> None:
    """Una FK a una tabla con `empresa_id` tiene que llevar `empresa_id` en su anchura.

    El criterio **no** es el ancho, porque hay FKs de una sola columna que son
    correctas: `empresa_id -> companies.id`, `user_id -> users.id` o
    `permiso_id -> permiso_operacion.id` apuntan a tablas que no tienen dimension
    de empresa, y ahi una columna basta. El agujero es cuando la FK de una sola
    columna apunta a una tabla que **si** lleva `empresa_id`: ahi no se impide que
    una fila referencie a otra empresa, porque la FK no mira la empresa.

    Se comprueba aqui, en el sitio donde se decide, y no en una migracion ya
    escrita: al escribirla habria que corregir el modelo.
    """
    import models  # noqa: F401
    from base import Base

    sueltas = {
        # La clave es `tabla.columna`, sin destino, para que sea comparable con
        # `FK_CIEGAS_AL_TENANT`. El destino va solo en el mensaje, que es donde
        # hace falta leerlo.
        f"{tabla.name}.{fk.parent.name}"
        for tabla in Base.metadata.tables.values()
        for fk in tabla.foreign_keys
        if len(fk.constraint.columns) == 1
        and "empresa_id" in Base.metadata.tables[fk.column.table.name].columns
    }
    nuevas = sueltas - FK_CIEGAS_AL_TENANT
    assert not nuevas, (
        "claves foraneas de una sola columna a una tabla que si tiene empresa_id, "
        f"y que por tanto no la miran: {sorted(nuevas)}. Declaralas en el modelo "
        "como compuestas, o anadelas a FK_CIEGAS_AL_TENANT explicando por que"
    )


def test_la_lista_de_fk_ciegas_al_tenant_no_miente() -> None:
    """La lista de excepciones no puede tornar a estar justificada.

    Si `evento_auditoria_acceso.rol_id` pasa a ser compuesta, hay que borrarla: una
    lista de excepciones que se queda de mas es una lista que ya no significa nada.
    """
    import models  # noqa: F401
    from base import Base

    reales = {
        f"{tabla.name}.{fk.parent.name}"
        for tabla in Base.metadata.tables.values()
        for fk in tabla.foreign_keys
        if len(fk.constraint.columns) == 1
        and "empresa_id" in Base.metadata.tables[fk.column.table.name].columns
    }
    justificadas = FK_CIEGAS_AL_TENANT - reales
    assert not justificadas, (
        f"ya no son ciegas al tenant, borralas de FK_CIEGAS_AL_TENANT: {sorted(justificadas)}"
    )


def test_la_migracion_de_conciliacion_crea_las_seis_tablas() -> None:
    """Las seis de SPEC-013, una a una: es la lista concreta que se corrigiÃ³."""
    contenido = (MIGRATIONS_DIR / "024_conciliacion.sql").read_text(encoding="utf-8")
    for tabla in (
        "extracto_bancario",
        "movimiento_bancario",
        "conciliacion",
        "cruce_conciliacion",
        "periodo_conciliado",
        "alerta_conciliacion",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {tabla} " in contenido, tabla


def test_la_migracion_de_conciliacion_admite_cruzar_un_movimiento() -> None:
    """El trigger de `movimiento_bancario` compara columna a columna en vez de
    reventar cualquier UPDATE, y por eso permite cambiar `estado`.

    Es el detalle que mas caro sale si se hace mal: confirmar un cruce pasa el
    movimiento a `conciliado` y deshacerlo lo devuelve a `pendiente`
    (`services/reconciliation/cruce.py`). Un trigger que reventase el UPDATE entero
    haria la conciliacion inservible, que es justo su funcion, y en SQLite no se
    veria porque alli la inmutabilidad no esta implementada.
    """
    contenido = (MIGRATIONS_DIR / "024_conciliacion.sql").read_text(encoding="utf-8")
    bloque = contenido[contenido.index("f_movimiento_bancario_inmutable") :]
    bloque = bloque[: bloque.index("$$ LANGUAGE plpgsql")]
    # El chequeo es de columnas concretas, no un reventon generico.
    for columna in ("importe", "signo", "fecha_operacion", "concepto", "orden", "extracto_id"):
        assert f"NEW.{columna} IS DISTINCT FROM OLD.{columna}" in bloque, columna
    # Y `estado` NO esta en la lista: es la que tiene que poder cambiar.
    assert "NEW.estado IS DISTINCT FROM OLD.estado" not in bloque
    assert "trg_movimiento_bancario_contenido_inmutable_update" in contenido
    assert "trg_movimiento_bancario_inmutable_delete" in contenido


def test_las_migraciones_son_idempotentes_tras_aplicadas() -> None:
    """`db.migrate` reaplica los ficheros ya aplicados y el fixture `pg_engine` de
    los tests de PostgreSQL tampoco borra el esquema antes de aplicarlos: los dos
    escriben sobre la base de verdad. Un `ADD CONSTRAINT` sin guardia hace que el
    segundo pase reviente con `DuplicateObjectError` y se cae la migracion entera
    (leccion de AGENTS.md 50: editar una migracion ya aplicada obliga a que siga
    siendo idempotente, o `db.migrate` falla sin decir en que estado quedo la base).
    """
    contenido = (MIGRATIONS_DIR / "024_conciliacion.sql").read_text(encoding="utf-8")
    adds = re.findall(r"ADD CONSTRAINT (\w+)", contenido)
    for nombre in adds:
        assert f"conname = '{nombre}'" in contenido, (
            f"ADD CONSTRAINT {nombre} sin guardia: el segundo pase de db.migrate "
            "falla con DuplicateObjectError"
        )

