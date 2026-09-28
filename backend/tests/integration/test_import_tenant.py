"""Importacion con aislamiento multi-empresa (SPEC-025 T032, FR-005/SC-005).

La importacion de A crea su version sin tocar el catalogo de B, y la version
importada en A es invisible (404) para B en detalle, activacion, cuentas y
preview de reclasificacion.
"""

from __future__ import annotations

CSV = (
    "operacion,codigo,nombre,padre_codigo,destino_codigo\n"
    "renombrado,4300,Clientes euros,430,4310\n"
    "alta,4310,Clientes pagos,431,\n"
)


def _importar(ns, codigo: str, empresa_id: int = 10, fecha: str = "2027-01-01"):
    return ns.post(
        "/api/v1/catalogo/importar",
        files={"file": ("c.csv", CSV.encode("utf-8"), "text/csv")},
        data={"codigo_version": codigo, "fecha_inicio": fecha},
        empresa_id=empresa_id,
    )


def test_importaciones_independientes_por_empresa(catalogo_client):
    ns = catalogo_client

    r10 = _importar(ns, "IMP-A", empresa_id=10)
    r20 = _importar(ns, "IMP-B", empresa_id=20)
    assert r10.status_code == 200, r10.text
    assert r20.status_code == 200, r20.text
    assert r10.json()["version_id"] != r20.json()["version_id"]

    listado_10 = ns.get("/api/v1/catalogo/versiones").json()
    assert listado_10["total"] == 2
    assert {v["codigo"] for v in listado_10["items"]} == {"BASE-2025", "IMP-A"}

    listado_20 = ns.get("/api/v1/catalogo/versiones", empresa_id=20).json()
    assert listado_20["total"] == 2
    assert {v["codigo"] for v in listado_20["items"]} == {"BASE-2025", "IMP-B"}


def test_version_importada_invisible_para_otra_empresa(catalogo_client):
    ns = catalogo_client
    ver10 = _importar(ns, "IMP-A2").json()["version_id"]

    detalle = ns.get(f"/api/v1/catalogo/versiones/{ver10}", empresa_id=20)
    assert detalle.status_code == 404
    assert detalle.json()["detail"]["code"] == "version_no_encontrada"

    activar = ns.post(
        f"/api/v1/catalogo/versiones/{ver10}/activar", empresa_id=20
    )
    assert activar.status_code == 404

    cuentas = ns.get(
        "/api/v1/catalogo/cuentas", empresa_id=20, version_id=ver10, q="4300"
    )
    assert cuentas.status_code == 404

    preview = ns.get(
        "/api/v1/catalogo/reclasificar/preview",
        empresa_id=20,
        version_id=ver10,
        ejercicio=2025,
    )
    assert preview.status_code == 404

    confirmar = ns.post(
        "/api/v1/catalogo/reclasificar/confirmar",
        empresa_id=20,
        json={"version_id": ver10, "ejercicio": 2025, "items": None},
    )
    assert confirmar.status_code == 404

    vigente_20 = ns.get(
        "/api/v1/catalogo/vigente", empresa_id=20, fecha="2027-06-01"
    ).json()
    assert vigente_20["version_id"] == ns.tokens["ver20"]


def test_activacion_propia_sin_rollo_ver_ajena(catalogo_client):
    ns = catalogo_client
    ver10 = _importar(ns, "IMP-A3").json()["version_id"]

    activar = ns.post(f"/api/v1/catalogo/versiones/{ver10}/activar")
    assert activar.status_code == 200
    assert activar.json()["estado"] == "vigente"

    vigente = ns.get("/api/v1/catalogo/vigente", fecha="2027-06-01").json()
    assert vigente["version_id"] == ver10
    assert vigente["codigo"] == "IMP-A3"
