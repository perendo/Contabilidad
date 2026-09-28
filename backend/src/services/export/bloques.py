"""Catalogo de bloques de datos exportables (SPEC-029 T009, research D2).

El catalogo es la **unica** fuente de verdad de que se exporta: cada `Bloque`
declara su nombre, su fichero dentro del ZIP, las entidades (tablas) que lo
componen y si admite el filtro por rango de ejercicios (FR-005). Los 17 bloques
obligatorios cubren FR-004; el bloque `datos_sii` es opcional (US3).

Multi-tenancy (research D4): cada tabla declara su columna de empresa
(`empresa_id`, `tenant_id` en `account_plan` de SPEC-001, `company_id` en
`companies`), y `recopilar.recopilar_bloque` la filtra **siempre** con el
`empresa_id` derivado de la sesion. Ninguna consulta existe sin ese filtro.

Filtro por ejercicio: se declara la columna que lo aporta (`ejercicio` entero,
`fecha` de tipo fecha, o un rango `fecha_ini`/`fecha_fin`) o la tabla padre
para las tablas hijas sin fecha propia (`journal_entry_line`, `factura_linea`,
`balanza_periodo_linea`, `desviacion`). El rango se aplica como comparacion de
fechas, no con `EXTRACT`, para que sea portable a SQLite y PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "BLOQUES",
    "BLOQUE_SII",
    "Bloque",
    "Padre",
    "TablaBloque",
    "bloque_por_nombre",
    "bloques_registro",
    "nombres_bloques",
    "ruta_por_nombre",
]

#: Prefijo de las lineas de manifiesto del bloque opcional SII (US3).
BLOQUE_SII = "datos_sii"

#: Etiquetas internas de las columnas auxiliares que anaden el ejercicio y la
#: fecha de cada fila para calcular `ejercicio_min/max` y `fecha_min/max`.
COL_EJERCICIO = "__ejercicio"
COL_FECHA = "__fecha"


@dataclass(frozen=True)
class Padre:
    """Tabla padre de la que se hereda el ejercicio de las filas hijas."""

    tabla: str
    clave: str
    empresa_col: str
    ejercicio_col: str | None = None
    fecha_col: str | None = None
    fecha_ini_col: str | None = None
    fecha_fin_col: str | None = None


@dataclass(frozen=True)
class TablaBloque:
    """Una tabla dentro de un bloque de exportacion.

    `empresa_col` es **obligatoria**: sin ella la tabla no se exporta (constitution
    III). El filtro por ejercicio se resuelve por este orden: `rango` (solape),
    columna `ejercicio` entera, columna `fecha`, y por ultimo la tabla `padre`.
    """

    tabla: str
    empresa_col: str
    padre: Padre | None = None
    fecha_col: str | None = None
    rango: tuple[str, str] | None = None
    #: `False` para maestro de datos cuya fecha es de alta/asignacion y no de
    #: negocio (`tercero_subcuenta`, proyecciones de `catalogo_version`): se
    #: exportan integros aunque se filtre por ejercicio (research D3).
    filtra_rango: bool = True
    excluir: frozenset[str] = field(default_factory=frozenset)
    #: Nombre legible de la entidad (snapshot del manifiesto).
    entidad: str = ""

    @property
    def nombre_entidad(self) -> str:
        """Nombre de la entidad para el snapshot del manifiesto."""
        return self.entidad or self.tabla


@dataclass(frozen=True)
class Bloque:
    """Bloque del catalogo: nombre, fichero, entidades y filtro por ejercicio."""

    nombre: str
    fichero: str
    descripcion: str
    tablas: tuple[TablaBloque, ...]
    #: `True` si alguna de sus tablas aporta ejercicio o fecha (research D3).
    filtra_ejercicio: bool = False
    opcional: bool = False

    @property
    def ruta(self) -> str:
        """Ruta del fichero dentro del ZIP; vacia si el bloque es un directorio.

        `datos_sii` es un directorio: sus dos ficheros los escribe
        `services.export.sii` porque su contenido se deriva de facturas, no de
        una consulta directa de tabla.
        """
        return f"bloques/{self.fichero}" if self.fichero.endswith(".json") else ""

    @property
    def entidades(self) -> tuple[str, ...]:
        """Entidades incluidas en el bloque, en orden de tabla."""
        return tuple(tabla.nombre_entidad for tabla in self.tablas)

    def construir_consulta(
        self,
        empresa_id: int,
        desde: int | None = None,
        hasta: int | None = None,
    ) -> Any:
        """Funcion query del bloque: `Select` con filtro de empresa y ejercicio.

        Se delega en `recopilar.construir_consulta_bloque`, que resuelve los
        filtros por tabla; se expone aqui para que el catalogo sea
        introspectable (test T012) sin depender de la sesion.
        """
        from services.export.recopilar import construir_consulta_bloque

        return construir_consulta_bloque(self, empresa_id, desde, hasta)


def _t(
    tabla: str,
    empresa_col: str = "empresa_id",
    *,
    padre: tuple[str, str] | None = None,
    padre_ejercicio: str | None = "ejercicio",
    padre_fecha: str | None = None,
    padre_rango: tuple[str, str] | None = None,
    fecha_col: str | None = None,
    rango: tuple[str, str] | None = None,
    filtra_rango: bool = True,
    entidad: str = "",
    excluir: frozenset[str] = frozenset(),
) -> TablaBloque:
    """Constructor corto: declara el padre y de que columna se hereda el rango."""
    ref: Padre | None = None
    if padre is not None:
        ref = Padre(
            tabla=padre[0],
            clave=padre[1],
            empresa_col=empresa_col,
            ejercicio_col=padre_ejercicio,
            fecha_col=padre_fecha,
            fecha_ini_col=padre_rango[0] if padre_rango else None,
            fecha_fin_col=padre_rango[1] if padre_rango else None,
        )
    return TablaBloque(
        tabla=tabla,
        empresa_col=empresa_col,
        padre=ref,
        fecha_col=fecha_col,
        rango=rango,
        filtra_rango=filtra_rango,
        excluir=excluir,
        entidad=entidad or tabla,
    )


#: Orden de escritura dentro del ZIP: los tres digitos del nombre de fichero
#: fijan la posicion y coinciden con el orden alfabetico de las rutas.
BLOQUES: tuple[Bloque, ...] = (
    Bloque(
        nombre="plan_cuentas",
        fichero="001_plan_cuentas.json",
        descripcion="Plan de cuentas de la empresa (SPEC-001)",
        tablas=(_t("account_plan", "tenant_id", entidad="AccountPlan"),),
    ),
    Bloque(
        nombre="plan_cuentas_versiones",
        fichero="002_plan_cuentas_versiones.json",
        descripcion="Versiones del catalogo y mapeos entre ellas (SPEC-025)",
        tablas=(
            _t(
                "catalogo_version",
                rango=("fecha_inicio", "fecha_fin"),
                fecha_col="fecha_inicio",
                entidad="CatalogoVersion",
            ),
            _t("catalogo_cuenta", filtra_rango=False, entidad="CatalogoCuenta"),
            _t("mapeo_cuenta", filtra_rango=False, entidad="MapeoCuenta"),
        ),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="asientos",
        fichero="003_asientos.json",
        descripcion="Cabeceras de asientos (SPEC-002)",
        tablas=(_t("journal_entry", entidad="JournalEntry"),),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="apuntes",
        fichero="004_apuntes.json",
        descripcion="Lineas de asiento (SPEC-002)",
        tablas=(
            _t(
                "journal_entry_line",
                padre=("journal_entry", "journal_entry_id"),
                entidad="JournalEntryLine",
            ),
        ),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="terceros",
        fichero="005_terceros.json",
        descripcion="Maestro de terceros y subcuentas (SPEC-008)",
        tablas=(
            _t("tercero", entidad="Tercero"),
            # `fecha_asignacion` es de alta de la subcuenta, no de negocio.
            _t("tercero_subcuenta", filtra_rango=False, entidad="TerceroSubcuenta"),
        ),
    ),
    Bloque(
        nombre="facturas",
        fichero="006_facturas.json",
        descripcion="Series y cabeceras de factura (SPEC-007)",
        tablas=(_t("serie_factura", entidad="SerieFactura"), _t("factura", entidad="Factura")),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="lineas_factura",
        fichero="007_lineas_factura.json",
        descripcion="Lineas de factura (SPEC-007)",
        tablas=(
            _t(
                "factura_linea",
                padre=("factura", "factura_id"),
                entidad="FacturaLinea",
            ),
        ),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="vencimientos",
        fichero="008_vencimientos.json",
        descripcion="Vencimientos de cobros y pagos (SPEC-011)",
        tablas=(_t("vencimiento", entidad="Vencimiento"),),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="cobros_pagos",
        fichero="009_cobros_pagos.json",
        descripcion="Cobros y pagos registrados (SPEC-011)",
        tablas=(_t("cobro_pago", entidad="CobroPago"),),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="remesas",
        fichero="010_remesas.json",
        descripcion="Remesas SEPA y recibos (SPEC-020)",
        tablas=(_t("remesa", entidad="Remesa"), _t("recibo_remesa", entidad="ReciboRemesa")),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="devoluciones",
        fichero="011_devoluciones.json",
        descripcion="Devoluciones de recibos y reclamaciones (SPEC-020)",
        tablas=(
            _t("devolucion_recibo", entidad="DevolucionRecibo"),
            _t("reclamacion", entidad="Reclamacion"),
        ),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="amortizaciones",
        fichero="012_amortizaciones.json",
        descripcion="Inmovilizado, planes y amortizaciones (SPEC-014)",
        tablas=(
            _t("activo_inmovilizado", entidad="ActivoInmovilizado"),
            _t("plan_amortizacion", entidad="PlanAmortizacion"),
            _t("amortizacion_generada", entidad="AmortizacionGenerada"),
            _t("baja_activo", entidad="BajaActivo"),
        ),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="cierres",
        fichero="013_cierres.json",
        descripcion="Periodos cerrados, balances y cierres anuales (SPEC-028)",
        tablas=(
            _t("periodo_cerrado", entidad="PeriodoCerrado"),
            _t("balanza_periodo", entidad="BalanzaPeriodo"),
            _t(
                "balanza_periodo_linea",
                padre=("balanza_periodo", "balanza_id"),
                entidad="BalanzaPeriodoLinea",
            ),
            _t("cierre_ejercicio", entidad="CierreEjercicio"),
            _t("solicitud_reapertura", entidad="SolicitudReapertura"),
        ),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="presupuestos",
        fichero="014_presupuestos.json",
        descripcion="Presupuestos, periodos de seguimiento y desviaciones (SPEC-026)",
        tablas=(
            _t("presupuesto", entidad="Presupuesto"),
            _t("periodo_seguimiento", entidad="PeriodoSeguimiento"),
            _t(
                "desviacion",
                padre=("periodo_seguimiento", "periodo_id"),
                entidad="Desviacion",
            ),
        ),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="previsiones",
        fichero="015_previsiones.json",
        descripcion="Previsiones de tesoreria y sus movimientos (SPEC-027)",
        tablas=(
            _t("prevision_tesoreria", entidad="PrevisionTesoreria"),
            _t("movimiento_prevision", entidad="MovimientoPrevision"),
        ),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="libros_iva",
        fichero="016_libros_iva.json",
        descripcion="Periodos fiscales, modelos, IVA diferido e informes (SPEC-012/010)",
        tablas=(
            _t("periodo_fiscal", entidad="PeriodoFiscal"),
            _t("exportacion_modelo", entidad="ExportacionModelo"),
            _t("iva_diferido_caja", entidad="IVADiferidoCaja"),
            _t("formulacion_cuentas_anuales", entidad="FormulacionCuentasAnuales"),
            _t("configuracion_informe", entidad="ConfiguracionInforme"),
            _t("clasificacion_efe", entidad="ClasificacionEFE"),
        ),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="configuracion",
        fichero="017_configuracion.json",
        descripcion="Configuracion general y fiscal de la empresa",
        tablas=(
            _t("companies", "company_id", entidad="Company"),
            _t("configuracion_fiscal", entidad="ConfiguracionFiscal"),
            _t("configuracion_sii", entidad="ConfiguracionSII"),
        ),
        filtra_ejercicio=True,
    ),
    Bloque(
        nombre="datos_sii",
        fichero="datos_sii/",
        descripcion="Datos normalizados para el SII de la AEAT (US3, opcional)",
        tablas=(),
        opcional=True,
    ),
)

#: Los 17 bloques obligatorios de FR-004, en orden de escritura.
BLOQUES_OBLIGATORIOS: tuple[Bloque, ...] = tuple(b for b in BLOQUES if not b.opcional)


def bloques_registro() -> tuple[Bloque, ...]:
    """Catalogo ordenado, incluida la entrada opcional de US3."""
    return BLOQUES


def nombres_bloques(incluir_opcionales: bool = False) -> tuple[str, ...]:
    """Nombres de los bloques, en orden de escritura dentro del ZIP."""
    return tuple(
        b.nombre for b in BLOQUES if incluir_opcionales or not b.opcional
    )


def bloque_por_nombre(nombre: str) -> Bloque | None:
    """Bloque del catalogo con ese nombre, o `None` si no existe."""
    for bloque in BLOQUES:
        if bloque.nombre == nombre:
            return bloque
    return None


def ruta_por_nombre(nombre: str) -> str | None:
    """Ruta dentro del ZIP de un bloque del manifiesto.

    Los 17 bloques se resuelven por el catalogo; las lineas `datos_sii.*` que
    inyecta `services.export.sii` se resuelven por sufijo dentro del
    directorio `bloques/datos_sii/`.
    """
    bloque = bloque_por_nombre(nombre)
    if bloque is not None:
        return bloque.ruta or None
    if nombre.startswith(f"{BLOQUE_SII}."):
        return f"bloques/{BLOQUE_SII}/{nombre.split('.', 1)[1]}.json"
    return None
