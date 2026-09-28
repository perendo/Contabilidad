"""Constitucion aplicada a los documentos adjuntos (SPEC-030, constitution V).

Revisa por AST y por texto el paquete `api/documentos/` y `services/documentos/`
para comprobar los principios que aplican a esta spec. Es la red que detecta una
regresion aunque los tests funcionales pasen.

Dos ficheros quedan fuera de la comprobacion de prefijo y de `Empresa`:
`api/documentos/__init__.py` es el agregador (declara `APIRouter(tags=...)` sin
prefijo y no recibe peticiones), igual que `api/costcenters/__init__.py` de
SPEC-017. El prefijo lo lleva cada sub-router, porque un `include_router` con
prefijo y camino vacios es un error de FastAPI y la ruta del listado global es
exactamente `""`.
"""

from __future__ import annotations

import ast
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
API = RAIZ / "src" / "api" / "documentos"
SERVICIOS = RAIZ / "src" / "services" / "documentos"

#: El agregador: no declara prefijo ni recibe peticiones.
AGREGADOR = API / "__init__.py"

#: Las seis rutas de `contracts/api-contracts.md` seccion 7, con su operacion de
#: RBAC. Si se anade una septima, este test falla: es el aviso de "anade tambien
#: la guarda y el test".
RUTAS_ESPERADAS: dict[tuple[str, str], str] = {
    ("POST", "/asiento/{asiento_id}"): "crear",
    ("GET", "/asiento/{asiento_id}"): "ver",
    ("GET", ""): "ver",
    ("GET", "/{documento_id}"): "ver",
    ("GET", "/{documento_id}/descarga"): "ver",
    ("DELETE", "/{documento_id}"): "baja",
}


def _hojas() -> list[Path]:
    """Ficheros con rutas, sin el agregador."""
    return [p for p in sorted(API.glob("*.py")) if p != AGREGADOR]


def _servicios() -> list[Path]:
    return sorted(SERVICIOS.glob("*.py"))


def _texto() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in _hojas() + _servicios())


def _decoradores(fichero: Path) -> list[tuple[str, str, str]]:
    """`(metodo, camino, operacion_rbac)` de cada ruta declarada en el fichero."""
    import re

    arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    encontradas: list[tuple[str, str, str]] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
            continue
        if nodo.func.attr.lower() not in {"get", "post", "put", "patch", "delete"}:
            continue
        metodo = nodo.func.attr.upper()
        camino = (
            nodo.args[0].value
            if nodo.args and isinstance(nodo.args[0], ast.Constant)
            else ""
        )
        operacion = ""
        for kw in nodo.keywords:
            if kw.arg != "dependencies" or not isinstance(kw.value, ast.List):
                continue
            for elemento in kw.value.elts:
                coincide = re.search(
                    r"require_permission\(\s*['\"](\w+)['\"]\s*,\s*['\"](\w+)['\"]",
                    ast.unparse(elemento),
                )
                if coincide:
                    operacion = coincide.group(2)
        encontradas.append((metodo, camino, operacion))
    return encontradas


# ------------------------------------------- endpoints /api/v1


@pytest.mark.parametrize("fichero", _hojas(), ids=lambda p: p.name)
def test_todo_router_lleva_el_prefijo_versionado(fichero: Path) -> None:
    """Constitution: los endpoints viven bajo `/api/v1/...`."""
    fuente = fichero.read_text(encoding="utf-8")
    if "APIRouter(" not in fuente:
        return
    assert 'prefix="/api/v1/documentos"' in fuente, (
        f"{fichero.name} declara un APIRouter sin el prefijo /api/v1/documentos"
    )


def test_la_superficie_es_exactamente_las_seis_rutas() -> None:
    """contracts seccion 7. El total sale de los decoradores reales, no de un
    numero escrito a mano."""
    encontradas: dict[tuple[str, str], str] = {}
    for fichero in _hojas():
        for metodo, camino, operacion in _decoradores(fichero):
            clave = (metodo, camino)
            assert clave not in encontradas, f"ruta duplicada: {clave}"
            encontradas[clave] = operacion
    assert encontradas == RUTAS_ESPERADAS


