"""Precision decimal en la exportacion (SPEC-029 T015/T039).

Parte 1 (T015): todo importe sale como cadena de 4 decimales, nunca `float`.
Parte 2 (T039): consistencia decimal del bloque SII con las facturas de origen.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from services.export.serializacion import (
    cuatro_decimales,
    iso_utc,
    serializar,
    volcar_json,
)
from tests.unit import export_support as soporte

#: Campos que son importes en el dominio: ninguno puede ser JSON numerico.
CAMPOS_IMPORTE = {
    "debe",
    "haber",
    "importe",
    "importe_base",
    "importe_iva",
    "importe_recargo",
    "importe_irpf",
    "importe_total",
    "base",
    "cuota_iva",
    "cuota_recargo",
    "cuota_irpf",
    "precio_unitario",
    "porcentaje_descuento",
    "cuota",
    "acumulado",
    "saldo",
    "total_debe",
    "total_haber",
    "resultado_ejercicio",
    "resultado_provisional",
}


def _es_importe(campo: str) -> bool:
    return campo in CAMPOS_IMPORTE or campo.startswith(("importe_", "cuota"))


# --- Parte 1 · precision decimal (T015) ------------------------------------


def test_decimal_se_serializa_como_cadena_de_4_decimales() -> None:
    assert serializar(Decimal("123.45")) == "123.4500"
    assert serializar(Decimal(-5)) == "-5.0000"
    assert serializar(Decimal(0)) == "0.0000"
    assert serializar(Decimal("1234.5678")) == "1234.5678"
    assert serializar(None) is None


def test_cuatro_decimales_redondea_a_half_even() -> None:
    assert cuatro_decimales(Decimal("1.00005")) == Decimal("1.0000")
    assert cuatro_decimales(Decimal("1.00015")) == Decimal("1.0002")
    assert cuatro_decimales(Decimal("2.00025")) == Decimal("2.0002")


def test_float_de_columna_se_trata_como_decimal() -> None:
    """SQLite guarda NUMERIC como REAL: se cuela un float y aun asi sale cadena."""
    assert serializar(123.45) == "123.4500"
    assert serializar(0.1 + 0.2) == "0.3000"


def test_otros_tipos_se_serializan_correctamente() -> None:
    import uuid
    from datetime import date, datetime, timezone
    from enum import Enum

    class Color(str, Enum):
        rojo = "rojo"

    identificador = uuid.uuid4()
    assert serializar(identificador) == str(identificador)
    assert serializar(date(2026, 9, 27)) == "2026-09-27"
    assert serializar(datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)) == "2026-09-27T12:00:00Z"
    # Un `datetime` naive (como el que devuelve SQLite) se interpreta como UTC.
    assert iso_utc(datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)) == "2026-09-27T12:00:00Z"
    assert serializar(Color.rojo) == "rojo"
    assert serializar(b"abc") == "YWJj"
    assert serializar({"a": Decimal(1)}) == {"a": "1.0000"}
    assert serializar([Decimal(1)]) == ["1.0000"]


def test_volcar_json_es_determinista_y_sin_floats() -> None:
    payload = {"importe": Decimal("1.5"), "n": 3, "b": True, "nulo": None}
    primero = volcar_json(payload)
    segundo = volcar_json(payload)
    assert primero == segundo
    assert primero == b'{"importe":"1.5000","n":3,"b":true,"nulo":null}'
    assert b"1.5" not in primero.replace(b'"1.5000"', b"")


def test_ningun_importe_del_zip_real_es_numero(export_client) -> None:
    """Recorre los 17 bloques del ZIP y comprueba SC-005 + constitucion."""
    respuesta = export_client.exportar()
    assert respuesta.status_code == 201, respuesta.text
    exportacion_id = respuesta.json()["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    )
    revisados = 0
    for ruta, crudo in ficheros.items():
        if not ruta.endswith(".json") or ruta == "manifest.json":
            continue
        for registro in json.loads(crudo.decode("utf-8")).get("registros", []):
            for campo, valor in registro.items():
                if not _es_importe(campo):
                    continue
                revisados += 1
                assert isinstance(valor, str), f"{ruta}.{campo} = {valor!r} no es cadena"
                assert len(valor.split(".")[-1]) == 4, f"{ruta}.{campo} = {valor!r}"
                assert Decimal(valor) == Decimal(valor)  # parseable sin perdida
    assert revisados > 0, "el dataset no contiene ningun importe que revisar"


def test_importes_parseables_sin_perdida(export_client) -> None:
    respuesta = export_client.exportar()
    exportacion_id = respuesta.json()["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    )
    apuntes = json.loads(ficheros["bloques/004_apuntes.json"].decode("utf-8"))
    lineas = [r for r in apuntes["registros"] if Decimal(r["debe"]) > 0]
    assert lineas
    debe = sum(Decimal(r["debe"]) for r in apuntes["registros"])
    haber = sum(Decimal(r["haber"]) for r in apuntes["registros"])
    # constitution I: el libro exportado sigue cuadrando.
    assert debe == haber


# --- Parte 2 · consistencia decimal del bloque SII (T039) -------------------


def test_bloque_sii_cuadra_con_las_facturas(export_client) -> None:
    respuesta = export_client.exportar(tipo="SII")
    assert respuesta.status_code == 201, respuesta.text
    exportacion_id = respuesta.json()["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    )
    emitidas = json.loads(
        ficheros["bloques/datos_sii/facturas_emitidas.json"].decode("utf-8")
    )
    assert emitidas["conteo_registros"] >= 1
    for registro in emitidas["registros"]:
        base = Decimal(registro["BaseImponible"])
        iva = Decimal(registro["CuotaRepercutida"])
        total = Decimal(registro["ImporteTotal"])
        tipo = Decimal(registro["TipoImpositivo"])
        for campo in ("BaseImponible", "CuotaRepercutida", "ImporteTotal"):
            assert len(registro[campo].split(".")[-1]) == 4
        assert len(registro["TipoImpositivo"].split(".")[-1]) == 2
        # Base * Tipo/100 = Cuota, y Base + Cuota = Total (redondeo Decimal).
        assert cuatro_decimales(base * tipo / Decimal(100)) == iva
        assert base + iva == total
        assert registro["EstadoCuadre"] == "CUADRADO"
        assert registro["ClaveRegimen"] == "01"
        assert registro["NIF"]
        assert registro["NombreRazon"]


def test_factura_descuadrada_marca_estado_descuadrado(export_client) -> None:
    """Un total incoherente con base+IVA se reporta como `DESCUADRADO`."""
    import uuid
    from datetime import date
    from decimal import Decimal

    from sqlalchemy import select

    from models.ar.tercero import Tercero
    from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
    from models.invoice.serie_factura import SerieFactura

    async def _op(sesion):
        serie = await sesion.scalar(
            select(SerieFactura).where(SerieFactura.empresa_id == 10)
        )
        tercero = await sesion.scalar(
            select(Tercero).where(Tercero.empresa_id == 10, Tercero.es_cliente.is_(True))
        )
        sesion.add(
            Factura(
                id=uuid.uuid4(),
                empresa_id=10,
                serie_id=serie.id,
                numero=99,
                ejercicio=2025,
                fecha=date(2025, 6, 1),
                tipo=FacturaTipo.VENTA,
                tercero_id=tercero.id,
                importe_base=Decimal("100.0000"),
                importe_iva=Decimal("21.0000"),
                importe_total=Decimal("999.0000"),
                estado=FacturaEstado.emitida,
            )
        )
        await sesion.flush()

    export_client.run(export_client.mutar(_op))
    respuesta = export_client.exportar(tipo="SII")
    exportacion_id = respuesta.json()["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    )
    emitidas = json.loads(
        ficheros["bloques/datos_sii/facturas_emitidas.json"].decode("utf-8")
    )
    descuadradas = [r for r in emitidas["registros"] if r["EstadoCuadre"] == "DESCUADRADO"]
    assert len(descuadradas) == 1
    assert descuadradas[0]["ImporteTotal"] == "999.0000"


@pytest.mark.parametrize(
    ("base", "iva", "recargo", "irpf", "total", "esperado"),
    [
        ("100.0000", "21.0000", "0.0000", "0.0000", "121.0000", True),
        ("100.0000", "21.0000", "5.0000", "15.0000", "111.0000", True),
        ("100.0000", "21.0000", "0.0000", "0.0000", "120.0000", False),
    ],
)
def test_regla_de_cuadre_del_sii(base, iva, recargo, irpf, total, esperado) -> None:
    from services.export.sii import cuadra

    assert (
        cuadra(
            Decimal(base),
            Decimal(iva),
            Decimal(recargo),
            Decimal(irpf),
            Decimal(total),
        )
        is esperado
    )


def test_soporte_de_test_expone_la_ayuda_de_bloques() -> None:
    bloque = soporte.bloque_de_prueba("asientos", "003_asientos.json", [{"id": "a"}])
    assert bloque.bloque.nombre == "asientos"
    assert bloque.bloque.ruta == "bloques/003_asientos.json"
    assert bloque.conteo_registros == 1
    assert bloque.ejercicio_min == 2025
