"""Aislamiento multi-tenant del flujo completo (SPEC-025 T043, FR-005/SC-005).

Version, importacion, cuentas, preview y confirm de la empresa A son 404
para B; cada empresa ejecuta su propio flujo de extremo a extremo sin datos
cruzados.
"""

from __future__ import annotations

from datetime import date

BODY = {
    "codigo": "NORMA-2026",
    "fecha_inicio": "2026-01-01",
    "fecha_fin": "2026-12-31",
    "cuentas": [
        {
            "operacion": "alta",
            "codigo": "4310",
            "nombre": "Clientes pagos",
            "padre_codigo": "431",
        },
        {
            "operacion": "renombrado",
            "codigo": "4300",
            "nombre": "Clientes euros",
            "padre_codigo": "430",
            "destino_codigo": "4310",
        },
    ],
}

CSV = (
    "operacion,codigo,nombre,padre_codigo,destino_codigo\n"
    "alta,4312,Clientes anticipos,431,\n"
)


def test_flujo_completo_aislado(catalogo_client):
    ns = catalogo_client

    ver_a = ns.post("/api/v1/catalogo/versiones", json=BODY).json()["id"]
    imp_resp = ns.post(
        "/api/v1/catalogo/importar",
        files={"file": ("c.csv", CSV.encode("utf-8"), "text/csv")},
        data={"codigo_version": "IMP-A", "fecha_inicio": "2027-01-01"},
    )
    assert imp_resp.status_code == 200, imp_resp.text
    imp_a = imp_resp.json()["version_id"]

    ns.asiento(
        10,
        date(2025, 6, 30),
        "Cobro 2025",
        [
            {"account_id": ns.cuenta(10, "4300"), "debit": "7700.0000", "credit": "0"},
            {"account_id": ns.cuenta(10, "1110"), "debit": "0", "credit": "7700.0000"},
        ],
    )
    preview = ns.get(
        "/api/v1/catalogo/reclasificar/preview",
        version_id=ver_a,
        ejercicio=2025,
    )
    assert preview.status_code == 200
    confirm = ns.post(
        "/api/v1/catalogo/reclasificar/confirmar",
        json={"version_id": ver_a, "ejercicio": 2025, "items": None},
    )
    assert confirm.status_code == 200
    assert confirm.json()["reclasificaciones"] == 1

    for ruta, kwargs in (
        (f"/api/v1/catalogo/versiones/{ver_a}", {}),
        (f"/api/v1/catalogo/versiones/{imp_a}", {}),
        (f"/api/v1/catalogo/versiones/{ver_a}/activar", {"metodo": "post"}),
        ("/api/v1/catalogo/cuentas", {"version_id": ver_a, "q": "4300"}),
        ("/api/v1/catalogo/reclasificar/preview", {"version_id": ver_a, "ejercicio": 2025}),
    ):
        if kwargs.pop("metodo", None) == "post":
            r = ns.post(ruta, empresa_id=20, **kwargs)
        else:
            r = ns.get(ruta, empresa_id=20, **kwargs)
        assert r.status_code == 404, (ruta, r.status_code)

    confirm_b = ns.post(
        "/api/v1/catalogo/reclasificar/confirmar",
        empresa_id=20,
        json={"version_id": ver_a, "ejercicio": 2025, "items": None},
    )
    assert confirm_b.status_code == 404

    vigente_b = ns.get(
        "/api/v1/catalogo/vigente", empresa_id=20, fecha="2026-06-01"
    ).json()
    assert vigente_b["version_id"] == ns.tokens["ver20"]


def test_cada_empresa_ejecuta_su_flujo(catalogo_client):
    ns = catalogo_client

    ver_a = ns.post("/api/v1/catalogo/versiones", json=BODY).json()["id"]
    assert ns.post(f"/api/v1/catalogo/versiones/{ver_a}/activar").status_code == 200

    body_b = dict(BODY, codigo="NORMA-2026-B")
    r_b = ns.post(
        "/api/v1/catalogo/versiones", json=body_b, empresa_id=20, token_key="admin"
    )
    assert r_b.status_code == 201
    ver_b = r_b.json()["id"]
    assert ver_b != ver_a
    assert (
        ns.post(
            f"/api/v1/catalogo/versiones/{ver_b}/activar", empresa_id=20
        ).status_code
        == 200
    )

    vigente_a = ns.get("/api/v1/catalogo/vigente", fecha="2026-06-01").json()
    vigente_b = ns.get(
        "/api/v1/catalogo/vigente", empresa_id=20, fecha="2026-06-01"
    ).json()
    assert vigente_a["version_id"] == ver_a
    assert vigente_b["version_id"] == ver_b

    assert (
        ns.get(f"/api/v1/catalogo/versiones/{ver_b}").status_code == 404
    )
    assert (
        ns.get(f"/api/v1/catalogo/versiones/{ver_a}", empresa_id=20).status_code == 404
    )
