"""Resúmenes de superficie (SPEC-031, US5).

Qué es esto
-----------

Cuando el usuario entra en una superficie ve un panel con sus destinos y, encima, un
resumen de cómo va esa área. Aquí vive el cálculo de ese resumen.

POR QUÉ NO SE COMPONE EN EL CLIENTE
------------------------------------

Podría haberse resuelto desde el frontend, llamando a las APIs que ya existen. Se
descartó por dos razones, y las dos importan:

1. El shell pediría entre cinco y seis peticiones en cada cambio de superficie, cada una
   con su propio manejo de error. Un fallo en una dejaría un hueco en el panel mientras
   las demás llegan, y la interfaz no podría distinguir "no hay datos" de "la consulta
   falló".
2. **El aislamiento por empresa quedaría sin probar en un solo sitio.** Cada endpoint
   existente ya tiene sus tests de tenant, pero "cada uno aísla bien" no es lo mismo que
   "la vista que junta varios de esos endpoints aísla bien". La composición es donde un
   filtro olvidado se convierte en una fuga: es el punto donde los datos de la empresa B
   entran en la pantalla de la A.

QUÉ NO ES ESTO
--------------

No es un dato contable nuevo. Cada cifra sale de una tabla que ya existe, ya está
auditada y ya tiene sus propias reglas. Aquí solo se cuenta, y por eso este módulo no
toca el motor de asientos ni altera ningún saldo. Mantenerlo en lectura es lo que
permite que US5 siga siendo una fase de navegación y no una fase contable.

LOS NÚMEROS SON `int` Y LAS ETIQUETAS SON TEXTO
-----------------------------------------------

Los conteos son enteros y no `Decimal`: no son importes, y forzarlos a cuatro decimales
daría una precisión que no existe. Los importes, cuando los hay (el saldo de
tesorería), sí son `Decimal` y se cuantizan a cuatro decimales por la regla del repo.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryLine
from models.ar.tercero import Tercero
from models.ar.vencimiento import Vencimiento
from models.fiscal.periodo_fiscal import PeriodoFiscal
from models.invoice.factura import Factura
from models.reporting.formulacion import FormulacionCuentasAnuales
from services.navigation.errores import error

#: Claves de superficie. Coinciden con `Superficie.clave` de `surfaces.ts`, y el test
#: `test_destinos_en_sync.py` vigila que las dos copias no se separen. Una superficie
#: nueva obliga a añadirla aqui, al mapa y a una función de resumen.
SUPERFICIES = (
    "contabilidad",
    "facturacion",
    "tesoreria",
    "informes",
    "fiscal",
    "maestros",
)

#: La superficie se resuelve contra la sesion, nunca contra el path. Se exporta para
#: que la API lo use en la validacion sin volver a escribir la lista.
SUPERFICIA_DESCONOCIDA = "superficie_desconocida"

#: `motivo` del resumen cuando la empresa no tiene ningún ejercicio contable. No es un
#: error: es una empresa recién creada, y su landing tiene que abrirse y decir eso.
SIN_EJERCICIO = "sin_ejercicio"

#: Cuenta de tesoreria. Es una constante de negocio del PGC, no un parametro: el
#: resumen tiene que ser el mismo para todos los usuarios de una empresa, o el panel
#: dependeria de quien lo mire.
CUENTA_TESORERIA = "572"


def _metrica(clave: str, etiqueta: str, valor: object, unidad: str | None = None) -> dict:
    """Métrica del resumen. `clave` es estable y `etiqueta` es para la persona.

    Se llevan las dos porque cada una tiene un consumidor distinto: el test comprueba
    `valor` por `clave`, porque la etiqueta puede cambiar de redacción; y la interfaz
    muestra `etiqueta`, porque una clave no se le enseña a nadie.
    """
    metrica = {"clave": clave, "etiqueta": etiqueta, "valor": valor}
    if unidad is not None:
        metrica["unidad"] = unidad
    return metrica


def _enlace(clave: str, etiqueta: str, ruta: str) -> dict:
    """Un "ir a" del resumen.

    Sin ellos el resumen informa pero no ayuda: el usuario lee que le faltan cuatro
    facturas y tiene que acordarse de dónde se emiten.
    """
    return {"clave": clave, "etiqueta": etiqueta, "ruta": ruta}


async def _contabilidad(db: AsyncSession, empresa_id: int, ejercicio: int) -> dict:
    """Asientos del ejercicio y el último, que es lo que pide el escenario 1."""
    total = await db.scalar(
        sa.select(sa.func.count())
        .select_from(JournalEntry)
        .where(JournalEntry.empresa_id == empresa_id, JournalEntry.ejercicio == ejercicio)
    )
    ultimo = (
        await db.execute(
            sa.select(JournalEntry.numero_asiento, JournalEntry.fecha, JournalEntry.concepto)
            .where(
                JournalEntry.empresa_id == empresa_id,
                JournalEntry.ejercicio == ejercicio,
                JournalEntry.numero_asiento.is_not(None),
            )
            .order_by(JournalEntry.fecha.desc(), JournalEntry.numero_asiento.desc())
            .limit(1)
        )
    ).first()

    metricas = [_metrica("asientos", "Asientos del ejercicio", int(total or 0))]
    if ultimo is not None and ultimo[0] is not None:
        metricas.append(
            _metrica("ultimo_asiento", "Último asiento", int(ultimo[0]), "numero")
        )
        metricas.append(
            _metrica("ultima_fecha", "Fecha del último", ultimo[1].isoformat())
        )
    return {
        "metricas": metricas,
        "enlaces": [
            _enlace("asientos", "Ver asientos", "/asientos/diario"),
            _enlace("nuevo_asiento", "Nuevo asiento", "/asientos/nuevo"),
        ],
    }


async def _facturacion(db: AsyncSession, empresa_id: int, ejercicio: int) -> dict:
    """Facturas emitidas y recibidas del ejercicio (escenario de US5, T048).

    Se cuenta por `ejercicio`, no por rango de fechas, igual que en contabilidad.
    """
    base = sa.select(sa.func.count()).select_from(Factura).where(
        Factura.empresa_id == empresa_id, Factura.ejercicio == ejercicio
    )
    emitidas = int(await db.scalar(base.where(Factura.tipo == "VENTA")) or 0)
    recibidas = int(await db.scalar(base.where(Factura.tipo == "COMPRA")) or 0)
    return {
        "metricas": [
            _metrica("facturas_emitidas", "Facturas emitidas", emitidas),
            _metrica("facturas_recibidas", "Facturas recibidas", recibidas),
        ],
        "enlaces": [
            _enlace("facturas", "Ver facturas", "/facturacion/facturas"),
            _enlace("series", "Series", "/facturacion/series"),
        ],
    }


async def _tesoreria(db: AsyncSession, empresa_id: int, ejercicio: int) -> dict:
    """Saldo de tesorería y vencimientos próximos (escenario 2).

    El saldo se calcula sobre el diario POSTED de las cuentas de tesorería, que es la
    única fuente que no depende de que alguien haya conciliado. La conciliación afecta a
    la vista de extractos, no al saldo real: usarlo aquí mezclaría dos cosas distintas.

    Se cruzan `JournalEntryLine` con `JournalEntry` por ORM y no con `text()` suelto, por
    dos razones. La primera es que `text()` no hereda los alias del FROM, así que
    cualquier cambio de nombre de tabla lo rompe sin que avise. La segunda es que el
    filtro de empresa vive en las dos tablas, y escribirlos a mano en un `text()` es la
    forma más fácil de olvidar el de una.
    """
    filtros_linea = (
        JournalEntryLine.cuenta.like(f"{CUENTA_TESORERIA}%"),
    )
    filtros_entrada = (
        JournalEntry.empresa_id == empresa_id,
        JournalEntry.ejercicio == ejercicio,
        JournalEntry.estado == "POSTED",
    )

    async def _suma(campo) -> Decimal:
        valor = await db.scalar(
            sa.select(sa.func.coalesce(sa.func.sum(campo), 0))
            .select_from(JournalEntryLine)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .where(JournalEntryLine.empresa_id == empresa_id, *filtros_entrada, *filtros_linea)
        )
        return Decimal(str(valor or 0))

    saldo = (await _suma(JournalEntryLine.debe) - await _suma(JournalEntryLine.haber)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_EVEN
    )

    pendientes = int(
        await db.scalar(
            sa.select(sa.func.count())
            .select_from(Vencimiento)
            .where(
                Vencimiento.empresa_id == empresa_id,
                Vencimiento.ejercicio == ejercicio,
                Vencimiento.estado == "pendiente",
            )
        )
        or 0
    )
    return {
        "metricas": [
            _metrica("saldo_tesoreria", "Saldo de tesorería", str(saldo), "eur"),
            _metrica("vencimientos_pendientes", "Vencimientos pendientes", pendientes),
        ],
        "enlaces": [
            _enlace("vencimientos", "Vencimientos", "/vencimientos"),
            _enlace("conciliacion", "Conciliación", "/conciliacion"),
        ],
    }


async def _informes(db: AsyncSession, empresa_id: int, ejercicio: int) -> dict:
    """Estado de formulación de cuentas anuales (T049).

    Se cuenta sobre `formulacion_cuentas_anuales`, que es donde SPEC-010 deja la
    formulacion. Se consulta el estado de la fila, no el contenido del snapshot: el
    resumen informa de si está formulado, no de las cifras del balance, que para eso
    están `/balance` y `/pyg`.
    """
    formuladas = int(
        await db.scalar(
            sa.select(sa.func.count())
            .select_from(FormulacionCuentasAnuales)
            .where(
                FormulacionCuentasAnuales.empresa_id == empresa_id,
                FormulacionCuentasAnuales.ejercicio == ejercicio,
            )
        )
        or 0
    )
    return {
        "metricas": [
            _metrica("formulaciones", "Formulaciones del ejercicio", formuladas),
        ],
        "enlaces": [
            _enlace("cuentas_anuales", "Cuentas anuales", "/cuentas-anuales"),
            _enlace("balance", "Balance", "/balance"),
            _enlace("pyg", "Pérdidas y ganancias", "/pyg"),
        ],
    }


async def _fiscal(db: AsyncSession, empresa_id: int, ejercicio: int) -> dict:
    """Estado de los libros de IVA (T050).

    `periodo_fiscal` viene de SPEC-012. Se cuentan los periodos del ejercicio, que es lo
    que responde a "cómo va de IVA", sin recalcular ningún libro.
    """
    periodos = int(
        await db.scalar(
            sa.select(sa.func.count())
            .select_from(PeriodoFiscal)
            .where(
                PeriodoFiscal.empresa_id == empresa_id,
                PeriodoFiscal.ejercicio == ejercicio,
            )
        )
        or 0
    )
    return {
        "metricas": [_metrica("periodos_fiscales", "Periodos fiscales", periodos)],
        "enlaces": [
            _enlace("libros_iva", "Libros de IVA", "/libros-iva"),
            _enlace("modelos", "Modelos", "/modelos"),
        ],
    }


async def _maestros(db: AsyncSession, empresa_id: int, ejercicio: int) -> dict:
    """Recuento de maestros y de terceros (T051, T071).

    `account_plan` se consulta por `tenant_id`, no por `empresa_id`: es la excepción de
    SPEC-001, y está señalada en su propio modelo. Es el tipo de detalle que hace que un
    recuento salga en cero sin que nada falle, así que va escrito y no heredado.
    """
    del ejercicio
    cuentas = int(
        await db.scalar(
            sa.select(sa.func.count())
            .select_from(AccountPlan)
            .where(AccountPlan.tenant_id == empresa_id)
        )
        or 0
    )
    terceros = int(
        await db.scalar(
            sa.select(sa.func.count())
            .select_from(Tercero)
            .where(Tercero.empresa_id == empresa_id)
        )
        or 0
    )
    return {
        "metricas": [
            _metrica("cuentas", "Cuentas del plan", cuentas),
            _metrica("terceros", "Terceros", terceros),
        ],
        "enlaces": [
            _enlace("empresas", "Empresas", "/maestros/empresas"),
            _enlace("terceros", "Terceros", "/terceros"),
            _enlace("plan_cuentas", "Plan de cuentas", "/cuentas"),
        ],
    }


#: Un registro por superficie: qué función la resuelve. Añadir una superficie es
#: añadir una entrada aquí, y el test de las seis superficies falla si se olvida.
RESOLUTORES = {
    "contabilidad": _contabilidad,
    "facturacion": _facturacion,
    "tesoreria": _tesoreria,
    "informes": _informes,
    "fiscal": _fiscal,
    "maestros": _maestros,
}


def validar_superficie(superficie: str) -> None:
    """404 si la clave no es una de las seis superficies del mapa."""
    if superficie not in RESOLUTORES:
        raise error(
            SUPERFICIA_DESCONOCIDA,
            f"'{superficie}' no es una superficie de navegacion.",
            status_code=404,
        )


async def resumen(
    db: AsyncSession, *, empresa_id: int, superficie: str, ejercicio: int | None
) -> dict:
    """El resumen de una superficie, ya con su cabecera.

    La cabecera (`superficie`, `empresa_id`, `ejercicio`) la pone la API, no el
    resolutor: es el mismo dato para las seis, y repetirlo seis veces sería seis sitios
    donde se puede olvidar el filtro de empresa.

    SIN EJERCICIO NO ES UN ERROR
    ----------------------------

    Una empresa recién creada no tiene ningún `EjercicioContable`. Su landing tiene que
    abrirse igualmente, porque es la pantalla desde la que se ve que no hay nada todavía.
    Por eso `ejercicio` puede ser `None` y lo que se devuelve son cero métricas con un
    `motivo`, no un 422: "todavía no hay ejercicio" es un estado normal de la aplicación,
    y un error convertiría el primer arranque en una pantalla de fallo.

    Es el mismo criterio que aplica `elegir_activo`, que devuelve `None` en lugar de
    suponer un ejercicio. Aquí no se supone nada: se dice que no lo hay.
    """
    validar_superficie(superficie)
    if ejercicio is None:
        return {
            "superficie": superficie,
            "empresa_id": empresa_id,
            "ejercicio": None,
            "motivo": SIN_EJERCICIO,
            "metricas": [],
            "enlaces": [],
        }
    cuerpo = await RESOLUTORES[superficie](db, empresa_id, ejercicio)
    return {
        "superficie": superficie,
        "empresa_id": empresa_id,
        "ejercicio": ejercicio,
        "motivo": None,
        "metricas": cuerpo["metricas"],
        "enlaces": cuerpo["enlaces"],
    }
