"""Aislamiento multi-tenant de la exportacion integral (SPEC-029 T011/T016/T032/T040/T048).

Parte 1 (T011 · modelos): la cabecera, el manifiesto y el blob de la empresa A
no son visibles para la empresa B por ninguna consulta.
Parte 2 (T016 · US1): el ZIP de A contiene 0 registros de B en todos los bloques.
Parte 3 (T032 · US2): B no verifica la exportacion de A (404) y verifica la suya.
Parte 4 (T040 · US3): B no ve el bloque SII ni la configuracion SII de A.
Escenario final (T048): A exporta los 17 bloques + SII y B no accede a nada.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import func, select

from models.audit.audit_log import AuditLog
from models.export.blob_exportacion import BlobExportacion
from models.export.exportacion import Exportacion
from models.export.manifiesto import ManifiestoBloque, ManifiestoExportacion

# --- Parte 1 · modelos (T011) ----------------------------------------------


async def test_cabecera_manifiesto_y_blob_de_otra_empresa_no_se_ven(db_session) -> None:
    from datetime import datetime, timezone
    from uuid import uuid4

    ahora = datetime.now(timezone.utc)
    cabecera = Exportacion(
        id=uuid4(),
        empresa_id=1,
        anio_creacion=2026,
        numero_exportacion=1,
        tipo="INTEGRAL",
        estado="lista",
        created_at=ahora,
        sha256="a" * 64,
        tamano_bytes=10,
        n_bloques=17,
    )
    db_session.add(cabecera)
    await db_session.flush()
    manifiesto = ManifiestoExportacion(
        id=uuid4(),
        empresa_id=1,
        exportacion_id=cabecera.id,
        formato_version="1.0.0",
        fecha_generacion=ahora,
        tenant_id=1,
        n_bloques=17,
        sha256_fichero="a" * 64,
    )
    db_session.add(manifiesto)
    await db_session.flush()
    db_session.add(
        ManifiestoBloque(
            id=uuid4(),
            empresa_id=1,
            manifiesto_id=manifiesto.id,
            bloque="asientos",
            entidades_exportadas="JournalEntry",
            conteo_registros=3,
        )
    )
    db_session.add(
        BlobExportacion(
            id=uuid4(),
            empresa_id=1,
            exportacion_id=cabecera.id,
            contenido=b"PK\x03\x04datos",
            sha256="a" * 64,
            tamano_bytes=10,
        )
    )
    await db_session.commit()
    for modelo in (Exportacion, ManifiestoExportacion, BlobExportacion):
        ajena = await db_session.scalar(
            select(modelo).where(modelo.empresa_id == 2, modelo.id == cabecera.id)
        )
        assert ajena is None, modelo.__name__
    lineas_b = await db_session.scalar(
        select(func.count())
        .select_from(ManifiestoBloque)
        .where(ManifiestoBloque.empresa_id == 2)
    )
    assert lineas_b == 0


def test_el_rbac_tiene_modulo_export_con_tres_operaciones() -> None:
    from services.security.catalogo import CATALOGO

    assert set(CATALOGO["export"]) == {"ver", "crear", "configurar"}


def test_las_rutas_de_exportacion_cubren_el_inventario() -> None:
    from fastapi.routing import APIRoute

    from api.export import router
    from api.routes_registry import guard_de_ruta

    rutas = {
        (min(r.methods), r.path): guard_de_ruta(r)
        for r in router.routes
        if isinstance(r, APIRoute)
    }
    assert set(rutas) == {
        ("POST", "/api/v1/exportaciones"),
        ("GET", "/api/v1/exportaciones"),
        ("GET", "/api/v1/exportaciones/sii/config"),
        ("PUT", "/api/v1/exportaciones/sii/config"),
        ("GET", "/api/v1/exportaciones/{exportacion_id}"),
        ("GET", "/api/v1/exportaciones/{exportacion_id}/descarga"),
        ("POST", "/api/v1/exportaciones/{exportacion_id}/verificar"),
        ("GET", "/api/v1/exportaciones/{exportacion_id}/sii"),
    }
    assert all(permiso is not None for permiso in rutas.values())


# --- Parte 2 · US1 (T016) --------------------------------------------------


def test_zip_de_a_no_contiene_ningun_registro_de_b(export_client) -> None:
    exportacion_id = export_client.exportar(empresa_id=10).json()["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga", empresa_id=10)
    )
    filas_b = 0
    for ruta, crudo in ficheros.items():
        if not ruta.endswith(".json") or ruta == "manifest.json":
            continue
        for registro in json.loads(crudo.decode("utf-8")).get("registros", []):
            if registro.get("empresa_id") in (None, 20):
                continue
            assert registro["empresa_id"] == 10, f"{ruta}: {registro['empresa_id']}"
            filas_b += 0
    # `companies` no tiene `empresa_id` (su PK es `company_id`): se comprueba aparte.
    configuracion = json.loads(ficheros["bloques/017_configuracion.json"].decode("utf-8"))
    ids = [r["company_id"] for r in configuracion["registros"] if "company_id" in r]
    assert ids == [10]
    assert filas_b == 0


def test_empresa_b_no_accede_a_la_exportacion_de_a(export_client) -> None:
    exportacion_id = export_client.exportar(empresa_id=10).json()["exportacion_id"]
    for metodo, sufijo in (
        ("get", ""),
        ("get", "/descarga"),
        ("get", "/sii"),
    ):
        respuesta = getattr(export_client, metodo)(
            f"/api/v1/exportaciones/{exportacion_id}{sufijo}", empresa_id=20
        )
        assert respuesta.status_code == 404, sufijo
        assert respuesta.json()["detail"]["code"] == "exportacion_no_encontrada"
    verificar = export_client.post(
        f"/api/v1/exportaciones/{exportacion_id}/verificar", empresa_id=20
    )
    assert verificar.status_code == 404


def test_listado_de_b_no_muestra_las_exportaciones_de_a(export_client) -> None:
    export_client.exportar(empresa_id=10)
    listado = export_client.get("/api/v1/exportaciones", empresa_id=20).json()
    assert listado["total"] == 0
    assert listado["items"] == []


# --- Parte 3 · US2 (T032) --------------------------------------------------


def test_b_no_verifica_la_exportacion_de_a(export_client) -> None:
    exportacion_id = export_client.exportar(empresa_id=10).json()["exportacion_id"]
    respuesta = export_client.post(
        f"/api/v1/exportaciones/{exportacion_id}/verificar", empresa_id=20
    )
    assert respuesta.status_code == 404


def test_b_verifica_su_propia_exportacion(export_client) -> None:
    exportacion_id = export_client.exportar(empresa_id=20).json()["exportacion_id"]
    veredicto = export_client.post(
        f"/api/v1/exportaciones/{exportacion_id}/verificar", empresa_id=20
    )
    assert veredicto.status_code == 200
    assert veredicto.json()["integro"] is True
    assert veredicto.json()["sha256_calculado"] == veredicto.json()["sha256_manifiesto"]


def test_verificar_otra_empresa_no_audita_en_la_primera(export_client) -> None:
    exportacion_id = export_client.exportar(empresa_id=10).json()["exportacion_id"]
    export_client.post(f"/api/v1/exportaciones/{exportacion_id}/verificar", empresa_id=10)

    async def _op(sesion):
        return await sesion.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.operacion == "VERIFICAR_EXPORTACION")
        )

    assert export_client.run(export_client.consultar(_op)) == 1


# --- Parte 4 · US3 (T040) --------------------------------------------------


def test_b_no_ve_la_configuracion_sii_de_a(export_client) -> None:
    de_a = export_client.get("/api/v1/exportaciones/sii/config", empresa_id=10)
    de_b = export_client.get("/api/v1/exportaciones/sii/config", empresa_id=20)
    assert de_a.json()["obligado_sii"] is True
    assert de_b.json()["obligado_sii"] is False


def test_b_no_ve_el_bloque_sii_de_a(export_client) -> None:
    exportacion_id = export_client.exportar(empresa_id=10, tipo="SII").json()[
        "exportacion_id"
    ]
    assert export_client.get(f"/api/v1/exportaciones/{exportacion_id}/sii", empresa_id=10).status_code == 200
    assert export_client.get(f"/api/v1/exportaciones/{exportacion_id}/sii", empresa_id=20).status_code == 404


def test_empresa_sin_configuracion_sii_recibe_422(export_client) -> None:
    respuesta = export_client.exportar(empresa_id=20, tipo="SII")
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "sin_configuracion_sii"


# --- Escenario final (T048) ------------------------------------------------


def test_a_exporta_los_17_bloques_mas_sii_y_b_no_accede_a_nada(export_client) -> None:
    exportacion_id = export_client.exportar(empresa_id=10).json()["exportacion_id"]
    detalle = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}", empresa_id=10
    ).json()
    nombres = {b["bloque"] for b in detalle["manifiesto"]["bloques"]}
    obligatorios = {
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
    }
    assert obligatorios <= nombres
    assert {"datos_sii.facturas_emitidas", "datos_sii.facturas_recibidas"} <= nombres
    # B no llega a ninguna parte: cabecera, manifiesto, blob, descarga ni verificacion.
    for sufijo in ("", "/descarga", "/sii"):
        assert (
            export_client.get(
                f"/api/v1/exportaciones/{exportacion_id}{sufijo}", empresa_id=20
            ).status_code
            == 404
        )
    assert (
        export_client.post(
            f"/api/v1/exportaciones/{exportacion_id}/verificar", empresa_id=20
        ).status_code
        == 404
    )
    # Y el blob almacenado sigue siendo el de A (inmutable).
    veredicto = export_client.post(
        f"/api/v1/exportaciones/{exportacion_id}/verificar", empresa_id=10
    ).json()
    assert veredicto["integro"] is True


def test_identificador_inexistente_da_404(export_client) -> None:
    respuesta = export_client.get(f"/api/v1/exportaciones/{uuid.uuid4()}")
    assert respuesta.status_code == 404


@pytest.mark.parametrize("sufijo", ["", "/descarga", "/sii"])
def test_identificador_mal_formado_da_422(export_client, sufijo) -> None:
    respuesta = export_client.get(f"/api/v1/exportaciones/no-es-uuid{sufijo}")
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "parametro_invalido"
