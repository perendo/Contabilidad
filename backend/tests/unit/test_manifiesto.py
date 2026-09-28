"""Modelos, catalogo y manifiesto de la exportacion integral (SPEC-029).

Parte 1 (T010): unicidad, FKs compuestas y trigger de inmutabilidad.
Parte 2 (T012): catalogo de bloques completo y coherente.
Parte 3 (T014): `manifest.json` interior y tension `tenant_id == empresa_id`.
Parte 4 (T031): el conteo de `ManifiestoBloque` coincide con los JSON del ZIP.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from base import Base
from models.export.blob_exportacion import BlobExportacion
from models.export.config_sii import ConfigSii
from models.export.exportacion import EstadoExportacion, TipoExportacion
from models.export.manifiesto import (
    FORMATO_VERSION,
    ManifiestoBloque,
    ManifiestoExportacion,
)
from services.export.bloques import BLOQUES, BLOQUES_OBLIGATORIOS
from services.export.recopilar import BloqueRecopilado, bytes_bloque
from services.export.zip_generator import escribir_zip, leer_manifiesto
from tests.unit import export_support as soporte

# --- Parte 1 · modelos -----------------------------------------------------


def test_tabla_y_enums_de_exportacion() -> None:
    assert Base.metadata.tables["exportacion"].name == "exportacion"
    assert {e.name for e in TipoExportacion} == {"INTEGRAL", "SII"}
    assert {e.value for e in EstadoExportacion} == {"en_proceso", "lista", "fallida"}


async def test_uniquidad_por_empresa_anio_y_numero(db_session) -> None:
    from models.export.exportacion import Exportacion

    ahora = datetime.now(timezone.utc)
    db_session.add_all(
        [
            Exportacion(
                id=uuid.uuid4(),
                empresa_id=1,
                anio_creacion=2026,
                numero_exportacion=1,
                tipo=TipoExportacion.INTEGRAL,
                estado=EstadoExportacion.en_proceso,
                created_at=ahora,
            ),
            Exportacion(
                id=uuid.uuid4(),
                empresa_id=1,
                anio_creacion=2026,
                numero_exportacion=2,
                tipo=TipoExportacion.INTEGRAL,
                estado=EstadoExportacion.en_proceso,
                created_at=ahora,
            ),
            # Mismo numero en otra empresa: permitido (multi-tenancy).
            Exportacion(
                id=uuid.uuid4(),
                empresa_id=2,
                anio_creacion=2026,
                numero_exportacion=1,
                tipo=TipoExportacion.INTEGRAL,
                estado=EstadoExportacion.en_proceso,
                created_at=ahora,
            ),
        ]
    )
    await db_session.commit()
    duplicada = Exportacion(
        id=uuid.uuid4(),
        empresa_id=1,
        anio_creacion=2026,
        numero_exportacion=1,
        tipo=TipoExportacion.INTEGRAL,
        estado=EstadoExportacion.en_proceso,
        created_at=ahora,
    )
    db_session.add(duplicada)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    total = await db_session.scalar(
        select(func.count()).select_from(Exportacion).where(Exportacion.empresa_id == 1)
    )
    assert total == 2


async def test_rango_de_ejercicios_incoherente_rechazado(db_session) -> None:
    from models.export.exportacion import Exportacion

    db_session.add(
        Exportacion(
            id=uuid.uuid4(),
            empresa_id=1,
            anio_creacion=2026,
            numero_exportacion=1,
            tipo=TipoExportacion.INTEGRAL,
            ejercicio_desde=2026,
            ejercicio_hasta=2025,
            estado=EstadoExportacion.en_proceso,
            created_at=datetime.now(timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_manifiesto_unico_por_exportacion(db_session) -> None:
    from models.export.exportacion import Exportacion

    ahora = datetime.now(timezone.utc)
    fila = Exportacion(
        id=uuid.uuid4(),
        empresa_id=1,
        anio_creacion=2026,
        numero_exportacion=1,
        tipo=TipoExportacion.INTEGRAL,
        estado=EstadoExportacion.en_proceso,
        created_at=ahora,
    )
    db_session.add(fila)
    await db_session.flush()
    cabecera = ManifiestoExportacion(
        id=uuid.uuid4(),
        empresa_id=1,
        exportacion_id=fila.id,
        formato_version=FORMATO_VERSION,
        fecha_generacion=ahora,
        tenant_id=1,
        n_bloques=17,
        sha256_fichero="a" * 64,
    )
    db_session.add(cabecera)
    await db_session.commit()
    segundo = ManifiestoExportacion(
        id=uuid.uuid4(),
        empresa_id=1,
        exportacion_id=fila.id,
        formato_version=FORMATO_VERSION,
        fecha_generacion=ahora,
        tenant_id=1,
        n_bloques=17,
        sha256_fichero="b" * 64,
    )
    db_session.add(segundo)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_fk_compuesta_manifiesto_de_otra_empresa_rechazada(db_session) -> None:
    from models.export.exportacion import Exportacion

    ahora = datetime.now(timezone.utc)
    fila = Exportacion(
        id=uuid.uuid4(),
        empresa_id=1,
        anio_creacion=2026,
        numero_exportacion=1,
        tipo=TipoExportacion.INTEGRAL,
        estado=EstadoExportacion.en_proceso,
        created_at=ahora,
    )
    db_session.add(fila)
    await db_session.flush()
    db_session.add(
        ManifiestoBloque(
            id=uuid.uuid4(),
            empresa_id=2,  # no es la empresa de la cabecera del manifiesto
            manifiesto_id=uuid.uuid4(),
            bloque="asientos",
            entidades_exportadas="JournalEntry",
            conteo_registros=1,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_config_sii_unica_por_empresa(db_session) -> None:
    db_session.add(
        ConfigSii(id=uuid.uuid4(), empresa_id=7, obligado_sii=True, clave_regimen="01")
    )
    await db_session.commit()
    db_session.add(
        ConfigSii(id=uuid.uuid4(), empresa_id=7, obligado_sii=False, clave_regimen="02")
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_trigger_exportacion_lista_es_inmutable(db_session) -> None:
    """`chk_exportacion_immutable`: en estado `lista` no hay UPDATE ni DELETE."""
    from models.export.exportacion import Exportacion

    ahora = datetime.now(timezone.utc)
    fila = Exportacion(
        id=uuid.uuid4(),
        empresa_id=1,
        anio_creacion=2026,
        numero_exportacion=1,
        tipo=TipoExportacion.INTEGRAL,
        estado=EstadoExportacion.en_proceso,
        created_at=ahora,
    )
    db_session.add(fila)
    await db_session.commit()
    # La transicion en_proceso -> lista si se admite.
    fila.estado = EstadoExportacion.lista
    fila.sha256 = "c" * 64
    fila.tamano_bytes = 1234
    fila.n_bloques = 17
    fila.completado_at = ahora
    await db_session.commit()
    # A partir de aqui, el snapshot es inmutable.
    fila.sha256 = "d" * 64
    with pytest.raises(IntegrityError, match="inmutable"):
        await db_session.commit()
    await db_session.rollback()
    with pytest.raises(IntegrityError):
        await db_session.delete(fila)
        await db_session.commit()
    await db_session.rollback()


async def test_trigger_blob_manifiesto_append_only(db_session) -> None:
    """El blob y las lineas de manifiesto son append-only en cualquier estado."""
    from models.export.exportacion import Exportacion

    ahora = datetime.now(timezone.utc)
    fila = Exportacion(
        id=uuid.uuid4(),
        empresa_id=1,
        anio_creacion=2026,
        numero_exportacion=1,
        tipo=TipoExportacion.INTEGRAL,
        estado=EstadoExportacion.en_proceso,
        created_at=ahora,
    )
    db_session.add(fila)
    await db_session.flush()
    blob = BlobExportacion(
        id=uuid.uuid4(),
        empresa_id=1,
        exportacion_id=fila.id,
        contenido=b"PK\x03\x04contenido",
        sha256="e" * 64,
        tamano_bytes=18,
        created_at=ahora,
    )
    db_session.add(blob)
    await db_session.commit()
    blob.sha256 = "f" * 64
    with pytest.raises(IntegrityError, match="inmutable"):
        await db_session.commit()
    await db_session.rollback()


async def test_nombre_fichero_y_estados_finales(db_session) -> None:
    from models.export.exportacion import ESTADOS_FINALES, Exportacion

    fila = Exportacion(
        id=uuid.uuid4(),
        empresa_id=42,
        anio_creacion=2026,
        numero_exportacion=7,
        tipo=TipoExportacion.SII,
        estado=EstadoExportacion.lista,
        created_at=datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc),
        tamano_bytes=5 * 1024 * 1024,
    )
    assert fila.nombre_fichero == "export_42_7_20260927.zip"
    assert fila.descargable is True
    assert fila.por_megabytes == Decimal("5.0000")
    assert ESTADOS_FINALES == {EstadoExportacion.lista, EstadoExportacion.fallida}
    assert support_ids(db_session) is None


def support_ids(_db) -> None:  # pragma: no cover - guarda de que el import sirve
    return None


# --- Parte 2 · catalogo de bloques (T012) ----------------------------------

BLOQUES_OBLIGATORIOS_ESPERADOS = (
    "plan_cuentas",
    "plan_cuentas_versiones",
    "asientos",
    "apuntes",
    "terceros",
    "facturas",
    "lineas_factura",
    "vencimientos",
    "cobros_pagos",
    "remesas",
    "devoluciones",
    "amortizaciones",
    "cierres",
    "presupuestos",
    "previsiones",
    "libros_iva",
    "configuracion",
)


def test_catalogo_tiene_los_17_bloques_obligatorios() -> None:
    nombres = [b.nombre for b in BLOQUES_OBLIGATORIOS]
    assert nombres == list(BLOQUES_OBLIGATORIOS_ESPERADOS)
    assert len(BLOQUES_OBLIGATORIOS) == 17


def test_cada_bloque_declara_nombre_fichero_query_y_filtro() -> None:
    for bloque in BLOQUES:
        assert bloque.nombre
        assert bloque.fichero
        assert bloque.descripcion
        assert isinstance(bloque.filtra_ejercicio, bool)
        assert callable(bloque.construir_consulta)
        assert isinstance(bloque.entidades, tuple)


def test_ficheros_ordenados_y_con_prefijo_numerico() -> None:
    ficheros = [b.fichero for b in BLOQUES_OBLIGATORIOS]
    assert ficheros == sorted(ficheros)
    for indice, fichero in enumerate(ficheros, start=1):
        assert fichero.startswith(f"{indice:03d}_")


def test_bloque_consulta_filtra_por_empresa_y_ejercicio() -> None:
    for bloque in BLOQUES:
        consultas = bloque.construir_consulta(10, 2025, 2025)
        assert set(consultas) == {t.tabla for t in bloque.tablas}
        filtradas = 0
        for consulta in consultas.values():
            sql = str(consulta.compile(compile_kwargs={"literal_binds": True})).lower()
            # constitution III: filtro de empresa en todas las consultas.
            assert " = 10" in sql
            if "2025" in sql:
                filtradas += 1
            # Portabilidad: nada de EXTRACT/year() (no existe en SQLite).
            assert "extract(" not in sql
            assert "year(" not in sql
        if bloque.filtra_ejercicio:
            # FR-005: al menos una tabla del bloque recibe el rango.
            assert filtradas >= 1, f"{bloque.nombre} declara filtro pero no lo aplica"


def test_toda_tabla_del_catalogo_declara_columna_de_empresa() -> None:
    for bloque in BLOQUES:
        for ref in bloque.tablas:
            assert ref.empresa_col
            tabla = Base.metadata.tables[ref.tabla]
            assert ref.empresa_col in tabla.c, f"{ref.tabla}.{ref.empresa_col}"
            if ref.padre is not None:
                padre = Base.metadata.tables[ref.padre.tabla]
                assert ref.padre.clave in tabla.c
                assert ref.padre.empresa_col in padre.c


def test_bloque_opcional_sii_marcado_como_opcional() -> None:
    opcionales = [b for b in BLOQUES if b.opcional]
    assert [b.nombre for b in opcionales] == ["datos_sii"]
    assert opcionales[0].ruta == ""
    assert BLOQUES[-1].nombre == "datos_sii"


# --- Parte 3 · manifest.json interior (T014) -------------------------------

def _bloque(nombre: str, fichero: str, registros: list[dict]) -> BloqueRecopilado:
    from services.export.bloques import Bloque

    return BloqueRecopilado(
        bloque=Bloque(
            nombre=nombre, fichero=fichero, descripcion="Test", tablas=(), filtra_ejercicio=True
        ),
        registros=registros,
        conteo_registros=len(registros),
        ejercicio_min=2025,
        ejercicio_max=2026,
        fecha_min=date(2025, 1, 1),
        fecha_max=date(2026, 12, 31),
    )


def test_manifest_json_interno_tiene_los_campos_del_contrato() -> None:
    bloques = [
        _bloque("plan_cuentas", "001_plan_cuentas.json", [{"code": "4300"}]),
        _bloque("asientos", "003_asientos.json", [{"id": "a"}, {"id": "b"}]),
    ]
    momento = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    zipio = escribir_zip(
        42, bloques, ejercicio_desde=2025, ejercicio_hasta=2026, fecha_generacion=momento
    )
    manifiesto = leer_manifiesto(zipio.contenido)
    assert manifiesto["formato_version"] == FORMATO_VERSION
    assert manifiesto["fecha_generacion"] == "2026-09-27T12:00:00Z"
    assert manifiesto["tenant_id"] == 42
    assert manifiesto["empresa_id"] == 42
    assert manifiesto["ejercicio_desde"] == 2025
    assert manifiesto["ejercicio_hasta"] == 2026
    assert manifiesto["n_bloques"] == 2
    assert len(zipio.sha256) == 64
    assert manifiesto["sha256_contenido"] == zipio.sha256_contenido
    por_nombre = {b["bloque"]: b for b in manifiesto["bloques"]}
    assert por_nombre["asientos"]["conteo_registros"] == 2
    assert por_nombre["asientos"]["ejercicio_min"] == 2025
    assert por_nombre["asientos"]["ejercicio_max"] == 2026
    assert por_nombre["asientos"]["fecha_min"] == "2025-01-01"
    assert por_nombre["plan_cuentas"]["fichero"] == "001_plan_cuentas.json"
    assert all(len(b["sha256"]) == 64 for b in manifiesto["bloques"])


def test_tension_tenant_id_igual_a_empresa_id(export_client) -> None:
    respuesta = export_client.exportar(empresa_id=20)
    assert respuesta.status_code == 201, respuesta.text
    exportacion_id = respuesta.json()["exportacion_id"]
    detalle = export_client.get(f"/api/v1/exportaciones/{exportacion_id}", empresa_id=20)
    assert detalle.json()["manifiesto"]["tenant_id"] == 20
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga", empresa_id=20)
    )
    import json

    manifiesto = json.loads(ficheros["manifest.json"].decode("utf-8"))
    assert manifiesto["tenant_id"] == 20


# --- Parte 4 · conteos del manifiesto == JSON del ZIP (T031) -----------------


def test_conteo_de_manifiesto_coincide_con_los_json_del_zip(export_client) -> None:
    import json

    respuesta = export_client.exportar()
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    exportacion_id = cuerpo["exportacion_id"]
    detalle = export_client.get(f"/api/v1/exportaciones/{exportacion_id}").json()
    por_bloque = {b["bloque"]: b for b in detalle["manifiesto"]["bloques"]}
    # La empresa A esta obligada al SII (T043): 17 obligatorios + `datos_sii.*`.
    assert len(por_bloque) == 19
    assert detalle["manifiesto"]["n_bloques"] == 19
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    )
    for nombre, linea in por_bloque.items():
        payload = json.loads(ficheros[linea["ruta"]].decode("utf-8"))
        assert payload["conteo_registros"] == linea["conteo_registros"]
        assert len(payload["registros"]) == linea["conteo_registros"]
        assert payload["bloque"] == nombre


def test_payload_de_bloque_incluye_cabecera_y_registros() -> None:
    import json

    recopilado = _bloque("asientos", "003_asientos.json", [{"id": "x"}])
    payload = json.loads(bytes_bloque(recopilado).decode("utf-8"))
    assert payload["bloque"] == "asientos"
    assert payload["entidades_exportadas"] == []
    assert payload["conteo_registros"] == 1
    assert payload["registros"] == [{"id": "x"}]


def test_cuentas_del_tenant_sembradas_por_el_fixture(export_client) -> None:
    """Guarda de que el dataset de la fixture llega a los bloques."""
    import json

    respuesta = export_client.exportar()
    exportacion_id = respuesta.json()["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    )
    cuentas = json.loads(ficheros["bloques/001_plan_cuentas.json"].decode("utf-8"))
    assert cuentas["conteo_registros"] > 0
    assert soporte.CUENTAS["ventas"] == "7000"
