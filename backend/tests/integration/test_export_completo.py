"""Exportacion completa de un tenant (SPEC-029 T027).

Reproduce el quickstart Scenario 1 y Scenario 6: el ZIP contiene los registros
esperados de cada bloque, la huella del binario es verificable y los conteos del
manifiesto cuadran. El caso de tenant con bloques vacios debe generar la
exportacion igualmente, con `conteo_registros = 0`.
"""

from __future__ import annotations

import hashlib
import json

from services.export.zip_generator import leer_manifiesto, rutas_zip
from tests.conftest import crear_empresa


def _exportar(export_client, **kwargs):
    respuesta = export_client.exportar(**kwargs)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def test_exportacion_completa_devuelve_zip_consistente(export_client) -> None:
    cuerpo = _exportar(export_client)
    assert cuerpo["estado"] == "lista"
    assert cuerpo["numero_exportacion"] == 1
    assert cuerpo["tipo"] == "INTEGRAL"
    assert cuerpo["n_bloques"] >= 17
    assert len(cuerpo["sha256"]) == 64
    assert cuerpo["tamano_bytes"] > 0
    assert cuerpo["tamano_mb"].count(".") == 1
    assert len(cuerpo["tamano_mb"].split(".")[1]) == 4
    assert cuerpo["manifiesto"]["formato_version"] == "1.0.0"
    assert cuerpo["nombre_fichero"].startswith("export_10_1_")
    exportacion_id = cuerpo["exportacion_id"]
    descarga = export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    assert descarga.status_code == 200
    assert descarga.content[:2] == b"PK"
    assert hashlib.sha256(descarga.content).hexdigest() == cuerpo["sha256"]


def test_cada_bloque_tiene_los_registros_esperados(export_client) -> None:
    exportacion_id = _exportar(export_client)["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    )

    def _bloque(ordinal: int, nombre: str) -> dict:
        return json.loads(ficheros[f"bloques/{ordinal:03d}_{nombre}.json"].decode("utf-8"))

    # Bloques con datos sembrados por la fixture.
    plan = _bloque(1, "plan_cuentas")
    assert plan["conteo_registros"] == 82
    assert {r["code"] for r in plan["registros"]} >= {"4300", "7000", "5720"}

    asientos = _bloque(3, "asientos")
    assert asientos["conteo_registros"] == 2
    assert asientos["ejercicio_min"] == 2025
    assert asientos["ejercicio_max"] == 2026
    assert {r["ejercicio"] for r in asientos["registros"]} == {2025, 2026}

    apuntes = _bloque(4, "apuntes")
    assert apuntes["conteo_registros"] == 6
    debe = sum(float(r["debe"]) for r in apuntes["registros"])
    haber = sum(float(r["haber"]) for r in apuntes["registros"])
    assert round(debe, 4) == round(haber, 4)

    terceros = _bloque(5, "terceros")
    # La fixture crea un cliente y un proveedor, cada uno con su subcuenta.
    assert terceros["conteo_por_entidad"] == {"Tercero": 2, "TerceroSubcuenta": 2}

    facturas = _bloque(6, "facturas")
    assert facturas["conteo_por_entidad"] == {"SerieFactura": 1, "Factura": 2}

    lineas = _bloque(7, "lineas_factura")
    assert lineas["conteo_registros"] == 2

    vencimientos = _bloque(8, "vencimientos")
    assert vencimientos["conteo_registros"] == 1
    assert vencimientos["registros"][0]["importe"] == "1210.0000"

    configuracion = _bloque(17, "configuracion")
    assert configuracion["conteo_por_entidad"]["Company"] == 1

    # Bloques sin datos en la fixture: presentes con conteo 0.
    for ordinal, vacio in (
        (10, "remesas"),
        (11, "devoluciones"),
        (12, "amortizaciones"),
        (13, "cierres"),
        (14, "presupuestos"),
        (15, "previsiones"),
    ):
        payload = _bloque(ordinal, vacio)
        assert payload["conteo_registros"] == 0
        assert payload["registros"] == []
        assert payload["ejercicio_min"] is None


def test_manifiesto_interno_coincide_con_la_respuesta(export_client) -> None:
    cuerpo = _exportar(export_client)
    exportacion_id = cuerpo["exportacion_id"]
    contenido = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}/descarga"
    ).content
    manifiesto = leer_manifiesto(contenido)
    assert manifiesto["tenant_id"] == 10
    assert manifiesto["n_bloques"] == cuerpo["n_bloques"]
    assert {b["bloque"] for b in manifiesto["bloques"]} >= {
        b["bloque"] for b in cuerpo["manifiesto"]["bloques"]
    }
    assert rutas_zip(contenido) == sorted(rutas_zip(contenido))