def test_ningun_endpoint_acepta_la_empresa_del_cliente() -> None:
    """constitucion III: `empresa_id` se deriva de la sesion, nunca del body,
    la query ni la ruta.

    Solo se revisan las **capas de API**: un servicio recibe `empresa_id: int`
    como argumento porque quien lo llama es el endpoint, y ahi el valor viene
    del alias `Empresa`. Lo que no puede pasar es que lo declare el endpoint."""
    for fichero in _hojas():
        fuente = fichero.read_text(encoding="utf-8")
        assert "empresa_id: int" not in fuente, fichero.name
        assert "empresa_id: str" not in fuente, fichero.name
        assert "empresa_id: Optional" not in fuente, fichero.name


def test_las_rutas_usan_el_alias_Empresa() -> None:
    """Ninguna ruta declara `empresa_id` por su cuenta: todas usan el alias
    `Empresa` de `api/documentos/deps.py`, que es `get_empresa_id`."""
    for fichero in _hojas():
        if fichero.name == "deps.py":
            continue  # aqui es donde se *define* el alias
        fuente = fichero.read_text(encoding="utf-8")
        if "empresa_id" not in fuente:
            continue
        assert "empresa_id: Empresa" in fuente, fichero.name
    deps = (API / "deps.py").read_text(encoding="utf-8")
    assert "Empresa = Annotated[int, Depends(get_empresa_id)]" in deps
    assert "Db = Annotated[AsyncSession, Depends(get_db)]" in deps


def test_ninguna_ruta_declara_el_tenant_en_path_o_body() -> None:
    """`/api/{empresa}/...` es exactamente el antipatron que la constitucion
    prohibe."""
    for fichero in _hojas() + _servicios():
        fuente = fichero.read_text(encoding="utf-8")
        limpio = fuente.replace("X-Empresa-Activa", "")
        assert "/empresa" not in limpio, fichero.name
        assert "/{empresa" not in limpio, fichero.name


# ------------------------------------------------- guards RBAC


def test_cada_ruta_lleva_su_guarda() -> None:
    """SPEC-015 deny-by-default: cada ruta lleva `require_permission` con su
    operacion, y la de lectura es `ver`."""
    for fichero in _hojas():
        for metodo, camino, operacion in _decoradores(fichero):
            assert operacion, f"{fichero.name}: {metodo} {camino} sin guarda"
    conteo: dict[str, int] = {}
    for fichero in _hojas():
        for _, _, operacion in _decoradores(fichero):
            conteo[operacion] = conteo.get(operacion, 0) + 1
    assert conteo == {"ver": 4, "crear": 1, "baja": 1}


def test_crear_y_baja_son_permisos_distintos() -> None:
    """FR-016: un permiso explicito para adjuntar y otro diferenciable para dar
    de baja, ambos existentes en el catalogo de `acct`."""
    from services.security.catalogo import CATALOGO

    assert {"ver", "crear", "baja"} <= set(CATALOGO["acct"])


# ------------------------------------------- precision decimal


