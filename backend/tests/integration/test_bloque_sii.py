"""Bloque SII de la exportacion (SPEC-029 T041, US3, quickstart Scenario 5).

`tipo=SII` anade `bloques/datos_sii/facturas_emitidas.json` y
`facturas_recibidas.json` con los campos AEAT; una empresa sin `ConfigSii` recibe
422 `sin_configuracion_sii`.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

CAMPOS_AEAT = {
    "NIF",
    "NombreRazon",
    "TipoFactura",
    "FechaOperacion",
    "FechaExpedicion",
    "NumeroFactura",
    "ClaveRegimen",
    "BaseImponible",
    "TipoImpositivo",
    "CuotaRepercutida",
    "ImporteTotal",
    "EstadoCuadre",
}


def test_zip_de_tipo_sii_incluye_los_dos_ficheros(export_client) -> None:
    respuesta = export_client.exportar(tipo="SII")
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "SII"
    exportacion_id = cuerpo["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    )
    assert "bloques/datos_sii/facturas_emitidas.json" in ficheros
    assert "bloques/datos_sii/facturas_recibidas.json" in ficheros
    emitidas = json.loads(
        ficheros["bloques/datos_sii/facturas_emitidas.json"].decode("utf-8")
    )
    recibidas = json.loads(
        ficheros["bloques/datos_sii/facturas_recibidas.json"].decode("utf-8")
    )
    assert emitidas["conteo_registros"] == 1
    assert recibidas["conteo_registros"] == 1
    assert emitidas["registros"][0]["TipoFactura"] == "F1"
    assert recibidas["registros"][0]["TipoFactura"] == "F2"
    assert emitidas["registros"][0]["Naturaleza"] == "VENTA"
    assert recibidas["registros"][0]["Naturaleza"] == "COMPRA"


def test_los_registros_tienen_los_campos_de_la_aeat(export_client) -> None:
    exportacion_id = export_client.exportar(tipo="SII").json()["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    )
    emitidas = json.loads(
        ficheros["bloques/datos_sii/facturas_emitidas.json"].decode("utf-8")
    )
    for registro in emitidas["registros"]:
        assert CAMPOS_AEAT <= set(registro)
        assert registro["NIF"].startswith("A")
        assert registro["NombreRazon"].startswith("Cliente")
        assert registro["ClaveRegimen"] == "01"
        assert registro["EstadoCuadre"] == "CUADRADO"
        assert Decimal(registro["BaseImponible"]) == Decimal("1000.0000")
        assert Decimal(registro["CuotaRepercutida"]) == Decimal("210.0000")
        assert Decimal(registro["ImporteTotal"]) == Decimal("1210.0000")
        assert registro["TipoImpositivo"] == "21.00"


def test_el_bloque_sii_tambien_aparece_en_integral(export_client) -> None:
    """T043: `ConfigSii.obligado_sii=true` anade el bloque aunque el tipo sea INTEGRAL."""
    exportacion_id = export_client.exportar().json()["exportacion_id"]
    assert export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}/descarga"
    ).status_code == 200
    detalle = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}"
    ).json()
    nombres = {b["bloque"] for b in detalle["manifiesto"]["bloques"]}
    assert "datos_sii.facturas_emitidas" in nombres


def test_el_sii_esta_en_el_manifiesto_con_su_conteo(export_client) -> None:
    exportacion_id = export_client.exportar(tipo="SII").json()["exportacion_id"]
    detalle = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}"
    ).json()["manifiesto"]
    lineas = {b["bloque"]: b for b in detalle["bloques"]}
    assert lineas["datos_sii.facturas_emitidas"]["conteo_registros"] == 1
    assert lineas["datos_sii.facturas_emitidas"]["ruta"] == (
        "bloques/datos_sii/facturas_emitidas.json"
    )
    assert len(lineas["datos_sii.facturas_emitidas"]["sha256"]) == 64
    assert detalle["n_bloques"] == len(detalle["bloques"])


def test_sii_conserva_la_integridad_del_zip(export_client) -> None:
    exportacion_id = export_client.exportar(tipo="SII").json()["exportacion_id"]
    veredicto = export_client.post(
        f"/api/v1/exportaciones/{exportacion_id}/verificar"
    ).json()
    assert veredicto["integro"] is True
    nombres = {b["bloque"] for b in veredicto["bloques"]}
    assert "datos_sii.facturas_emitidas" in nombres
    assert "datos_sii.facturas_recibidas" in nombres


def test_sin_configuracion_sii_da_422(export_client) -> None:
    respuesta = export_client.exportar(empresa_id=20, tipo="SII")
    assert respuesta.status_code == 422
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == "sin_configuracion_sii"
    assert "ConfigSii" in detalle["detail"]
    # No queda ninguna exportacion a medias.
    listado = export_client.get("/api/v1/exportaciones", empresa_id=20).json()
    fallidas = [i for i in listado["items"] if i["estado"] == "fallida"]
    assert len(fallidas) == 1
    assert fallidas[0]["mensaje_error"]


def test_el_bloque_sii_se_lee_del_zip_y_no_se_recalcula(export_client) -> None:
    """Regression: la API lee el blob inmutable, no recalcula con datos nuevos.

    Si el tenant cambia despues de exportar, la respuesta debe seguir siendo
    exactamente lo que contiene el ZIP (research D9).
    """
    export_client.put(
        "/api/v1/exportaciones/sii/config",
        {"obligado_sii": True, "clave_regimen": "05"},
        empresa_id=10,
    )
    exportacion_id = export_client.exportar(tipo="SII").json()["exportacion_id"]
    antes = export_client.get(f"/api/v1/exportaciones/{exportacion_id}/sii").json()
    assert antes["config"]["clave_regimen"] == "05"

    # Se anade una factura nueva y se cambia el regimen tras exportar.
    import uuid
    from datetime import date
    from decimal import Decimal

    from sqlalchemy import select

    from models.invoice.factura import Factura, FacturaEstado, FacturaTipo

    async def _op(sesion):
        raiz = await sesion.scalar(
            select(Factura).where(
                Factura.empresa_id == 10, Factura.tipo == FacturaTipo.VENTA
            )
        )
        sesion.add(
            Factura(
                id=uuid.uuid4(),
                empresa_id=10,
                serie_id=raiz.serie_id,
                numero=90,
                ejercicio=2025,
                fecha=date(2025, 11, 1),
                tipo=FacturaTipo.VENTA,
                tercero_id=raiz.tercero_id,
                importe_base=Decimal("300.0000"),
                importe_iva=Decimal("63.0000"),
                importe_total=Decimal("363.0000"),
                estado=FacturaEstado.emitida,
            )
        )
        await sesion.flush()

    export_client.run(export_client.mutar(_op))
    export_client.put(
        "/api/v1/exportaciones/sii/config",
        {"obligado_sii": True, "clave_regimen": "16"},
        empresa_id=10,
    )

    despues = export_client.get(f"/api/v1/exportaciones/{exportacion_id}/sii").json()
    assert despues == antes
    emitidas = next(
        b for b in despues["bloques_sii"] if b["nombre"] == "facturas_emitidas"
    )
    assert emitidas["conteo"] == 1
    assert all(r["ClaveRegimen"] == "05" for r in emitidas["registros"])


def test_el_zip_es_la_fuente_del_bloque_sii(export_client) -> None:
    """`leer_bloque_sii` reconstruye el bloque exactamente desde el binario."""
    import json

    from services.export.sii import leer_bloque_sii

    exportacion_id = export_client.exportar(tipo="SII").json()["exportacion_id"]
    contenido = _zip_bytes(export_client, exportacion_id)
    config, bloques = leer_bloque_sii(contenido)
    assert set(bloques) == {"facturas_emitidas", "facturas_recibidas"}
    assert config["clave_regimen"] == "01"
    assert config["obligado_sii"] is True
    assert json.dumps(bloques)  # serializable sin datos no-JSON


def test_el_payload_sii_conserva_la_configuracion_completa(export_client) -> None:
    """El payload del ZIP serializa **toda** la configuracion de la cabecera AEAT,
    no solo `clave_regimen` y `sin_anexo`.

    Sin `entidad_representante_id` y `fecha_alta` en el payload, la lectura del
    bloque desde el ZIP (que es la via que respeta la inmutabilidad de la
    exportacion) devolvia una configuracion incompleta y distinta de la que
    expone la API, y el manifiesto historico no conservaba el alta en el censal.
    """
    from services.export.sii import leer_bloque_sii, ruta_sii

    export_client.put(
        "/api/v1/exportaciones/sii/config",
        {
            "obligado_sii": True,
            "clave_regimen": "05",
            "sin_anexo": True,
            "entidad_representante_id": "3f1c8a52-9d4e-4a1b-8c77-2e6b1a9d0f31",
            "fecha_alta": "2026-01-15",
        },
    )
    exportacion_id = export_client.exportar(tipo="SII").json()["exportacion_id"]
    contenido = _zip_bytes(export_client, exportacion_id)

    config, _ = leer_bloque_sii(contenido)
    assert config["clave_regimen"] == "05"
    assert config["sin_anexo"] is True
    assert config["entidad_representante_id"] == "3f1c8a52-9d4e-4a1b-8c77-2e6b1a9d0f31"
    assert config["fecha_alta"] == "2026-01-15"

    # Y los ficheros del ZIP lo llevan escrito, no solo la lectura.
    import io
    import json
    import zipfile

    with zipfile.ZipFile(io.BytesIO(contenido), "r") as archivo:
        for nombre in ("facturas_emitidas", "facturas_recibidas"):
            payload = json.loads(archivo.read(ruta_sii(nombre)).decode("utf-8"))
            assert payload["entidad_representante_id"] == config["entidad_representante_id"]
            assert payload["fecha_alta"] == config["fecha_alta"]

    # La API y el ZIP coinciden: ya no puede haber discrepancia.
    api = export_client.get(f"/api/v1/exportaciones/{exportacion_id}/sii").json()
    assert api["config"]["entidad_representante_id"] == config["entidad_representante_id"]
    assert api["config"]["fecha_alta"] == config["fecha_alta"]


def test_leer_bloque_sii_tolera_un_zip_generado_antes_del_cambio(export_client) -> None:
    """Retrocompatibilidad: un ZIP anterior a este cambio no tiene los dos campos
    nuevos y se sigue leyendo, devolviendo `None` (que es lo que entonces se
    guardaba) en vez de reventar con un `KeyError`."""
    import io
    import json
    import zipfile

    from services.export.sii import leer_bloque_sii, ruta_sii

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archivo:
        for nombre in ("facturas_emitidas", "facturas_recibidas"):
            archivo.writestr(
                ruta_sii(nombre),
                json.dumps(
                    {
                        "bloque": f"datos_sii.{nombre}",
                        "clave_regimen": "01",
                        "sin_anexo": False,
                        "conteo_registros": 0,
                        "registros": [],
                    }
                ),
            )
    config, bloques = leer_bloque_sii(buffer.getvalue())
    assert config["clave_regimen"] == "01"
    assert config["entidad_representante_id"] is None
    assert config["fecha_alta"] is None
    assert set(bloques) == {"facturas_emitidas", "facturas_recibidas"}

def _zip_bytes(export_client, exportacion_id: str, empresa_id: int = 10) -> bytes:
    respuesta = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}/descarga", empresa_id=empresa_id
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.content


def test_leer_bloque_sii_falla_si_el_zip_no_lo_contiene(export_client) -> None:
    """Un ZIP sin `datos_sii/` (empresa no obligada) da 422 `bloque_sii_ausente`."""
    from services.export.errores import ExportError
    from services.export.sii import leer_bloque_sii

    exportacion_id = export_client.exportar(empresa_id=20).json()["exportacion_id"]
    contenido = _zip_bytes(export_client, exportacion_id, empresa_id=20)
    with pytest.raises(ExportError) as info:
        leer_bloque_sii(contenido)
    assert info.value.code == "bloque_sii_ausente"
    assert info.value.status_code == 422
    # Y el endpoint lo impide antes, con su propio codigo.
    respuesta = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}/sii", empresa_id=20
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "exportacion_no_sii"


def test_creado_por_es_el_usuario_autenticado(export_client) -> None:
    """El data-model pide el usuario que ejecuta la exportacion, no una etiqueta."""
    cuerpo = export_client.exportar(token_key="accountant").json()
    assert cuerpo["creado_por"] == "2"
    detalle = export_client.get(
        f"/api/v1/exportaciones/{cuerpo['exportacion_id']}", token_key="accountant"
    ).json()
    assert detalle["creado_por"] == "2"
    export_client.put(
        "/api/v1/exportaciones/sii/config",
        {"obligado_sii": True, "clave_regimen": "02", "sin_anexo": True},
        empresa_id=20,
    )
    respuesta = export_client.exportar(empresa_id=20, tipo="SII")
    assert respuesta.status_code == 201, respuesta.text
    exportacion_id = respuesta.json()["exportacion_id"]
    detalle = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}/sii", empresa_id=20
    ).json()
    assert detalle["config"]["clave_regimen"] == "02"
    assert detalle["config"]["sin_anexo"] is True
    for bloque in detalle["bloques_sii"]:
        assert bloque["conteo"] == len(bloque["registros"])
        for registro in bloque["registros"]:
            assert registro["ClaveRegimen"] == "02"


def test_una_rectificativa_se_clasifica_por_su_factura_raiz(export_client) -> None:
    """Una rectificativa de venta va a emitidas, no a recibidas."""
    import uuid
    from datetime import date

    from sqlalchemy import select

    from models.invoice.factura import Factura, FacturaEstado, FacturaTipo

    async def _op(sesion):
        raiz = await sesion.scalar(
            select(Factura).where(
                Factura.empresa_id == 10, Factura.tipo == FacturaTipo.VENTA
            )
        )
        sesion.add(
            Factura(
                id=uuid.uuid4(),
                empresa_id=10,
                serie_id=raiz.serie_id,
                numero=77,
                ejercicio=2025,
                fecha=date(2025, 9, 1),
                tipo=FacturaTipo.RECTIFICATIVA,
                tercero_id=raiz.tercero_id,
                factura_original_id=raiz.id,
                importe_base=Decimal("100.0000"),
                importe_iva=Decimal("21.0000"),
                importe_total=Decimal("121.0000"),
                estado=FacturaEstado.emitida,
            )
        )
        await sesion.flush()

    export_client.run(export_client.mutar(_op))
    exportacion_id = export_client.exportar(tipo="SII").json()["exportacion_id"]
    payload = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}/sii"
    ).json()
    emitidas = next(b for b in payload["bloques_sii"] if b["nombre"] == "facturas_emitidas")
    recibidas = next(b for b in payload["bloques_sii"] if b["nombre"] == "facturas_recibidas")
    assert emitidas["conteo"] == 2
    assert recibidas["conteo"] == 1
    rectificativas = [r for r in emitidas["registros"] if r["TipoFactura"] == "R1"]
    assert len(rectificativas) == 1
    assert rectificativas[0]["NumeroFactura"] == "F10-77"


def test_solo_se_exportan_facturas_emitidas(export_client) -> None:
    import uuid
    from datetime import date

    from sqlalchemy import select

    from models.invoice.factura import Factura, FacturaEstado, FacturaTipo

    async def _op(sesion):
        raiz = await sesion.scalar(
            select(Factura).where(
                Factura.empresa_id == 10, Factura.tipo == FacturaTipo.VENTA
            )
        )
        sesion.add(
            Factura(
                id=uuid.uuid4(),
                empresa_id=10,
                serie_id=raiz.serie_id,
                numero=78,
                ejercicio=2025,
                fecha=date(2025, 10, 1),
                tipo=FacturaTipo.VENTA,
                tercero_id=raiz.tercero_id,
                importe_base=Decimal("50.0000"),
                importe_iva=Decimal("10.5000"),
                importe_total=Decimal("60.5000"),
                estado=FacturaEstado.borrador,
            )
        )
        await sesion.flush()

    export_client.run(export_client.mutar(_op))
    exportacion_id = export_client.exportar(tipo="SII").json()["exportacion_id"]
    payload = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}/sii"
    ).json()
    emitidas = next(b for b in payload["bloques_sii"] if b["nombre"] == "facturas_emitidas")
    assert emitidas["conteo"] == 1


@pytest.mark.parametrize("empresa_id", [10, 20])
def test_el_endpoint_sii_responde_200_a_la_empresa_activa(export_client, empresa_id) -> None:
    if empresa_id == 20:
        export_client.put(
            "/api/v1/exportaciones/sii/config",
            {"obligado_sii": True, "clave_regimen": "01"},
            empresa_id=20,
        )
    exportacion_id = export_client.exportar(
        empresa_id=empresa_id, tipo="SII"
    ).json()["exportacion_id"]
    respuesta = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}/sii", empresa_id=empresa_id
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["config"]["obligado_sii"] is True
