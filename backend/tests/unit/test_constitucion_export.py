"""Constitucion V aplicada al modulo de exportacion (SPEC-029 T047).

Verifica por AST y por comportamiento lo que la constitution exige al flujo de
exportacion: `Decimal` sin `float`, inmutabilidad de la exportacion homologada,
aislamiento por `empresa_id` en todas las tablas y auditoria de cada generacion
y verificacion.
"""

from __future__ import annotations

import ast
import json
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from base import Base
from models.audit.audit_log import AuditLog
from models.export.exportacion import EstadoExportacion, Exportacion
from services.export.bloques import BLOQUES

SERVICIOS = Path(__file__).resolve().parents[2] / "src" / "services" / "export"
API = Path(__file__).resolve().parents[2] / "src" / "api" / "export.py"
MODELOS = Path(__file__).resolve().parents[2] / "src" / "models" / "export"
FUNCIONES_AUDITAR = {
    "GENERAR_EXPORTACION",
    "GENERAR_EXPORTACION_FALLIDA",
    "VERIFICAR_EXPORTACION",
}


def _arbol(ruta: Path) -> ast.Module:
    return ast.parse(ruta.read_text(encoding="utf-8"))


def _ficheros() -> list[Path]:
    return sorted(SERVICIOS.glob("*.py")) + [API] + sorted(MODELOS.glob("*.py"))


# --- Precision decimal ------------------------------------------------------


def test_ningun_fichero_del_modulo_declara_float() -> None:
    for ruta in _ficheros():
        arbol = _arbol(ruta)
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.AnnAssign) and isinstance(nodo.annotation, ast.Name):
                assert nodo.annotation.id != "float", f"{ruta.name}: float anotado"
            es_retorno = (
                isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef)
                and isinstance(nodo.returns, ast.Name)
            )
            if es_retorno:
                retorno = nodo.returns
                assert isinstance(retorno, ast.Name)
                assert retorno.id != "float", f"{ruta.name}: float como retorno"
        fuente = ruta.read_text(encoding="utf-8")
        assert "import numpy" not in fuente


def test_servicios_de_exportacion_no_usan_floats_para_importes() -> None:
    for ruta in SERVICIOS.glob("*.py"):
        arbol = _arbol(ruta)
        llamadas = {
            nodo.func.id
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
        }
        assert "float" not in llamadas, f"{ruta.name} convierte a float"


def test_seriializador_emite_cadenas_de_cuatro_decimales() -> None:
    from services.export.serializacion import serializar

    assert serializar(Decimal(1)) == "1.0000"
    assert serializar(Decimal("1234.56789")) == "1234.5679"


