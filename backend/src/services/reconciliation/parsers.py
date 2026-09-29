"""Parser de extractos bancarios (SPEC-013).

Formatos admitidos: norma 43/19 (ancho fijo), CSV normalizado y XLSX de banco
(hoja de calculo). Servicio puro sin estado: devuelve un `ExtractoDTO` validado.

Los importes se construyen como `Decimal` a partir de cadenas o de enteros, nunca
aritmetica en `float`. El XLSX es el unico formato cuyas celdas llegan ya como
`float` (las escribe el banco), y ahi el paso a `Decimal` pasa por `str()`: es la
cadena decimal mas corta que vuelve al mismo `float`, que para importes en euros
es exactamente el importe del banco. La justificacion larga esta en
`importe_de_celda`.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from services.reconciliation.layouts import (
    CODIGO_CONTROL,
    CODIGOS_CABECERA,
    CODIGOS_CREDITO,
    CODIGOS_DEBITO,
    COLUMNAS_XLSX_OBLIGATORIAS,
    FILAS_BUSQUEDA_CABECERA,
    LAYOUT_NORMA_43,
    LONGITUD_LINEA,
)

CABECERAS_CSV = ("numero", "fecha_operacion", "fecha_valor", "concepto", "importe", "signo")

#: Escala de dinero de la aplicacion (`NUMERIC(18,4)`, constitucion: regla fiscal).
ESCALA_IMPORTE = Decimal("0.0001")


class LayoutError(Exception):
    def __init__(self, code: str, registro: int, campo: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.registro = registro
        self.campo = campo


@dataclass
class MovimientoDTO:
    orden: int
    fecha_operacion: date
    fecha_valor: date | None
    concepto: str
    importe: Decimal
    signo: str
    referencia: str | None


@dataclass
class ExtractoDTO:
    cuenta: str
    fecha_inicio: date
    fecha_fin: date
    saldo_inicial: Decimal
    saldo_final: Decimal
    movimientos: list[MovimientoDTO] = field(default_factory=list)
    #: IBAN que declara el propio extracto, cuando el formato lo trae. NO es un
    #: codigo del plan de cuentas: un XLSX de banco identifica la cuenta con un
    #: IBAN, y `importacion.py` sigue exigiendo que el usuario diga a que cuenta
    #: 572 corresponde. Se conserva para que el usuario pueda confirmar que ha
    #: subido el extracto del banco y de la cuenta que cree.
    iban: str | None = None


def _dec_campo(valor: str, registro: int, campo: str) -> Decimal:
    texto = (valor or "").strip()
    if not texto:
        return Decimal("0.0000")
    if not texto.isdigit():
        raise LayoutError("layout_invalido", registro, campo, f"{campo} no numérico")
    if len(texto) <= 4:
        texto = texto.zfill(4)
    return Decimal(f"{texto[:-4] or '0'}.{texto[-4:]}")


def _fecha(valor: str, registro: int, campo: str) -> date:
    texto = (valor or "").strip()
    try:
        return date(int(texto[0:4]), int(texto[4:6]), int(texto[6:8]))
    except (ValueError, IndexError) as exc:
        raise LayoutError("layout_invalido", registro, campo, f"{campo} inválida: {valor}") from exc


def parse_norma_43(file_bytes: bytes) -> ExtractoDTO:
    """Parse a fixed-width norma 43/19 extract (ISO-8859-1)."""
    texto = file_bytes.decode("iso-8859-1")
    lineas = [ln for ln in texto.splitlines() if ln.strip()]
    if not lineas:
        raise LayoutError("layout_invalido", 0, "fichero", "El fichero está vacío")

    cabecera_cuenta: str | None = None
    fecha_inicio: date | None = None
    saldo_inicial: Decimal | None = None
    saldo_final: Decimal | None = None
    movimientos: list[MovimientoDTO] = []
    control: dict[str, int | Decimal] | None = None
    for i, linea in enumerate(lineas, start=1):
        if len(linea) != LONGITUD_LINEA:
            raise LayoutError(
                "layout_invalido", i, "longitud",
                f"Línea {i}: longitud {len(linea)} != {LONGITUD_LINEA}",
            )
        codigo = linea[0:2]
        if codigo in CODIGOS_CABECERA:
            off = LAYOUT_NORMA_43.cabecera
            cabecera_cuenta = linea[off["cuenta"][0]:off["cuenta"][1]].strip()
            fecha_inicio = _fecha(linea[off["fecha_datos"][0]:off["fecha_datos"][1]], i, "fecha_datos")
            saldo_inicial = _dec_campo(linea[off["saldo_inicial"][0]:off["saldo_inicial"][1]], i, "saldo_inicial")
            saldo_final = _dec_campo(linea[off["saldo_final"][0]:off["saldo_final"][1]], i, "saldo_final")
        elif codigo in CODIGOS_DEBITO or codigo in CODIGOS_CREDITO:
            off = LAYOUT_NORMA_43.operacion
            movimientos.append(
                MovimientoDTO(
                    orden=len(movimientos) + 1,
                    fecha_operacion=_fecha(linea[off["fecha_operacion"][0]:off["fecha_operacion"][1]], i, "fecha_operacion"),
                    fecha_valor=_fecha(linea[off["fecha_valor"][0]:off["fecha_valor"][1]], i, "fecha_valor"),
                    concepto=linea[off["concepto"][0]:off["concepto"][1]].strip(),
                    importe=_dec_campo(linea[off["importe"][0]:off["importe"][1]], i, "importe"),
                    signo="D" if codigo in CODIGOS_DEBITO else "H",
                    referencia=linea[off["referencia"][0]:off["referencia"][1]].strip() or None,
                )
            )
        elif codigo == CODIGO_CONTROL:
            off = LAYOUT_NORMA_43.control
            control = {
                "n_operaciones": int(linea[off["n_operaciones"][0]:off["n_operaciones"][1]] or "0"),
                "suma": _dec_campo(linea[off["suma"][0]:off["suma"][1]], i, "suma"),
            }
        else:
            raise LayoutError("layout_invalido", i, "codigo", f"Registro {i}: código desconocido {codigo}")

    if cabecera_cuenta is None or fecha_inicio is None or saldo_inicial is None or saldo_final is None:
        raise LayoutError("layout_invalido", 0, "cabecera", "Falta el registro de cabecera 01")
    if control is None:
        raise LayoutError("layout_invalido", 0, "control", "Falta el registro de control 98")
    if len(movimientos) < 1:
        raise LayoutError("layout_invalido", 0, "movimientos", "El extracto no tiene movimientos")
    if control["n_operaciones"] != len(movimientos):
        raise LayoutError(
            "layout_invalido", 0, "control",
            f"Control declara {control['n_operaciones']} movimientos, leídos {len(movimientos)}",
        )
    suma_abs = sum((m.importe for m in movimientos), Decimal(0))
    if suma_abs != control["suma"]:
        raise LayoutError("layout_invalido", 0, "cuadre", f"Suma control {control['suma']} != {suma_abs}")

    neto = sum(
        (m.importe if m.signo == "H" else -m.importe for m in movimientos), Decimal(0)
    )
    diff = saldo_final - saldo_inicial
    if neto != diff:
        raise LayoutError(
            "layout_invalido", 0, "cuadre",
            f"Σ movimientos {neto} != saldo_final − saldo_inicial {diff}",
        )

    return ExtractoDTO(
        cuenta=cabecera_cuenta,
        fecha_inicio=fecha_inicio,
        fecha_fin=max((m.fecha_operacion for m in movimientos), default=fecha_inicio),
        saldo_inicial=saldo_inicial,
        saldo_final=saldo_final,
        movimientos=movimientos,
    )


def parse_csv_normalizado(file_bytes: bytes) -> ExtractoDTO:
    """Parse the normalized CSV variant (UTF-8, ';')."""
    texto = file_bytes.decode("utf-8-sig")
    lector = csv.DictReader(io.StringIO(texto), delimiter=";")
    if lector.fieldnames is None or any(c not in lector.fieldnames for c in CABECERAS_CSV):
        raise LayoutError("layout_invalido", 1, "cabecera", "Faltan columnas del CSV normalizado")
    movimientos: list[MovimientoDTO] = []
    totales: Decimal | None = None
    for i, fila in enumerate(lector, start=2):
        numero = (fila.get("numero") or "").strip()
        if numero == "0":
            totales = _dec_campo((fila.get("importe") or "").replace(".", "").replace(",", ""), i, "importe")
            continue
        signo = (fila.get("signo") or "").strip().upper()
        if signo not in ("D", "H"):
            raise LayoutError("layout_invalido", i, "signo", f"Signo inválido: {signo}")
        try:
            importe = Decimal((fila.get("importe") or "").strip())
        except InvalidOperation as exc:
            raise LayoutError("layout_invalido", i, "importe", "Importe inválido") from exc
        if importe <= 0:
            raise LayoutError("layout_invalido", i, "importe", "El importe debe ser > 0")
        movimientos.append(
            MovimientoDTO(
                orden=len(movimientos) + 1,
                fecha_operacion=date.fromisoformat((fila.get("fecha_operacion") or "").strip()),
                fecha_valor=(
                    date.fromisoformat((fila.get("fecha_valor") or "").strip())
                    if (fila.get("fecha_valor") or "").strip()
                    else None
                ),
                concepto=(fila.get("concepto") or "").strip(),
                importe=importe,
                signo=signo,
                referencia=(fila.get("referencia") or "").strip() or None,
            )
        )
    if not movimientos:
        raise LayoutError("layout_invalido", 0, "movimientos", "El CSV no tiene movimientos")
    neto = sum((m.importe if m.signo == "H" else -m.importe for m in movimientos), Decimal(0))
    if totales is not None and neto != totales:
        raise LayoutError("layout_invalido", 0, "cuadre", f"CSV: {neto} != totales {totales}")
    saldo_inicial = Decimal("0.0000")
    saldo_final = neto
    return ExtractoDTO(
        cuenta="",
        fecha_inicio=min(m.fecha_operacion for m in movimientos),
        fecha_fin=max(m.fecha_operacion for m in movimientos),
        saldo_inicial=saldo_inicial,
        saldo_final=saldo_final,
        movimientos=movimientos,
    )


def parse_extracto(file_bytes: bytes, layout: str) -> ExtractoDTO:
    """Despacha al parser del formato pedido.

    Un `layout` desconocido es un **error**, no un "usa norma 43 por defecto". Con
    el despacho silencioso, un `layout` mal escrito (un typo, un valor vacio, un
    `xlsx` en vez de `xlsx_bancario`) acababa en el parser de ancho fijo y
    respondia "linea 1: longitud 22 != 100", que no dice nada del problema real.
    """
    if layout == "norma_43_1919":
        return parse_norma_43(file_bytes)
    if layout == "csv_normalizado":
        return parse_csv_normalizado(file_bytes)
    if layout == "xlsx_bancario":
        return parse_xlsx_bancario(file_bytes)
    raise LayoutError(
        "layout_desconocido", 0, "layout", f"Formato no soportado: {layout or '(vacio)'}"
    )


# ---------------------------------------------------------------------------
# XLSX de banco
# ---------------------------------------------------------------------------


def normalizar_columna(valor: object) -> str:
    """Clave de comparacion de una cabecera: sin acentos, sin espacios, minuscula.

    El banco escribe `Fecha Operacion` con tilde y el XLSX guarda la cadena tal
    cual, asi que comparar literalmente dejaria fuera el fichero del banco en
    cuanto una tilde se descoloca. Se quitan los diacriticos con NFKD, que es lo
    que hace que `Operación` y `Operacion` den la misma clave.
    """
    texto = "" if valor is None else str(valor)
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_marcas = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return "".join(c for c in sin_marcas.lower() if c.isalnum())


def _celda(fila: tuple[object, ...], indice: int) -> object:
    """Valor de una columna por indice, tolerante a filas cortas."""
    if indice is None or indice < 0 or indice >= len(fila):
        return None
    return fila[indice]


def importe_de_celda(valor: object, registro: int, campo: str) -> Decimal:
    """Convierte una celda de importe a `Decimal` con 4 decimales.

    Por que `str()` y no el `float` directamente: `Decimal(5281.99)` es el valor
    binario exacto, `5281.989999999999781721...`, no el importe del banco.
    `Decimal(str(5281.99))` si lo es, porque `str` de un flotante devuelve la
    cadena decimal mas corta que vuelve a ese mismo flotante. Para importes en
    euros (que no llegan a 15 cifras significativas) las dos coinciden, y el
    cuantizado a 4 decimales es el importe del extracto. Es el mismo criterio que
    aplica `importexport.parseador.parse_decimal` al otro lado del proyecto.

    Los enteros y las cadenas se toman tal cual, que es el camino exacto.
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return Decimal("0.0000")
    if isinstance(valor, bool):
        raise LayoutError("layout_invalido", registro, campo, f"{campo} no es un importe")
    if isinstance(valor, int):
        return (Decimal(valor)).quantize(ESCALA_IMPORTE)
    if isinstance(valor, float):
        return Decimal(str(valor)).quantize(ESCALA_IMPORTE)
    if isinstance(valor, Decimal):
        return valor.quantize(ESCALA_IMPORTE)
    texto = str(valor).strip().replace("EUR", "").replace("€", "").strip()
    # La banca española escribe miles con punto y decimales con coma.
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        return Decimal(texto).quantize(ESCALA_IMPORTE)
    except InvalidOperation as exc:
        raise LayoutError("layout_invalido", registro, campo, f"{campo} no numerico: {valor!r}") from exc


