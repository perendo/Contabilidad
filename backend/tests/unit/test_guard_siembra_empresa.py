"""Guard de la siembra de empresas en tests (trabajo transversal, AGENTS §47).

Por que existe: `db.add(Company(...))` + `seed_default_pgc` estaba repetido en
mas de cien sitios y se duplicaba con cada spec nueva. Este test es lo que hace
que `tests/conftest.py` sea el **unico** camino: si alguien construye un
`Company` fuera de la lista de mas abajo, falla aqui y no en un test futuro que
se pregunte por cuentas que no existen.

Es una **cremalla**, no un muro: `PENDIENTES` es la lista de ficheros que aun
lo hacen a mano, y su unico proposito es que no pueda crecer. Cada vez que se
migre un fichero, se borra su linea y el test se vuelve mas estricto. Un dia la
lista estara vacia.

Excepciones permanentes:

- `conftest.py`: define el helper y consulta empresas ya sembradas.
- `test_pg_schema.py`: contrato PostgreSQL, habla con la BD por SQL crudo.

Como la migracion fue mecanica y verificada por la suite completa, la lista
residual se acepto de forma explicita en vez de reescribir 67 ficheros a mano:
cada uno tiene su propia forma y el beneficio marginal no compensaba el riesgo.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TESTS = RAIZ / "tests"
CONFTEST = TESTS / "conftest.py"

#: Ficheros que aun construyen `Company` a mano. **Solo puede encogerse.**
PENDIENTES: frozenset[str] = frozenset(
    {
        "integration/test_alta_aislamiento.py",
        "integration/test_alta_triggers.py",
        "integration/test_arbol_aislamiento.py",
        "integration/test_budget_tenant_isolation.py",
        "integration/test_cierre_aislamiento.py",
        "integration/test_cierre_atomico.py",
        "integration/test_conciliacion_http.py",
        "integration/test_editar_aislamiento.py",
        "integration/test_informes_full_tenant_isolation.py",
        "integration/test_invoice_aislamiento.py",
        "integration/test_journal_tenant_isolation.py",
        "integration/test_pgc_cross_tenant_full.py",
        "integration/test_pgc_tenant_isolation.py",
        "integration/test_quickstart_informes.py",
        "integration/test_quickstart_pgc.py",
        "integration/test_quickstart_rbac.py",
        "integration/test_rbac_full_tenant_isolation.py",
        "integration/test_suggest_aislamiento.py",
        "integration/test_suggest_perf.py",
        "integration/test_template_tenant_isolation.py",
        "integration/test_tercero_amend_routes.py",
        "integration/test_tercero_tenant_isolation.py",
        "integration/test_terceros_full_tenant_isolation.py",
        "integration/test_trial_balance_aislamiento.py",
        "integration/test_vencimiento_tenant.py",
        "unit/anticipo_support.py",
        "unit/budget_support.py",
        "unit/cashflow_support.py",
        "unit/closing_support.py",
        "unit/test_account_plan_model.py",
        "unit/test_alta_rechazos.py",
        "unit/test_alta_subcuenta.py",
        "unit/test_alta_tercero.py",
        "unit/test_anticipo_models.py",
        "unit/test_arbol_jerarquia.py",
        "unit/test_budget_models.py",
        "unit/test_cierre_balance.py",
        "unit/test_cobros_pagos.py",
        "unit/test_conciliacion_models.py",
        "unit/test_condiciones_pronto_pago.py",
        "unit/test_constitucion_importexport.py",
        "unit/test_constitucion_informes.py",
        "unit/test_constitucion_pgc.py",
        "unit/test_constitucion_templates.py",
        "unit/test_editar_cuenta.py",
        "unit/test_exportar.py",
        "unit/test_generacion_balance.py",
        "unit/test_generacion_cuenta_plan.py",
        "unit/test_generacion_variables.py",
        "unit/test_importar.py",
        "unit/test_invoice_precision.py",
        "unit/test_is_models.py",
        "unit/test_ledger_saldo_acumulado.py",
        "unit/test_plantilla_alta.py",
        "unit/test_plantilla_edicion_inmutable.py",
        "unit/test_plantilla_estado.py",
        "unit/test_plantilla_lineas.py",
        "unit/test_previsualizacion.py",
        "unit/test_proteccion_cuenta_movimiento.py",
        "unit/test_rbac_models.py",
        "unit/test_retenciones_models.py",
        "unit/test_retirada.py",
        "unit/test_saldo_derivado.py",
        "unit/test_suggest_apuntables.py",
        "unit/test_switch_company.py",
        "unit/test_template_models.py",
        "unit/test_trial_balance_cuadre.py",
    }
)

#: Ficheros que SI pueden construir `Company` a mano.
PERMITIDOS = {
    CONFTEST,  # define el helper y consulta empresas ya sembradas
    TESTS / "integration" / "test_pg_schema.py",  # SQL crudo, no ORM
    Path(__file__).resolve(),  # este mismo fichero
}

RE_CONSTRUCCION = re.compile(r"(?<![\w.])Company\(")


def _ficheros_con_company() -> dict[str, int]:
    encontrados: dict[str, int] = {}
    for p in sorted(TESTS.rglob("*.py")):
        if p in PERMITIDOS:
            continue
        n = len(RE_CONSTRUCCION.findall(p.read_text(encoding="utf-8")))
        if n:
            encontrados[p.relative_to(TESTS).as_posix()] = n
    return encontrados


def test_no_aparece_ningun_company_nuevo_a_mano() -> None:
    """La lista de pendientes solo puede encogerse: si sale un `Company(` fuera
    de ella, el helper vuelve a ser opcional y se rompe la garantia."""
    reales = _ficheros_con_company()
    nuevos = set(reales) - PENDIENTES
    assert not nuevos, (
        f"Construye la empresa con `crear_empresa` / `sembrar_empresa_pgc` de "
        f"conftest: {sorted(nuevos)}"
    )


def test_la_lista_de_pendientes_no_tiene_ficheros_inventados() -> None:
    """La lista no debe nombrar ficheros que ya no existen o que ya se migraron:
    una lista que miente deja de ser una cremalla."""
    reales = _ficheros_con_company()
    obsoletos = PENDIENTES - set(reales)
    assert not obsoletos, (
        f"Ficheros en PENDIENTES que ya no construyen Company: {sorted(obsoletos)}; "
        "borralos de la lista para que el guard sea mas estricto"
    )


def test_el_helper_cubre_las_cuatro_formas() -> None:
    """La firma del helper es la que leen los transformadores y la documentacion,
    asi que cambiarla tiene que romper este test a proposito."""
    arbol = ast.parse(CONFTEST.read_text(encoding="utf-8"))
    esperadas = {
        "crear_empresa": {"db", "empresa_id", "nif", "razon_social", "is_active"},
        "sembrar_empresa_pgc": {
            "db",
            "empresa_id",
            "nif",
            "razon_social",
            "is_active",
        },
        "crear_empresas": {
            "db",
            "empresa_ids",
            "nifs",
            "razones_sociales",
            "inactivos",
        },
        "sembrar_empresas_pgc": {
            "db",
            "empresa_ids",
            "nifs",
            "razones_sociales",
            "inactivos",
        },
    }
    encontradas: dict[str, set[str]] = {}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.AsyncFunctionDef) and nodo.name in esperadas:
            argumentos = {a.arg for a in nodo.args.args} | {
                a.arg for a in nodo.args.kwonlyargs
            }
            # `*empresa_ids` no aparece en `args`, viene en `vararg`.
            if nodo.args.vararg is not None:
                argumentos.add(nodo.args.vararg.arg)
            encontradas[nodo.name] = argumentos
    assert set(encontradas) == set(esperadas), (
        f"faltan helpers en conftest: {set(esperadas) - set(encontradas)}"
    )
    for nombre, esperados in esperadas.items():
        assert encontradas[nombre] == esperados, (
            f"{nombre} cambio de firma: {encontradas[nombre]} != {esperados}"
        )


def _cuerpo_crear_empresa() -> str:
    """El cuerpo del helper **sin docstring**.

    El docstring menciona `commit` al explicar por que el helper no hace commit,
    y contarlo seria un falso positivo. Se extrae con `ast` en vez de con indices
    de texto para no depender del formato.
    """
    texto = CONFTEST.read_text(encoding="utf-8")
    nodo = next(
        n
        for n in ast.walk(ast.parse(texto))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "crear_empresa"
    )
    cuerpo = list(nodo.body)
    if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(cuerpo[0].value, ast.Constant):
        cuerpo = cuerpo[1:]
    return ast.unparse(ast.Module(body=cuerpo, type_ignores=[]))


def test_el_nif_y_la_razon_social_se_derivan_del_id() -> None:
    """Los valores por defecto dependen de `empresa_id`, no de una constante.

    Es lo que hace que dos empresas sembradas en el mismo test no colisionen, y
    lo que evita que cada sitio invente sus propias etiquetas. La comprobacion
    es agnostica al estilo de comillas porque el cuerpo viene de `ast.unparse`,
    que las normaliza a simples simples."""
    cuerpo = _cuerpo_crear_empresa()
    plano = cuerpo.replace('"', "'")
    assert "f'T{empresa_id:08d}'" in plano
    assert "f'E{empresa_id} SL'" in plano


def test_crear_empresa_hace_flush_y_no_commit() -> None:
    """El `flush` es imprescindible —el trigger del catalogo RBAC y las FKs del
    plan de cuentas necesitan ver la fila— y el `commit` no lo puede hacer el
    helper: pertenece a quien llama."""
    cuerpo = _cuerpo_crear_empresa()
    assert "await db.flush()" in cuerpo
    assert "commit()" not in cuerpo


def test_crear_empresas_no_siembra_el_pgc() -> None:
    """`crear_empresas` existe para los tests que plantan su propio plan.

    Si sembrara el PGC estandar, `seed_default_pgc` y `_plantar_pgc` chocarían
    con `UNIQUE (tenant_id, code)`, que es el bug que la separacion evita."""
    texto = CONFTEST.read_text(encoding="utf-8")
    cuerpo = texto[texto.index("async def crear_empresas(") :]
    cuerpo = cuerpo[: cuerpo.index("async def sembrar_empresas_pgc(")]
    assert "seed_default_pgc" not in cuerpo
    assert "await crear_empresa(" in cuerpo
