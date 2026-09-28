"""Importacion normativa via HTTP (SPEC-025 T031, FR-005/FR-006).

Multipart CSV del escenario esc3 (renombre 4300 -> 4310 + alta 4310),
cuerpo JSON alternativo, errores de fichero/parametros y activacion sin
pendientes.
"""

from __future__ import annotations

CSV_ESC3 = (
    "operacion,codigo,nombre,padre_codigo,destino_codigo\n"
    "renombrado,4300,Clientes euros,430,4310\n"
    "alta,4310,Clientes pagos,431,\n"
)


def _multipart(codigo: str = "PGC-2026-IMP", fecha_inicio: str = "2026-01-01"):
    files = {"file": ("catalogo_2026.csv", CSV_ESC3.encode("utf-8"), "text/csv")}
    data = {"codigo_version": codigo, "fecha_inicio": fecha_inicio}
    return files, data


def test_import_csv_esc3_y_activacion(catalogo_client):
    ns = catalogo_client
    files, data = _multipart()
    r = ns.post("/api/v1/catalogo/importar", files=files, data=data)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["nuevas"] == 1
    assert res["renombradas"] == 1
    assert res["suprimidas"] == 0
    assert res["mapeos"] == 1
    assert res["pendientes_mapeo"] == []

    version_id = res["version_id"]
    detalle = ns.get(f"/api/v1/catalogo/versiones/{version_id}").json()
    assert detalle["codigo"] == "PGC-2026-IMP"
    assert detalle["estado"] == "borrador"
    por_codigo = {c["codigo_version"]: c for c in detalle["cuentas"]}
    assert por_codigo["4310"]["estado"] == "nueva"
    assert por_codigo["4300"]["estado"] == "renombrada"
    renombre = next(m for m in detalle["mapeos"] if m["tipo_movimiento"] == "renombrada")
    assert renombre["cuenta_destino_id"] == por_codigo["4310"]["id"]
    base = ns.get(f"/api/v1/catalogo/versiones/{ns.tokens['ver10']}").json()
    por_base = {c["codigo_version"]: c["id"] for c in base["cuentas"]}
    assert renombre["cuenta_origen_id"] == por_base["4300"]
    assert renombre["requiere_reclasificacion"] is True

    activar = ns.post(f"/api/v1/catalogo/versiones/{version_id}/activar")
    assert activar.status_code == 200
    assert activar.json()["estado"] == "vigente"


def test_import_json_body(catalogo_client):
    ns = catalogo_client
    r = ns.post(
        "/api/v1/catalogo/importar",
        json={
            "codigo_version": "PGC-JSON",
            "fecha_inicio": "2027-01-01",
            "fecha_fin": None,
            "operaciones": [
                {
                    "operacion": "alta",
                    "codigo": "4315",
                    "nombre": "Clientes varios",
                    "padre_codigo": "431",
                    "destino_codigo": None,
                }
            ],
            "mapeo": [],
        },
    )
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["nuevas"] == 1
    assert res["suprimidas"] == 0
    assert res["pendientes_mapeo"] == []
    detalle = ns.get(f"/api/v1/catalogo/versiones/{res['version_id']}").json()
    assert any(c["codigo_version"] == "4315" for c in detalle["cuentas"])


def test_import_faltan_parametros_422(catalogo_client):
    ns = catalogo_client

    sin_fichero = ns.post(
        "/api/v1/catalogo/importar",
        files={"otro": ("nota.txt", b"pepe", "text/plain")},
        data={"codigo_version": "X", "fecha_inicio": "2026-01-01"},
    )
    assert sin_fichero.status_code == 422
    assert sin_fichero.json()["detail"]["code"] == "fichero_invalido"

    files, data = _multipart()
    del data["fecha_inicio"]
    sin_fecha = ns.post("/api/v1/catalogo/importar", files=files, data=data)
    assert sin_fecha.status_code == 422
    assert sin_fecha.json()["detail"]["code"] == "parametro_invalido"

    malo = ns.post(
        "/api/v1/catalogo/importar",
        json={
            "codigo_version": "Y",
            "fecha_inicio": "2026-01-01",
            "operaciones": [
                {
                    "operacion": "inventado",
                    "codigo": "1234",
                    "nombre": "x",
                    "padre_codigo": "12",
                    "destino_codigo": None,
                }
            ],
            "mapeo": [],
        },
    )
    assert malo.status_code == 422


def test_import_csv_invalido_422(catalogo_client):
    ns = catalogo_client

    vacio = ns.post(
        "/api/v1/catalogo/importar",
        files={"file": ("vacio.csv", b"", "text/csv")},
        data={"codigo_version": "Z", "fecha_inicio": "2026-01-01"},
    )
    assert vacio.status_code == 422

    fila_mala = ns.post(
        "/api/v1/catalogo/importar",
        files={
            "file": (
                "malo.csv",
                (
                    b"operacion,codigo,nombre,padre_codigo,destino_codigo\n"
                    b"inventado,9999,Cuenta,0,\n"
                ),
                "text/csv",
            )
        },
        data={"codigo_version": "Z2", "fecha_inicio": "2026-01-01"},
    )
    assert fila_mala.status_code == 422
