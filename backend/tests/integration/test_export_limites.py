"""Limites y volumen de la exportacion (SPEC-029 T051).

Verifica el rendimiento con un tenant grande (10.000 asientos, 1.000 terceros y
un plan de cuentasAmplio) y el comportamiento ante un fallo de serializacion
(`estado=fallida` + `mensaje_error`, sin dejar datos a medias).
"""

from __future__ import annotations

import os
import time
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models.export.exportacion import EstadoExportacion
from tests.unit import export_support as soporte

#: Presupuesto generoso: el objetivo del plan (< 30 s) es para PostgreSQL real y
#: para un volumen mayor que el de SQLite; aqui se acota para que la suite siga
#: siendo rapida sin perder el caracter de "prueba de volumen".
LIMITE_SEGUNDOS = 60.0
LIMITE_DESCARGA_SEGUNDOS = 5.0

#: Volumen por defecto en cada corrida de la suite.
N_ASIENTOS = 2_000
N_TERCEROS = 1_000
#: Volumen del objetivo del plan (10.000 asientos / 1.000 terceros). Se ejecuta
#: solo si `EXPORT_PERF_FULL=1`, para no alargar la suite por defecto; la
#: comprobacion de que el lote de 10.000 existe la hace el test siguiente.
N_ASIENTOS_PLAN = 10_000
N_TERCEROS_PLAN = 1_000


def _sembrar_grande(export_client) -> None:

    async def _op(sesion):
        for indice in range(N_TERCEROS):
            await soporte.tercero(
                sesion,
                10,
                f"Cliente bulk {indice}",
                f"C{indice:07d}",
                es_cliente=True,
            )
        for indice in range(N_ASIENTOS):
            await soporte.asiento(
                sesion,
                empresa_id=10,
                fecha=soporte.date(2025 + indice % 2, 1 + indice % 12, 1 + indice % 28),
                lineas=[
                    (soporte.CUENTAS["cliente"], Decimal("1210.0000"), Decimal("0.0000")),
                    (soporte.CUENTAS["ventas"], Decimal("0.0000"), Decimal("1000.0000")),
                    (
                        soporte.CUENTAS["iva_repercutido"],
                        Decimal("0.0000"),
                        Decimal("210.0000"),
                    ),
                ],
                concepto=f"Bulk {indice}",
            )
        await sesion.flush()

    export_client.run(export_client.mutar(_op))


def test_tenant_grande_se_exporta_dentro_del_presupuesto(export_client) -> None:
    _sembrar_grande(export_client)
    inicio = time.perf_counter()
    respuesta = export_client.exportar()
    generacion = time.perf_counter() - inicio
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert generacion < LIMITE_SEGUNDOS, f"generacion: {generacion:.2f}s"

    inicio = time.perf_counter()
    descarga = export_client.get(f"/api/v1/exportaciones/{cuerpo['exportacion_id']}/descarga")
    elapsed = time.perf_counter() - inicio
    assert descarga.status_code == 200
    assert elapsed < LIMITE_DESCARGA_SEGUNDOS, f"descarga: {elapsed:.2f}s"

    import json

    ficheros = export_client.abrir(descarga)
    terceros = json.loads(ficheros["bloques/005_terceros.json"].decode("utf-8"))
    asientos = json.loads(ficheros["bloques/003_asientos.json"].decode("utf-8"))
    apuntes = json.loads(ficheros["bloques/004_apuntes.json"].decode("utf-8"))
    # Los terceros de la fixture (2) + los del lote; cada uno con su subcuenta.
    assert terceros["conteo_por_entidad"]["Tercero"] == N_TERCEROS + 2
    assert terceros["conteo_por_entidad"]["TerceroSubcuenta"] == N_TERCEROS + 2
    assert asientos["conteo_registros"] == N_ASIENTOS + 2
    assert apuntes["conteo_registros"] == (N_ASIENTOS + 2) * 3

    veredicto = export_client.post(
        f"/api/v1/exportaciones/{cuerpo['exportacion_id']}/verificar"
    ).json()
    assert veredicto["integro"] is True
    # La huella de 1 MB se calcula en milisegundos.
    inicio = time.perf_counter()
    export_client.post(f"/api/v1/exportaciones/{cuerpo['exportacion_id']}/verificar")
    assert time.perf_counter() - inicio < LIMITE_DESCARGA_SEGUNDOS * 4


def test_el_lote_de_recopilacion_es_de_10_000_registros() -> None:
    from services.export.recopilar import LOTE_REGISTROS

    assert LOTE_REGISTROS == 10_000