def test_ningun_modulo_declara_un_float() -> None:
    """constitucion: prohibido `float` para importes. Se revisa el AST, no el
    texto, para no penalizar un `0.4f` de formato."""
    for fichero in _hojas() + _servicios():
        for nodo in ast.walk(ast.parse(fichero.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Constant) and isinstance(nodo.value, float):
                pytest.fail(
                    f"{fichero.name}:{nodo.lineno} contiene un literal float "
                    f"({nodo.value!r}); los importes van con Decimal"
                )
            if isinstance(nodo, ast.Name) and nodo.id == "float":
                pytest.fail(f"{fichero.name}:{nodo.lineno} referencia el tipo float")


def test_el_importe_informativo_esta_declarado_como_numeric_18_4() -> None:
    from sqlalchemy import Numeric

    from models.acct.documento import DocumentoAsiento

    columna = DocumentoAsiento.__table__.c.importe_informativo
    assert isinstance(columna.type, Numeric)
    assert (columna.type.precision, columna.type.scale) == (18, 4)
    assert columna.nullable is True


def test_el_importe_informativo_viaja_como_string_de_cuatro_decimales() -> None:
    """El importe se formatea a 4 decimales en el serializador compartido."""
    from models.acct.documento import DocumentoAsiento, EstadoDocumento, TipoDocumento
    from services.documentos._serializacion import serializar

    fila = DocumentoAsiento(
        empresa_id=1,
        journal_entry_id=uuid.uuid4(),
        contenido=b"%PDF-1.4",
        sha256="a" * 64,
        nombre_original="f.pdf",
        content_type="application/pdf",
        extension="pdf",
        size_bytes=8,
        num_paginas=1,
        tipo_documento=TipoDocumento.factura,
        # El `default=activo` del modelo se aplica en el `flush`, asi que en una
        # instancia sin flush hay que fijarlo explicitamente.
        estado=EstadoDocumento.activo,
        importe_informativo=Decimal("1210.5"),
    )
    objeto = serializar(fila)
    assert objeto["importe_informativo"] == "1210.5000"
    assert isinstance(objeto["importe_informativo"], str)
    assert objeto["created_at"] == ""


# ------------------------------------------- FR-015 / SC-007


def test_ningun_modulo_escribe_en_el_diario() -> None:
    """FR-015 y SC-007 son garantias estructurales: ningun modulo **importa**
    `journal_entry_line` ni escribe sobre `JournalEntry`.

    Se revisa el AST y no el texto porque los docstrings mencionan ambos
    nombres al explicar justo lo que no se hace."""
    for fichero in _servicios():
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            nombres: list[str] = []
            if isinstance(nodo, ast.ImportFrom):
                nombres = [a.name for a in nodo.names] + [nodo.module or ""]
            elif isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            for nombre in nombres:
                assert "journal_entry_line" not in nombre, (
                    f"{fichero.name}:{nodo.lineno} importa {nombre}"
                )
                assert "JournalEntryLine" not in nombre, (
                    f"{fichero.name}:{nodo.lineno} importa {nombre}"
                )
            if isinstance(nodo, ast.Call):
                llamada = ast.unparse(nodo.func)
                if llamada in ("db.add", "session.add", "db.delete", "session.delete"):
                    assert "JournalEntry" not in ast.unparse(nodo), (
                        f"{fichero.name}:{nodo.lineno} escribe en el diario"
                    )


def test_el_modelo_no_anade_columnas_al_asiento() -> None:
    """research D11: las 19 columnas del data-model y ni una mas."""
    from models.acct.documento import DocumentoAsiento

    esperados = {
        "id",
        "empresa_id",
        "journal_entry_id",
        "contenido",
        "sha256",
        "nombre_original",
        "content_type",
        "extension",
        "size_bytes",
        "num_paginas",
        "tipo_documento",
        "descripcion",
        "importe_informativo",
        "estado",
        "baja_motivo",
        "baja_usuario",
        "baja_at",
        "created_by",
        "created_at",
    }
    columnas = set(DocumentoAsiento.__table__.c.keys())
    assert columnas == esperados, columnas ^ esperados
    assert len(esperados) == 19


# ------------------------------------------- ACID boundary


def test_el_boundary_acid_es_get_db_mas_flush() -> None:
    """Desviacion V1 de plan.md: el boundary es `get_db` + `flush()`, nunca
    `async with session.begin()`.

    Se busca el nodo `AsyncWith` con una llamada a `begin()`, no el texto: los
    docstrings mencionan el patron justamente para explicar que no se usa. Y
    solo los modulos que **escriben** necesitan `flush()`; `consulta.py` es de
    solo lectura y no lo necesita."""
    for fichero in _servicios():
        fuente = fichero.read_text(encoding="utf-8")
        for nodo in ast.walk(ast.parse(fuente)):
            if not isinstance(nodo, ast.AsyncWith):
                continue
            for item in nodo.items:
                if "begin()" in ast.unparse(item.context_expr):
                    pytest.fail(
                        f"{fichero.name}:{nodo.lineno} abre su propia transaccion; "
                        "el boundary del repositorio es get_db + flush()"
                    )
    for nombre in ("adjuntos.py", "bajas.py"):
        fuente = (SERVICIOS / nombre).read_text(encoding="utf-8")
        assert "await session.flush()" in fuente, nombre


def test_las_mutaciones_se_auditan() -> None:
    """FR-011: alta y baja escriben su traza en `audit_log`."""
    from services.documentos.adjuntos import OPERACION_ALTA
    from services.documentos.bajas import OPERACION_BAJA

    assert OPERACION_ALTA == "ADJUNTAR_DOCUMENTO"
    assert OPERACION_BAJA == "DAR_DE_BAJA_DOCUMENTO"
    texto = _texto()
    assert "registrar_auditoria" in texto
    assert 'entidad="documento_asiento"' in texto


# ------------------------------------------- multitenancy


def test_toda_consulta_filtra_por_empresa() -> None:
    """constitucion III sin excepcion: cada lectura de `DocumentoAsiento` esta
    dentro de una sentencia que lleva el filtro por `empresa_id`.

    Se revisa el cuerpo de la **funcion** y no cada llamada suelta, porque el
    filtro llega encadenado en `.where(...)` y esa cadena cae fuera del nodo
    `select(...)`. Se acepta tambien delegar en el helper `_base(empresa_id)`,
    que es la unica forma de construir la base filtrada; se comprueba aparte que
    ese helper filtra de verdad."""
    consulta = (SERVICIOS / "consulta.py").read_text(encoding="utf-8")
    # El helper base filtra por tenant, sin excepcion.
    inicio = consulta.index("def _base(")
    cuerpo_base = consulta[inicio : consulta.index("def ", inicio + 10)]
    assert "DocumentoAsiento.empresa_id == empresa_id" in cuerpo_base

    for fichero in _servicios():
        if "DocumentoAsiento" not in fichero.read_text(encoding="utf-8"):
            continue
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        for funcion in ast.walk(arbol):
            if not isinstance(funcion, ast.AsyncFunctionDef):
                continue
            cuerpo = ast.unparse(funcion)
            if "DocumentoAsiento" not in cuerpo or "select(" not in cuerpo:
                continue
            filtrada = "DocumentoAsiento.empresa_id" in cuerpo
            delegada = "_base(empresa_id)" in cuerpo
            assert filtrada or delegada, (
                f"{fichero.name}:{funcion.lineno} consulta documentos sin filtrar "
                "por empresa_id"
            )


def test_el_404_cross_tenant_no_distingue_del_inexistente() -> None:
    """research D14: mismo texto para "no existe" y "es de otra empresa"."""
    from services.documentos.bajas import NO_EXISTE as NO_EXISTE_BAJA
    from services.documentos.consulta import NO_EXISTE as NO_EXISTE_CONSULTA

    assert NO_EXISTE_BAJA == NO_EXISTE_CONSULTA
    assert NO_EXISTE_CONSULTA == "El documento no existe o pertenece a otra empresa"


def test_el_asiento_inexistente_y_el_ajeno_dicen_lo_mismo() -> None:
    """research D14 aplicado al asiento: 404 indistinguible."""
    fuente = (SERVICIOS / "adjuntos.py").read_text(encoding="utf-8")
    assert fuente.count('"El asiento no existe"') >= 2
    consulta = (SERVICIOS / "consulta.py").read_text(encoding="utf-8")
    assert consulta.count('"El asiento no existe"') >= 1


# ------------------------------------------- FR-020


def test_el_listado_del_asiento_devuelve_vacio_y_no_404() -> None:
    """research D11: `GET /asiento/{id}` devuelve 200 con `items` vacio. El 404 es
    por el asiento, nunca por la ausencia de documentos."""
    fuente = (SERVICIOS / "consulta.py").read_text(encoding="utf-8")
    inicio = fuente.index("async def listar_documentos_asiento")
    # La funcion siguiente se busca por su firma completa, porque el nombre
    # `listar_documentos` es prefijo de este y `index` lo encontraria antes.
    fin = fuente.index("async def listar_documentos(", inicio)
    cuerpo = fuente[inicio:fin]
    assert '"items"' in cuerpo
    assert '"total": len(filas)' in cuerpo
    assert '"documentos_obligatorios": False' in cuerpo


def test_el_registro_no_declara_documentos_obligatorios() -> None:
    """FR-020 en la capa de persistencia: nada en la tabla obliga a tener uno."""
    from models.acct.documento import DocumentoAsiento

    columnas = set(DocumentoAsiento.__table__.c.keys())
    assert not any("obligator" in c for c in columnas)
    assert not any(c.startswith("conteo_documentos") for c in columnas)


# ------------------------------------------- inmutabilidad declarada


def test_el_modelo_declara_las_columnas_congeladas() -> None:
    """research D3: la lista de columnas que el trigger congela es cerrada y
    excluye las cuatro de la baja logica."""
    from models.acct.documento import COLUMNAS_INMUTABLES, DocumentoAsiento

    columnas = set(DocumentoAsiento.__table__.c.keys())
    assert set(COLUMNAS_INMUTABLES) < columnas
    for columna_baja in ("estado", "baja_motivo", "baja_usuario", "baja_at"):
        assert columna_baja not in COLUMNAS_INMUTABLES
    # La evidencia inmutable incluye el contenido, su nombre y su huella.
    for evidencia in ("contenido", "sha256", "nombre_original", "journal_entry_id"):
        assert evidencia in COLUMNAS_INMUTABLES