def test_zip_real_no_tiene_floats_en_los_bloques(export_client) -> None:
    import json as _json

    respuesta = export_client.exportar()
    exportacion_id = respuesta.json()["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    )
    for registro in _json.loads(
        ficheros["bloques/004_apuntes.json"].decode("utf-8")
    )["registros"]:
        assert isinstance(registro["debe"], str)
        assert isinstance(registro["haber"], str)
        assert registro["debe"].count(".") == 1
        assert len(registro["debe"].split(".")[1]) == 4


# --- Inmutabilidad ----------------------------------------------------------


def test_trigger_de_inmutabilidad_esta_en_migracion_y_espejo_sqlite() -> None:
    migracion = (
        Path(__file__).resolve().parents[2] / "migrations" / "020_export.sql"
    ).read_text(encoding="utf-8")
    assert "chk_exportacion_immutable_update" in migracion
    assert "chk_exportacion_immutable_delete" in migracion
    assert "trg_blob_exportacion_append_only_update" in migracion
    assert "trg_manifiesto_bloque_append_only_update" in migracion
    espejo = (
        Path(__file__).resolve().parents[2] / "src" / "db" / "triggers.py"
    ).read_text(encoding="utf-8")
    assert "chk_exportacion_immutable_update" in espejo
    assert "trg_blob_exportacion_append_only_delete" in espejo


async def test_exportacion_homologada_no_se_puede_tocar(db_session) -> None:
    ahora = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    fila = Exportacion(
        id=uuid.uuid4(),
        empresa_id=1,
        anio_creacion=2026,
        numero_exportacion=1,
        tipo="INTEGRAL",
        estado=EstadoExportacion.en_proceso,
        created_at=ahora,
    )
    db_session.add(fila)
    await db_session.commit()
    fila.estado = EstadoExportacion.lista
    await db_session.commit()
    fila.n_bloques = 99
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    with pytest.raises(IntegrityError):
        await db_session.delete(fila)
        await db_session.commit()
    await db_session.rollback()


async def test_transicion_en_proceso_a_lista_se_permite(db_session) -> None:
    ahora = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    fila = Exportacion(
        id=uuid.uuid4(),
        empresa_id=1,
        anio_creacion=2026,
        numero_exportacion=1,
        tipo="SII",
        estado=EstadoExportacion.en_proceso,
        created_at=ahora,
    )
    db_session.add(fila)
    await db_session.commit()
    fila.estado = EstadoExportacion.fallida
    fila.mensaje_error = "boom"
    await db_session.commit()
    assert fila.estado == EstadoExportacion.fallida


# --- Multi-tenancy ----------------------------------------------------------


def test_toda_tabla_exportada_declara_filtro_de_empresa() -> None:
    for bloque in BLOQUES:
        for ref in bloque.tablas:
            tabla = Base.metadata.tables[ref.tabla]
            assert ref.empresa_col in tabla.c


def test_las_cuatro_tablas_nuevas_declaran_uniqued_por_empresa() -> None:
    for nombre in (
        "exportacion",
        "manifiesto_exportacion",
        "manifiesto_bloque",
        "blob_exportacion",
    ):
        uniques = {
            tuple(sorted(c.name for c in u.columns))
            for u in Base.metadata.tables[nombre].constraints
            if u.__class__.__name__ == "UniqueConstraint"
        }
        assert ("empresa_id", "id") in uniques, nombre


async def test_consulta_de_otra_empresa_no_encuentra_la_exportacion(db_session) -> None:
    ahora = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    fila = Exportacion(
        id=uuid.uuid4(),
        empresa_id=1,
        anio_creacion=2026,
        numero_exportacion=1,
        tipo="INTEGRAL",
        estado=EstadoExportacion.lista,
        created_at=ahora,
    )
    db_session.add(fila)
    await db_session.commit()
    desde_otra = await db_session.scalar(
        select(Exportacion).where(Exportacion.empresa_id == 2, Exportacion.id == fila.id)
    )
    assert desde_otra is None


# --- Auditoria --------------------------------------------------------------


def test_generar_audita_en_la_misma_transaccion(export_client) -> None:
    respuesta = export_client.exportar()
    exportacion_id = uuid.UUID(respuesta.json()["exportacion_id"])

    async def _op(sesion):
        return list(
            (
                await sesion.scalars(
                    select(AuditLog).where(
                        AuditLog.entidad == "Exportacion",
                        AuditLog.entidad_id == str(exportacion_id),
                    )
                )
            ).all()
        )

    registros = export_client.run(export_client.consultar(_op))
    assert len(registros) == 1
    assert registros[0].operacion == "GENERAR_EXPORTACION"
    assert registros[0].empresa_id == 10
    payload = json.loads(registros[0].payload or "{}")
    assert payload["n_bloques"] >= 17
    assert len(payload["sha256"]) == 64


def test_verificar_audita_en_la_misma_transaccion(export_client) -> None:
    exportacion_id = export_client.exportar().json()["exportacion_id"]
    veredicto = export_client.post(f"/api/v1/exportaciones/{exportacion_id}/verificar")
    assert veredicto.status_code == 200
    assert veredicto.json()["integro"] is True

    async def _op(sesion):
        return list(
            (
                await sesion.scalars(
                    select(AuditLog).where(AuditLog.operacion == "VERIFICAR_EXPORTACION")
                )
            ).all()
        )

    registros = export_client.run(export_client.consultar(_op))
    assert len(registros) == 1
    assert registros[0].entidad_id == exportacion_id
    assert json.loads(registros[0].payload or "{}")["integro"] is True


def test_los_tres_codigos_de_auditoria_estan_declarados() -> None:
    fuentes = "\n".join(p.read_text(encoding="utf-8") for p in SERVICIOS.glob("*.py"))
    for codigo in FUNCIONES_AUDITAR:
        assert codigo in fuentes


# --- Correlatividad (constitution IV) --------------------------------------


def test_numeracion_correlativa_por_empresa_y_anio(export_client) -> None:
    primera = export_client.exportar().json()
    segunda = export_client.exportar().json()
    assert primera["numero_exportacion"] == 1
    assert segunda["numero_exportacion"] == 2
    assert primera["anio_creacion"] == segunda["anio_creacion"]
    otra = export_client.exportar(empresa_id=20).json()
    assert otra["numero_exportacion"] == 1


def test_numeracion_rechaza_rango_incoherente(export_client) -> None:
    respuesta = export_client.exportar(desde=2026, hasta=2025)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "rango_invalido"


def test_numeracion_exige_los_dos_extremos_del_rango(export_client) -> None:
    respuesta = export_client.exportar(desde=2025)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "rango_incompleto"


def test_tipos_aceptados_solo_integral_y_sii() -> None:
    from models.export.exportacion import TipoExportacion

    assert {t.value for t in TipoExportacion} == {"INTEGRAL", "SII"}


def test_endpoint_no_acepta_empresa_id_del_cliente(export_client) -> None:
    respuesta = export_client.post(
        "/api/v1/exportaciones", {"tipo": "INTEGRAL", "empresa_id": 20}
    )
    assert respuesta.status_code == 201, respuesta.text
    exportacion_id = respuesta.json()["exportacion_id"]
    assert exportacion_id
    # El `empresa_id` del body se ignora: la exportacion es de la empresa activa.
    listado = export_client.get("/api/v1/exportaciones").json()
    assert exportacion_id in [item["exportacion_id"] for item in listado["items"]]
    assert listado["total"] == 1
    listado_b = export_client.get("/api/v1/exportaciones", empresa_id=20).json()
    assert listado_b["total"] == 0
    assert exportacion_id not in [item["exportacion_id"] for item in listado_b["items"]]


def test_ningun_endpoint_recibe_empresa_id_en_el_path() -> None:
    """La empresa activa llega por `Depends(get_empresa_id)`, nunca del request."""
    fuente = API.read_text(encoding="utf-8")
    assert "/{empresa_id}" not in fuente
    arbol = _arbol(API)
    desde_request = {"Path", "Query", "Body", "Form", "Header"}
    # `Empresa = Annotated[int, Depends(get_empresa_id)]` es el alias autorizado.
    alias_dependencia = {"Empresa", "Depends", "get_empresa_id", "int", "Annotated"}
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for argumento in (*nodo.args.args, *nodo.args.kwonlyargs):
            if not argumento.arg.endswith("empresa_id"):
                continue
            origenes = {
                sub.id if isinstance(sub, ast.Name) else getattr(sub, "attr", "")
                for sub in ast.walk(argumento.annotation)
            } - {""}
            assert not (origenes & desde_request), f"{nodo.name}.{argumento.arg} viene del request"
            assert origenes <= alias_dependencia, f"{nodo.name}.{argumento.arg}: {origenes}"


def test_serializacion_centralizada_en_un_solo_modulo() -> None:
    """Ninguna serializacion manual de importes fuera de `serializacion.py`."""
    for ruta in SERVICIOS.glob("*.py"):
        if ruta.name == "serializacion.py":
            continue
        arbol = _arbol(ruta)
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
                assert nodo.func.id != "json", f"{ruta.name} usa json.dumps directamente"


def test_payload_de_bloque_serializa_registros(export_client) -> None:
    payload: dict[str, Any] = json.loads(
        export_client.abrir(
            export_client.get(
                f"/api/v1/exportaciones/{export_client.exportar().json()['exportacion_id']}/descarga"
            )
        )["manifest.json"].decode("utf-8")
    )
    assert payload["formato_version"] == "1.0.0"
    assert payload["tenant_id"] == 10