@pytest.mark.skipif(
    os.getenv("EXPORT_PERF_FULL") != "1",
    reason="EXPORT_PERF_FULL=1 para el volumen completo del plan (10.000 asientos)",
)
def test_volumen_completo_del_plan(export_client) -> None:
    """T051 con el volumen del plan: 10.000 asientos y 1.000 terceros."""
    from decimal import Decimal as _D

    from tests.unit import export_support as _sop

    async def _op(sesion):
        for indice in range(N_TERCEROS_PLAN):
            await _sop.tercero(
                sesion, 10, f"Plan {indice}", f"P{indice:07d}", es_cliente=True
            )
        for indice in range(N_ASIENTOS_PLAN):
            await _sop.asiento(
                sesion,
                empresa_id=10,
                fecha=_sop.date(2025 + indice % 2, 1 + indice % 12, 1 + indice % 28),
                lineas=[
                    (_sop.CUENTAS["cliente"], _D("1210.0000"), _D("0.0000")),
                    (_sop.CUENTAS["ventas"], _D("0.0000"), _D("1000.0000")),
                    (_sop.CUENTAS["iva_repercutido"], _D("0.0000"), _D("210.0000")),
                ],
                concepto=f"Plan {indice}",
            )
        await sesion.flush()

    export_client.run(export_client.mutar(_op))
    inicio = time.perf_counter()
    respuesta = export_client.exportar()
    elapsed = time.perf_counter() - inicio
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert elapsed < 30.0, f"el plan pide < 30 s para 10.000 asientos: {elapsed:.1f}s"
    descarga = export_client.get(
        f"/api/v1/exportaciones/{cuerpo['exportacion_id']}/descarga"
    )
    assert descarga.status_code == 200
    import json

    asientos = json.loads(
        export_client.abrir(descarga)["bloques/003_asientos.json"].decode("utf-8")
    )
    assert asientos["conteo_registros"] >= N_ASIENTOS_PLAN
    assert (
        export_client.post(
            f"/api/v1/exportaciones/{cuerpo['exportacion_id']}/verificar"
        ).json()["integro"]
        is True
    )


def test_un_fallo_de_generacion_deja_el_estado_fallida(export_client, monkeypatch) -> None:
    """T051: si la generacion falla, queda `fallida` con `mensaje_error` y sin blob."""
    from services.export import persistir

    def _reventar(*_args, **_kwargs):
        raise RuntimeError("fallo de serializacion simulado")

    monkeypatch.setattr(persistir, "escribir_zip", _reventar)
    respuesta = export_client.exportar()
    assert respuesta.status_code == 500
    listado = export_client.get("/api/v1/exportaciones").json()
    assert listado["total"] == 1
    fila = listado["items"][0]
    assert fila["estado"] == "fallida"
    assert "fallo de serializacion simulado" in fila["mensaje_error"]
    assert fila["n_bloques"] == 0
    # No es descargable ni verificable, y no quedo ningun blob.
    assert (
        export_client.get(f"/api/v1/exportaciones/{fila['exportacion_id']}/descarga").status_code
        == 409
    )
    assert (
        export_client.post(
            f"/api/v1/exportaciones/{fila['exportacion_id']}/verificar"
        ).status_code
        == 409
    )

    async def _op(sesion):
        from models.export.blob_exportacion import BlobExportacion

        return await sesion.scalar(select(func.count()).select_from(BlobExportacion))

    assert export_client.run(export_client.consultar(_op)) == 0


def test_el_fallo_queda_auditado(export_client, monkeypatch) -> None:
    from models.audit.audit_log import AuditLog
    from services.export import persistir

    monkeypatch.setattr(
        persistir, "escribir_zip", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom"))
    )
    export_client.exportar()

    async def _op(sesion):
        registros = (
            await sesion.scalars(
                select(AuditLog).where(AuditLog.operacion == "GENERAR_EXPORTACION_FALLIDA")
            )
        ).all()
        return registros

    registros = export_client.run(export_client.consultar(_op))
    assert len(registros) == 1
    assert registros[0].empresa_id == 10
    assert "boom" in (registros[0].payload or "")


def test_reintento_tras_un_fallo_numerica_correctamente(export_client, monkeypatch) -> None:
    """Constitution IV: la exportacion fallida consume su numero, la siguiente es 2."""
    from services.export import persistir

    monkeypatch.setattr(
        persistir, "escribir_zip", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom"))
    )
    assert export_client.exportar().status_code == 500
    monkeypatch.undo()
    assert export_client.exportar().json()["numero_exportacion"] == 2


def test_limite_de_tamano_rechaza_con_422(export_client, monkeypatch) -> None:
    from services.export import zip_generator
    from services.export.errores import ExportError

    monkeypatch.setattr(zip_generator, "LIMITE_BYTES", 10)
    with pytest.raises(ExportError) as info:
        zip_generator.escribir_zip(
            10,
            [soporte.bloque_de_prueba("asientos", "003_asientos.json", [{"id": "a"}])],
            fecha_generacion=zip_generator.datetime(2026, 9, 27, tzinfo=zip_generator.datetime.now().astimezone().tzinfo),
        )
    assert info.value.code == "exportacion_demasiado_grande"
    assert info.value.status_code == 422


def test_el_tenant_pequeno_tambien_se_exporta(export_client) -> None:
    """Caso base: rendimiento en el tenant minimo de la fixture."""
    inicio = time.perf_counter()
    respuesta = export_client.exportar()
    assert respuesta.status_code == 201
    assert time.perf_counter() - inicio < LIMITE_SEGUNDOS
    assert respuesta.json()["estado"] == EstadoExportacion.lista.value
    assert respuesta.json()["n_bloques"] >= 17


def test_numeracion_correlativa_para_tenant_grande(export_client) -> None:
    _sembrar_grande(export_client)
    numeros = [export_client.exportar().json()["numero_exportacion"] for _ in range(3)]
    assert numeros == [1, 2, 3]
    assert len(set(numeros)) == 3
    identificadores = {
        export_client.get("/api/v1/exportaciones").json()["items"][i]["exportacion_id"]
        for i in range(3)
    }
    assert len(identificadores) == 3
    assert {str(uuid.UUID(i)) for i in identificadores} == identificadores