def test_tenant_con_bloques_vacios_se_exporta_igual(export_client) -> None:
    """Quickstart Scenario 6: el manifiesto refleja el contenido real.

    Se crea la empresa 30 con solo el PGC (sin ningun dato de negocio), de modo
    que todos los bloques de datos quedan con `conteo_registros = 0`.
    """
    from models.iam.user_company import UserCompany, UserRol
    from services.acct.seed import seed_default_pgc

    async def _empresa_vacia(sesion):
        await crear_empresa(sesion, 30, nif="C00000030", razon_social="Vacia SL")
        await sesion.flush()
        sesion.add(
            UserCompany(
                id=30, user_id=1, company_id=30, role=UserRol.ADMIN, is_default=False
            )
        )
        await seed_default_pgc(sesion, 30)
        await sesion.flush()

    export_client.run(export_client.mutar(_empresa_vacia))
    cuerpo = _exportar(export_client, empresa_id=30)
    exportacion_id = cuerpo["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(
            f"/api/v1/exportaciones/{exportacion_id}/descarga", empresa_id=30
        )
    )
    plan = json.loads(ficheros["bloques/001_plan_cuentas.json"].decode("utf-8"))
    assert plan["conteo_registros"] == 82
    asientos = json.loads(ficheros["bloques/003_asientos.json"].decode("utf-8"))
    assert asientos["conteo_registros"] == 0
    assert asientos["registros"] == []
    assert asientos["ejercicio_min"] is None
    terceros = json.loads(ficheros["bloques/005_terceros.json"].decode("utf-8"))
    assert terceros["conteo_registros"] == 0
    veredicto = export_client.post(
        f"/api/v1/exportaciones/{exportacion_id}/verificar", empresa_id=30
    ).json()
    assert veredicto["integro"] is True
    detalle = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}", empresa_id=30
    ).json()
    conteos = {b["bloque"]: b["conteo_registros"] for b in detalle["manifiesto"]["bloques"]}
    assert len(conteos) == 17
    assert conteos["plan_cuentas"] == 82
    assert conteos["asientos"] == 0
    assert conteos["terceros"] == 0
    assert conteos["facturas"] == 0


def test_listado_paginado_y_filtros(export_client) -> None:
    for _ in range(3):
        export_client.exportar()
    export_client.exportar(tipo="SII")
    listado = export_client.get("/api/v1/exportaciones", page_size=2).json()
    assert listado["total"] == 4
    assert len(listado["items"]) == 2
    assert listado["page"] == 1
    integral = export_client.get("/api/v1/exportaciones", tipo="INTEGRAL").json()
    assert integral["total"] == 3
    lista = export_client.get("/api/v1/exportaciones", estado="lista").json()
    assert lista["total"] == 4
    fallida = export_client.get("/api/v1/exportaciones", estado="fallida").json()
    assert fallida["total"] == 0
    # El listado viene ordenado de mas reciente a mas antigua.
    numeros = [item["numero_exportacion"] for item in export_client.get("/api/v1/exportaciones").json()["items"]]
    assert numeros == sorted(numeros, reverse=True)


def test_zip_reproducible_entre_dos_generaciones(export_client) -> None:
    """Dos exportaciones seguidas del mismo estado dan los mismos bloques."""
    primera = _exportar(export_client)
    segunda = _exportar(export_client)
    uno = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{primera['exportacion_id']}/descarga")
    )
    dos = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{segunda['exportacion_id']}/descarga")
    )
    assert set(uno) == set(dos)
    for ruta in uno:
        if ruta == "manifest.json":
            continue
        assert uno[ruta] == dos[ruta], ruta


def test_detalle_expone_el_inventario_completo(export_client) -> None:
    exportacion_id = _exportar(export_client)["exportacion_id"]
    detalle = export_client.get(f"/api/v1/exportaciones/{exportacion_id}").json()
    assert detalle["manifiesto"]["n_bloques"] == len(detalle["manifiesto"]["bloques"])
    for linea in detalle["manifiesto"]["bloques"]:
        assert linea["bloque"]
        assert linea["ruta"].startswith("bloques/")
        assert linea["conteo_registros"] >= 0
        assert isinstance(linea["entidades_exportadas"], list)
        if linea["sha256"]:
            assert len(linea["sha256"]) == 64
    asientos = next(
        b for b in detalle["manifiesto"]["bloques"] if b["bloque"] == "asientos"
    )
    assert asientos["ejercicio_min"] == 2025
    assert asientos["ejercicio_max"] == 2026
    assert asientos["fecha_min"] == "2025-02-10"
    assert asientos["fecha_max"] == "2026-02-11"


def test_descarga_rechaza_exportacion_no_lista(export_client) -> None:
    """Una exportacion `fallida` no es descargable (409)."""
    import uuid
    from datetime import datetime, timezone

    from models.export.exportacion import EstadoExportacion, Exportacion

    identificador = uuid.uuid4()

    async def _crear(sesion):
        sesion.add(
            Exportacion(
                id=identificador,
                empresa_id=10,
                anio_creacion=2026,
                numero_exportacion=99,
                tipo="INTEGRAL",
                estado=EstadoExportacion.fallida,
                created_at=datetime.now(timezone.utc),
                mensaje_error="fallo simulado",
            )
        )
        await sesion.flush()

    export_client.run(export_client.mutar(_crear))
    respuesta = export_client.get(f"/api/v1/exportaciones/{identificador}/descarga")
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "exportacion_no_descargable"
    verificado = export_client.post(f"/api/v1/exportaciones/{identificador}/verificar")
    assert verificado.status_code == 409
    assert verificado.json()["detail"]["code"] == "exportacion_no_lista"
