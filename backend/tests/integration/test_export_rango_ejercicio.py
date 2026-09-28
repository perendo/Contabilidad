"""Filtro por rango de ejercicios (SPEC-029 T017, FR-005, quickstart Scenario 3).

Con `ejercicio_desde = ejercicio_hasta = 2025` los bloques temporales solo
contienen datos de 2025 y los bloques atemporales (plan de cuentas, terceros,
configuracion) se exportan integros. El manifiesto refleja `ejercicio_min` y
`ejercicio_max` de cada bloque.
"""

from __future__ import annotations

import json

import pytest

from services.export.bloques import bloque_por_nombre

#: Bloques que se exportan enteros aunque se filtre por ejercicio (research D3).
ATEMPORALES = ("plan_cuentas", "terceros")


def _exportar(export_client, desde=None, hasta=None, empresa_id=10):
    respuesta = export_client.exportar(
        empresa_id=empresa_id, desde=desde, hasta=hasta
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _manifiesto(export_client, exportacion_id, empresa_id=10):
    return export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}", empresa_id=empresa_id
    ).json()["manifiesto"]


def _bloque(export_client, exportacion_id, ordinal, nombre, empresa_id=10):
    ficheros = export_client.abrir(
        export_client.get(
            f"/api/v1/exportaciones/{exportacion_id}/descarga", empresa_id=empresa_id
        )
    )
    return json.loads(ficheros[f"bloques/{ordinal:03d}_{nombre}.json"].decode("utf-8"))


def test_rango_de_un_ejercicio_solo_trae_ese_ejercicio(export_client) -> None:
    cuerpo = _exportar(export_client, desde=2025, hasta=2025)
    assert cuerpo["ejercicio_desde"] == 2025
    assert cuerpo["ejercicio_hasta"] == 2025
    exportacion_id = cuerpo["exportacion_id"]

    asientos = _bloque(export_client, exportacion_id, 3, "asientos")
    assert asientos["conteo_registros"] == 1
    assert {r["ejercicio"] for r in asientos["registros"]} == {2025}
    assert asientos["ejercicio_min"] == asientos["ejercicio_max"] == 2025

    apuntes = _bloque(export_client, exportacion_id, 4, "apuntes")
    assert apuntes["conteo_registros"] == 3
    assert apuntes["ejercicio_min"] == apuntes["ejercicio_max"] == 2025

    facturas = _bloque(export_client, exportacion_id, 6, "facturas")
    assert facturas["conteo_por_entidad"]["Factura"] == 1
    lineas = _bloque(export_client, exportacion_id, 7, "lineas_factura")
    assert lineas["conteo_registros"] == 1

    vencimientos = _bloque(export_client, exportacion_id, 8, "vencimientos")
    assert vencimientos["conteo_registros"] == 1

    manifiesto = _manifiesto(export_client, exportacion_id)
    por_bloque = {b["bloque"]: b for b in manifiesto["bloques"]}
    assert por_bloque["asientos"]["ejercicio_min"] == 2025
    assert por_bloque["asientos"]["ejercicio_max"] == 2025
    assert por_bloque["apuntes"]["ejercicio_min"] == 2025
    assert por_bloque["facturas"]["ejercicio_min"] == 2025


def test_los_bloques_atemporales_se_exportan_completos(export_client) -> None:
    exportacion_id = _exportar(export_client, desde=2025, hasta=2025)["exportacion_id"]
    completo = _exportar(export_client)["exportacion_id"]
    for ordinal, nombre in ((1, "plan_cuentas"), (5, "terceros")):
        filtrado = _bloque(export_client, exportacion_id, ordinal, nombre)
        entero = _bloque(export_client, completo, ordinal, nombre)
        assert filtrado["conteo_registros"] == entero["conteo_registros"] > 0
        assert filtrado["registros"] == entero["registros"]


def test_sin_rango_se_exporta_el_tenant_completo(export_client) -> None:
    exportacion_id = _exportar(export_client)["exportacion_id"]
    asientos = _bloque(export_client, exportacion_id, 3, "asientos")
    assert asientos["conteo_registros"] == 2
    assert asientos["ejercicio_min"] == 2025
    assert asientos["ejercicio_max"] == 2026
    manifiesto = _manifiesto(export_client, exportacion_id)
    assert manifiesto["ejercicio_desde"] is None
    assert manifiesto["ejercicio_hasta"] is None


@pytest.mark.parametrize(
    ("desde", "hasta", "codigo"),
    [
        (2026, 2025, "rango_invalido"),
        (2025, None, "rango_incompleto"),
        (None, 2025, "rango_incompleto"),
    ],
)
def test_rangos_incoherentes_dan_422(export_client, desde, hasta, codigo) -> None:
    respuesta = export_client.exportar(desde=desde, hasta=hasta)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == codigo


def test_el_rango_tambien_filtra_el_bloque_sii(export_client) -> None:
    exportacion_id = _exportar(export_client, desde=2025, hasta=2025)["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    )
    emitidas = json.loads(
        ficheros["bloques/datos_sii/facturas_emitidas.json"].decode("utf-8")
    )
    recibidas = json.loads(
        ficheros["bloques/datos_sii/facturas_recibidas.json"].decode("utf-8")
    )
    assert {r["Ejercicio"] for r in emitidas["registros"]} == {2025}
    # La factura de compra es de 2026 y queda fuera del rango.
    assert recibidas["conteo_registros"] == 0


def test_integridad_se_mantiene_con_rango(export_client) -> None:
    exportacion_id = _exportar(export_client, desde=2026, hasta=2026)["exportacion_id"]
    veredicto = export_client.post(
        f"/api/v1/exportaciones/{exportacion_id}/verificar"
    ).json()
    assert veredicto["integro"] is True
    assert all(b["coincide"] for b in veredicto["bloques"])


def test_bloque_con_rango_usa_solape_para_las_versiones(export_client) -> None:
    """`catalogo_version` tiene `fecha_inicio`/`fecha_fin`: entra si se solapa."""
    import uuid as _uuid
    from datetime import date

    from models.catalog.catalogo_version import CatalogoVersion

    async def _version(sesion):
        sesion.add(
            CatalogoVersion(
                id=_uuid.uuid4(),
                empresa_id=10,
                numero_version=9,
                codigo="PGC-2020",
                fecha_inicio=date(2020, 1, 1),
                fecha_fin=date(2035, 12, 31),
                estado="vigente",
            )
        )
        await sesion.flush()

    export_client.run(export_client.mutar(_version))
    exportacion_id = _exportar(export_client, desde=2025, hasta=2025)["exportacion_id"]
    versiones = _bloque(export_client, exportacion_id, 2, "plan_cuentas_versiones")
    assert versiones["conteo_por_entidad"]["CatalogoVersion"] == 1
    bloque = bloque_por_nombre("plan_cuentas_versiones")
    assert bloque is not None and bloque.tablas[0].rango == ("fecha_inicio", "fecha_fin")