def _fecha_xlsx(valor: object, registro: int, campo: str) -> date | None:
    """Fecha de una celda del XLSX.

    Acepta las tres formas que se han visto en extractos de banco: la celda como
    fecha real de Excel, el texto `DD/MM/AAAA` que es como lo escribe Santander, y
    el ISO `AAAA-MM-DD` de exportaciones propias. Las tres son inequivocas: los
    dos primeros separan el dia del ano en 2 digitos, el ISO en 4.
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for patron, orden in (
        (r"^(\d{4})-(\d{2})-(\d{2})", (1, 2, 3)),
        (r"^(\d{1,2})/(\d{1,2})/(\d{4})", (3, 2, 1)),
        (r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", (3, 2, 1)),
        (r"^(\d{1,2})-(\d{1,2})-(\d{4})", (3, 2, 1)),
    ):
        encaje = re.match(patron, texto)
        if encaje:
            try:
                return date(*(int(encaje.group(i)) for i in orden))
            except ValueError as exc:
                raise LayoutError(
                    "layout_invalido", registro, campo, f"{campo} invalida: {texto}"
                ) from exc
    raise LayoutError("layout_invalido", registro, campo, f"{campo} invalida: {texto}")


def _divisa_eur(valor: object, registro: int) -> None:
    """Rechaza un extracto que no este en euros, en vez de importarlo como si lo estuviera.

    El extracto no lleva tipo de cambio (SPEC-013 no lo contempla) asi que un
    extracto en dolares importado tal cual seria un extracto **falso** con
    cifras equivocadas y un saldo que no cuadra con el banco. Es peor que no
    importarlo, asi que se dice explicitamente.
    """
    texto = str(valor or "").strip().upper()
    if texto and texto != "EUR":
        raise LayoutError(
            "divisa_no_soportada",
            registro,
            "divisa",
            f"El extracto esta en {texto} y la importacion solo admite EUR",
        )


def _referencia_xlsx(
    fila: tuple[object, ...], columnas: dict[str, int]
) -> str | None:
    """Mejor referencia disponible: numero de documento, referencias o codigo.

    Las columnas `Referencia 1` y `Referencia 2` del XLSX del banco vienen
    rellenas a ancho fijo con espacios de relleno, asi que se quitan antes de
    mirar si hay algo. Se cortan a 80 porque es la anchura de la columna.
    """
    for clave in ("numerodedocumento", "referencia1", "referencia2", "codigo"):
        indice = columnas.get(clave)
        if indice is None:
            continue
        valor = _celda(fila, indice)
        if valor is None:
            continue
        texto = str(int(valor)) if isinstance(valor, float) and valor.is_integer() else str(valor)
        texto = texto.strip()
        if texto:
            return texto[:80]
    return None


def _buscar_cabecera(
    filas: list[tuple[object, ...]],
) -> tuple[int, dict[str, int]]:
    """Fila de cabecera e indice de cada columna, o `LayoutError` si no esta.

    Devolver el indice y no solo un booleano es lo que permite absorber las
    columnas sobrantes (`Informacion adicional` y las dos `Divisa`) sin que el
    parser tenga que saber cuantas hay ni en que orden. Cuando una clave se
    repite gana la **primera** aparecida: el XLSX del banco repite `Divisa` (la
    del importe y la del saldo) y la primera es la que manda.
    """
    for numero, fila in enumerate(filas[:FILAS_BUSQUEDA_CABECERA], start=1):
        claves = {normalizar_columna(c) for c in fila}
        if all(obligatoria in claves for obligatoria in COLUMNAS_XLSX_OBLIGATORIAS):
            columnas: dict[str, int] = {}
            for indice, celda in enumerate(fila):
                clave = normalizar_columna(celda)
                if clave and clave not in columnas:
                    columnas[clave] = indice
            return numero, columnas
    raise LayoutError(
        "layout_invalido",
        1,
        "cabecera",
        "No se encuentra la cabecera del extracto: se requieren las columnas "
        + ", ".join(COLUMNAS_XLSX_OBLIGATORIAS),
    )


def _iban_de_la_hoja(filas: list[tuple[object, ...]]) -> str | None:
    """IBAN del bloque de metadatos, si el fichero lo trae.

    Se busca en las filas **anteriores** a la cabecera, que es donde el banco
    pone los datos de la cuenta. Un IBAN español es `ES` + 22 digitos.
    """
    for fila in filas[:FILAS_BUSQUEDA_CABECERA]:
        for celda in fila:
            texto = re.sub(r"[\s-]", "", str(celda or "")).upper()
            if re.fullmatch(r"ES\d{22}", texto):
                return texto
    return None


def _saldo_final_desde_cadena(
    saldos: list[Decimal], importes: list[Decimal], registro_de: int
) -> tuple[Decimal, Decimal]:
    """Deduce `saldo_inicial` y `saldo_final` de la columna de saldos.

    El XLSX del banco **no trae saldo inicial**: trae el saldo *despues* de cada
    movimiento. Ese saldo plays el papel del registro de control `98` de la norma
    43: si la columna esta bien, cada saldo es el anterior mas el movimiento, y de
    ahi salen los dos saldos con una sola comprobacion.

    Se aceptan las dos ordenaciones porque el banco entrega el mas reciente
    primero y un exportador propio entregaria lo contrario, y se deduce por que
    direccion encaja en lugar de mirar la primera fecha. Un extracto con un
    descuadre se rechaza, que es lo que evita dar por bueno un fichero con un
    movimiento de mas o de menos.
    """
    n = len(saldos)
    if n < 1:
        raise LayoutError("layout_invalido", registro_de, "saldo", "El extracto no tiene movimientos")

    # Descendente (mas reciente primero): saldo[i] - importe[i] == saldo[i + 1].
    rota_desc = next(
        (i for i in range(n - 1) if saldos[i] - importes[i] != saldos[i + 1]), None
    )
    if rota_desc is None:
        return saldos[-1] - importes[-1], saldos[0]
    # Ascendente (mas antiguo primero): el saldo de la fila i+1 es el de la i mas el
    # movimiento **i+1**, que es el unico que todavia no estaba aplicado.
    rota_asc = next(
        (i for i in range(n - 1) if saldos[i] + importes[i + 1] != saldos[i + 1]), None
    )
    if rota_asc is None:
        return saldos[0] - importes[0], saldos[-1]
    fila = registro_de + rota_desc + 1
    raise LayoutError(
        "layout_invalido",
        fila,
        "saldo",
        f"La columna Saldo no encaja con los importes a partir de la fila {fila}: "
        f"saldo {saldos[rota_desc]} tras un movimiento de {importes[rota_desc]} "
        f"no llega al siguiente {saldos[rota_desc + 1]}",
    )


def parse_xlsx_bancario(file_bytes: bytes) -> ExtractoDTO:
    """Parse el XLSX que da un banco en su area de clientes (SPEC-013).

    Formato de referencia, el que exporta la banca electronica española
    (Santander, y los que copian su plantilla):

    - Una hoja, con un **bloque de metadatos encima** (titular, saldos e IBAN) y
      despues la tabla de movimientos. La cabecera **se busca**, no se asume en la
      fila 1, porque el alto del bloque no esta garantizado.
    - Fechas como texto `DD/MM/AAAA` (no como fecha de Excel).
    - El **signo va en el propio importe**: los cargos son negativos y los abonos
      positivos. No hay columna `D`/`H` como en la norma 43.
    - Una columna `Saldo` con el saldo posterior a cada movimiento.

    El IBAN no se usa como cuenta: es un IBAN, no un codigo del plan, asi que
    `importacion.py` sigue exigiendo que se indique la cuenta 572 a la que
    corresponde. Se devuelve en `ExtractoDTO.iban` para poder mostrarlo.
    """
    import openpyxl

    try:
        libro = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as exc:
        raise LayoutError(
            "layout_invalido", 0, "fichero", "El XLSX esta danado o no se puede leer"
        ) from exc

    try:
        hoja = libro.active
    except AttributeError as exc:
        raise LayoutError("layout_invalido", 0, "fichero", "El XLSX no tiene hojas") from exc
    if hoja is None:
        raise LayoutError("layout_invalido", 0, "fichero", "El XLSX no tiene hojas")

    filas = [tuple(fila) for fila in hoja.iter_rows(values_only=True)]
    if not filas:
        raise LayoutError("layout_invalido", 0, "fichero", "El XLSX esta vacio")

    numero_cabecera, columnas = _buscar_cabecera(filas)
    # `_buscar_cabecera` solo devuelve si estan las tres obligatorias, asi que
    # aqui ya se puede afirmar sin `assert` (que `python -O` se come).
    fecha_col: int = columnas["fechaoperacion"]
    ib_col: int = columnas["importe"]
    saldo_col: int = columnas["saldo"]
    fecha_valor_col: int | None = columnas.get("fechavalor")
    concepto_col: int | None = columnas.get("concepto")
    divisa_col: int | None = columnas.get("divisa")

    movimientos: list[MovimientoDTO] = []
    saldos: list[Decimal] = []
    importes: list[Decimal] = []
    for numero, fila in enumerate(filas[numero_cabecera:], start=numero_cabecera + 1):
        fecha = _fecha_xlsx(_celda(fila, fecha_col), numero, "fecha_operacion")
        if fecha is None:
            # Fila de totales, separadores o cola vacia: se ignoran, no son un
            # movimiento y no deberian tumbar la importacion.
            continue
        importe = importe_de_celda(_celda(fila, ib_col), numero, "importe")
        saldo = importe_de_celda(_celda(fila, saldo_col), numero, "saldo")
        concepto = _celda(fila, concepto_col) if concepto_col is not None else None
        if concepto is not None and not (
            isinstance(concepto, str) and concepto.strip() or concepto == 0
        ):
            concepto = None
        movimientos.append(
            MovimientoDTO(
                orden=0,
                fecha_operacion=fecha,
                fecha_valor=_fecha_xlsx(
                    _celda(fila, fecha_valor_col), numero, "fecha_valor"
                )
                if fecha_valor_col is not None
                else None,
                concepto=(str(concepto).strip() if concepto is not None else "")[:255],
                importe=abs(importe),
                signo="D" if importe < 0 else "H",
                referencia=_referencia_xlsx(fila, columnas),
            )
        )
        saldos.append(saldo)
        importes.append(importe)
        if divisa_col is not None:
            _divisa_eur(_celda(fila, divisa_col), numero)

    if not movimientos:
        raise LayoutError("layout_invalido", 0, "movimientos", "El XLSX no tiene movimientos")

    saldo_inicial, saldo_final = _saldo_final_desde_cadena(
        saldos, importes, numero_cabecera
    )

    # El banco entrega el mas reciente primero. Se ordena a mas antiguo, que es
    # como leen las otras dos variantes y como se lee un extracto en papel.
    movimientos.sort(key=lambda m: (m.fecha_operacion, m.fecha_valor or m.fecha_operacion))
    for orden, movimiento in enumerate(movimientos, start=1):
        movimiento.orden = orden

    fechas = [m.fecha_operacion for m in movimientos]
    return ExtractoDTO(
        cuenta="",
        fecha_inicio=min(fechas),
        fecha_fin=max(fechas),
        saldo_inicial=saldo_inicial,
        saldo_final=saldo_final,
        movimientos=movimientos,
        iban=_iban_de_la_hoja(filas),
    )

