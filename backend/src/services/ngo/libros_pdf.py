"""Generación de libros oficiales en PDF (SPEC-019 US2 / FR-005).

Los libros solo se generan sobre ejercicios cerrados (SPEC-004) y reflejan
fielmente el diario/mayor inmutable (SC-002). La `sha256` se calcula sobre el
contenido textual canónico (no sobre el binario del PDF) para que la
comparación entre re-emisiones sea estable (D3/D4); el diario comparte canon con
la legalización (contracts/legalizacion.md §2).
"""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, date, datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry, JournalEntryLine
from models.iam.company import Company
from models.ngo.libros import LibroOficial, LibroTipo
from services.audit.writer import audit_escribir
from services.ngo.errores import NgoError

TIPOS_VALIDOS = {t.value for t in LibroTipo}


def _cuatro(value: Decimal) -> str:
    return f"{value:0.4f}"


async def _ejercicio_cerrado(db: AsyncSession, empresa_id: int, ejercicio: int) -> FiscalYear:
    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id,
            FiscalYear.year == ejercicio,
        )
    )
    if fy is None:
        raise NgoError("ejercicio_inexistente", f"No existe el ejercicio {ejercicio}")
    if not fy.is_closed:
        raise NgoError("ejercicio_abierto", f"El ejercicio {ejercicio} no está cerrado")
    return fy


async def _empresa(db: AsyncSession, empresa_id: int) -> tuple[str, str]:
    comp = await db.get(Company, empresa_id)
    if comp is None:
        return "", ""
    return comp.razon_social, comp.nif


async def _entradas_ejercicio(db: AsyncSession, empresa_id: int, ejercicio: int) -> list[dict]:
    entradas = (
        await db.scalars(
            select(JournalEntry)
            .where(
                JournalEntry.empresa_id == empresa_id,
                JournalEntry.ejercicio == ejercicio,
                JournalEntry.numero_asiento.is_not(None),
            )
            .order_by(JournalEntry.numero_asiento)
        )
    ).all()
    resultado: list[dict] = []
    for entrada in entradas:
        lineas = (
            await db.scalars(
                select(JournalEntryLine)
                .where(
                    JournalEntryLine.empresa_id == empresa_id,
                    JournalEntryLine.journal_entry_id == entrada.id,
                )
                .order_by(JournalEntryLine.line_no)
            )
        ).all()
        resultado.append(
            {
                "id": entrada.id,
                "numero": entrada.numero_asiento,
                "fecha": entrada.fecha.isoformat(),
                "concepto": entrada.concepto,
                "lineas": [
                    {
                        "cuenta": l.cuenta,
                        "descripcion": l.descripcion or "",
                        "debe": l.debe,
                        "haber": l.haber,
                    }
                    for l in lineas
                ],
            }
        )
    return resultado


def _rango(entradas: list[dict]) -> tuple[int, int]:
    numeros = [e["numero"] for e in entradas if e["numero"] is not None]
    if not numeros:
        return 0, 0
    return int(min(numeros)), int(max(numeros))


def _total_lineas(entradas: list[dict]) -> tuple[Decimal, Decimal]:
    debe = sum((l["debe"] for e in entradas for l in e["lineas"]), Decimal(0))
    haber = sum((l["haber"] for e in entradas for l in e["lineas"]), Decimal(0))
    return debe, haber


def canon_diario(empresa_id: int, ejercicio: int, entradas: list[dict]) -> str:
    desde, hasta = _rango(entradas)
    canon = f"{empresa_id}|{ejercicio}|{desde}|{hasta}|"
    for e in entradas:
        canon += f"{e['numero']}|{e['fecha']}|"
        for l in e["lineas"]:
            canon += f"{l['cuenta']}|{l['debe']:.4f}|{l['haber']:.4f}|"
    return canon


def canon_mayor(
    empresa_id: int, ejercicio: int, cuentas: list[dict], desde: int, hasta: int
) -> str:
    canon = f"{empresa_id}|{ejercicio}|mayor|{desde}|{hasta}|"
    for c in cuentas:
        canon += f"ACCOUNT|{c['code']}|{c['name']}|"
        for fila in c["filas"]:
            canon += f"{fila['numero']}|{fila['fecha']}|{fila['debe']:.4f}|{fila['haber']:.4f}|{fila['saldo']:.4f}|"
        canon += f"BALANCE|{c['saldo_final']:.4f}|"
    return canon


def canon_cuentas_anuales(
    empresa_id: int, ejercicio: int, rubros: list[dict], desde: int, hasta: int
) -> str:
    canon = f"{empresa_id}|{ejercicio}|cuentas_anuales|{desde}|{hasta}|"
    for r in rubros:
        canon += f"{r['codigo']}|{r['nombre']}|{r['saldo']:.4f}|"
    return canon


async def _datos_cuentas(db: AsyncSession, empresa_id: int, ejercicio: int) -> list[dict]:
    entradas = await _entradas_ejercicio(db, empresa_id, ejercicio)
    por_cuenta: dict[str, dict] = {}
    for e in entradas:
        for l in e["lineas"]:
            c = por_cuenta.setdefault(
                l["cuenta"], {"code": l["cuenta"], "name": l["descripcion"], "filas": [], "saldo": Decimal(0)}
            )
            movimiento = l["debe"] - l["haber"]
            c["saldo"] += movimiento
            c["filas"].append(
                {
                    "numero": e["numero"],
                    "fecha": e["fecha"],
                    "debe": l["debe"],
                    "haber": l["haber"],
                    "saldo": c["saldo"],
                }
            )
    cuentas = []
    for code in sorted(por_cuenta):
        c = por_cuenta[code]
        c["name"] = c["name"] or code
        cuentas.append(
            {
                "code": c["code"],
                "name": c["name"],
                "filas": c["filas"],
                "saldo_final": c["saldo"],
            }
        )
    return cuentas


async def _datos_cuentas_anuales(db: AsyncSession, empresa_id: int, ejercicio: int) -> list[dict]:
    cuentas = await _datos_cuentas(db, empresa_id, ejercicio)
    balance = [c for c in cuentas if c["code"][0] in "12345"]
    pyg = [c for c in cuentas if c["code"][0] in "67"]
    rubros = [
        {"codigo": "balance", "nombre": "Balance de situacion", "saldo": Decimal(0)},
    ]
    for c in balance:
        rubros.append({"codigo": c["code"], "nombre": c["name"], "saldo": c["saldo_final"]})
    rubros.append({"codigo": "pyg", "nombre": "Perdidas y ganancias", "saldo": Decimal(0)})
    for c in pyg:
        rubros.append({"codigo": c["code"], "nombre": c["name"], "saldo": c["saldo_final"]})
    return rubros


def _estilos():
    estilos = getSampleStyleSheet()
    return estilos


def _pdf_diario(meta: dict, entradas: list[dict], total_debe: Decimal, total_haber: Decimal) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"Libro Diario {meta['ejercicio']}")
    estilos = _estilos()
    t1 = estilos["Title"]
    h2 = estilos["Heading2"]
    normal = estilos["Normal"]

    flow: list = [
        Paragraph(f"Libro Diario - {meta['razon_social']} (NIF {meta['nif']})", t1),
        Paragraph(f"Ejercicio {meta['ejercicio']} | Rango de asientos: Nº {meta['desde']} - Nº {meta['hasta']}", h2),
        Paragraph(f"Fecha de generacion: {meta['fecha_generacion']}", normal),
        Spacer(1, 0.4 * cm),
    ]
    for e in entradas:
        flow.append(
            Paragraph(f"Asiento Nº {e['numero']} | Fecha {e['fecha']} | {e['concepto']}", h2)
        )
        filas = [["Cuenta", "Descripcion", "Debe", "Haber"]]
        for l in e["lineas"]:
            filas.append([l["cuenta"], l["descripcion"], _cuatro(l["debe"]), _cuatro(l["haber"])])
        tabla = Table(filas, colWidths=[2.2 * cm, 7.0 * cm, 3.4 * cm, 3.4 * cm])
        tabla.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            )
        )
        flow.append(tabla)
        flow.append(
            Paragraph(
                f"Total asiento: Debe = {_cuatro(total_debe)} | Haber = {_cuatro(total_haber)}",
                normal,
            )
        )
        flow.append(Spacer(1, 0.4 * cm))
    flow.append(
        Paragraph(f"Suma total del diario: Debe = {_cuatro(total_debe)} | Haber = {_cuatro(total_haber)}", h2)
    )
    _construir(doc, flow)
    return buf.getvalue()


def _pdf_mayor(meta: dict, cuentas: list[dict]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"Libro Mayor {meta['ejercicio']}")
    estilos = _estilos()
    t1 = estilos["Title"]
    h2 = estilos["Heading2"]
    normal = estilos["Normal"]

    flow: list = [
        Paragraph(f"Libro Mayor - {meta['razon_social']} (NIF {meta['nif']})", t1),
        Paragraph(f"Ejercicio {meta['ejercicio']} | Rango de asientos: Nº {meta['desde']} - Nº {meta['hasta']}", h2),
        Paragraph(f"Fecha de generacion: {meta['fecha_generacion']}", normal),
        Spacer(1, 0.4 * cm),
    ]
    for c in cuentas:
        flow.append(Paragraph(f"Cuenta {c['code']} | {c['name']}", h2))
        filas = [["Nº", "Fecha", "Concepto", "Debe", "Haber", "Saldo"]]
        total_debe = Decimal(0)
        total_haber = Decimal(0)
        for fila in c["filas"]:
            total_debe += fila["debe"]
            total_haber += fila["haber"]
            filas.append(
                [
                    str(fila["numero"]),
                    fila["fecha"],
                    "",
                    _cuatro(fila["debe"]),
                    _cuatro(fila["haber"]),
                    _cuatro(fila["saldo"]),
                ]
            )
        filas.append(["","","Totales", _cuatro(total_debe), _cuatro(total_haber), _cuatro(c["saldo_final"])])
        tabla = Table(filas, colWidths=[1.5 * cm, 2.6 * cm, 6.0 * cm, 2.7 * cm, 2.7 * cm, 2.7 * cm])
        tabla.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            )
        )
        flow.append(tabla)
        flow.append(Paragraph(f"Saldo final de la cuenta: {_cuatro(c['saldo_final'])}", normal))
        flow.append(Spacer(1, 0.4 * cm))
    _construir(doc, flow)
    return buf.getvalue()


def _pdf_cuentas_anuales(meta: dict, rubros: list[dict]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"Cuentas Anuales {meta['ejercicio']}")
    estilos = _estilos()
    t1 = estilos["Title"]
    h2 = estilos["Heading2"]

    flow: list = [
        Paragraph(f"Cuentas Anuales - {meta['razon_social']} (NIF {meta['nif']})", t1),
        Paragraph(f"Ejercicio {meta['ejercicio']} | Rango de asientos: Nº {meta['desde']} - Nº {meta['hasta']}", h2),
        Paragraph(f"Fecha de generacion: {meta['fecha_generacion']}", estilos["Normal"]),
        Spacer(1, 0.4 * cm),
    ]
    filas = [["Codigo", "Rubro", "Saldos"]]
    for r in rubros:
        filas.append([r["codigo"], r["nombre"], _cuatro(r["saldo"])])
    tabla = Table(filas, colWidths=[3.0 * cm, 9.0 * cm, 4.0 * cm])
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    flow.append(tabla)
    _construir(doc, flow)
    return buf.getvalue()


def _construir(doc: SimpleDocTemplate, flow: list) -> None:
    def numerar(canv: pdf_canvas.Canvas, _doc: SimpleDocTemplate) -> None:
        canv.saveState()
        canv.setFont("Helvetica", 8)
        canv.drawCentredString(A4[0] / 2.0, 1.0 * cm, f"Pagina {canv.getPageNumber()}")
        canv.restoreState()

    doc.build(flow, onFirstPage=numerar, onLaterPages=numerar)


class _PDFLibro:
    def __init__(self, tipo: str):
        self.tipo = tipo

    def construir(self, meta: dict, datos: dict) -> bytes:
        if self.tipo == LibroTipo.diario.value:
            return _pdf_diario(meta, datos["entradas"], datos["total_debe"], datos["total_haber"])
        if self.tipo == LibroTipo.mayor.value:
            return _pdf_mayor(meta, datos["cuentas"])
        return _pdf_cuentas_anuales(meta, datos["rubros"])


async def generar_libros(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    tipos: list[str],
    actor: str | None = None,
) -> list[dict]:
    await _ejercicio_cerrado(db, empresa_id, ejercicio)
    invalidos = [t for t in tipos if t not in TIPOS_VALIDOS]
    if invalidos:
        raise NgoError("tipo_invalido", f"Tipos de libro desconocidos: {invalidos}")
    if not tipos:
        raise NgoError("tipos_vacios", "Debe indicar al menos un tipo de libro")

    razon_social, nif = await _empresa(db, empresa_id)
    entradas = await _entradas_ejercicio(db, empresa_id, ejercicio)
    desde, hasta = _rango(entradas)
    total_debe, total_haber = _total_lineas(entradas)
    meta = {
        "razon_social": razon_social,
        "nif": nif,
        "ejercicio": ejercicio,
        "desde": desde,
        "hasta": hasta,
        "fecha_generacion": datetime.now(UTC).date().isoformat(),
    }

    resultado: list[dict] = []
    for tipo in tipos:
        if tipo == LibroTipo.diario.value:
            canon = canon_diario(empresa_id, ejercicio, entradas)
            datos: dict = {"entradas": entradas, "total_debe": total_debe, "total_haber": total_haber}
        elif tipo == LibroTipo.mayor.value:
            cuentas = await _datos_cuentas(db, empresa_id, ejercicio)
            canon = canon_mayor(empresa_id, ejercicio, cuentas, desde, hasta)
            datos = {"cuentas": cuentas}
        else:
            rubros = await _datos_cuentas_anuales(db, empresa_id, ejercicio)
            canon = canon_cuentas_anuales(empresa_id, ejercicio, rubros, desde, hasta)
            datos = {"rubros": rubros}

        huella = hashlib.sha256(canon.encode("utf-8")).hexdigest()
        existente = await db.scalar(
            select(LibroOficial).where(
                LibroOficial.empresa_id == empresa_id,
                LibroOficial.ejercicio == ejercicio,
                LibroOficial.tipo == tipo,
            )
        )
        if existente is not None and existente.sha256 == huella:
            resultado.append(
                {
                    "tipo": tipo,
                    "sha256": huella,
                    "url": f"/api/v1/libros/{existente.id}/descarga",
                    "size_bytes": existente.size_bytes,
                    "reusado": True,
                }
            )
            continue

        pdf_bytes = _PDFLibro(tipo).construir(meta, datos)
        if existente is None:
            existente = LibroOficial(
                empresa_id=empresa_id,
                ejercicio=ejercicio,
                tipo=tipo,
                periodo_desde=date(ejercicio, 1, 1),
                periodo_hasta=date(ejercicio, 12, 31),
                contenido_pdf=pdf_bytes,
                sha256=huella,
                size_bytes=len(pdf_bytes),
                generado_por=actor,
            )
            db.add(existente)
        else:
            existente.contenido_pdf = pdf_bytes
            existente.sha256 = huella
            existente.size_bytes = len(pdf_bytes)
            existente.generado_por = actor
        await db.flush()
        await audit_escribir(
            db,
            empresa_id=empresa_id,
            actor=actor or "system",
            action="GENERAR_LIBRO",
            entity="libro_oficial",
            entity_id=str(existente.id),
            payload={"ejercicio": ejercicio, "tipo": tipo, "sha256": huella},
        )
        await db.flush()
        resultado.append(
            {
                "tipo": tipo,
                "sha256": huella,
                "url": f"/api/v1/libros/{existente.id}/descarga",
                "size_bytes": len(pdf_bytes),
                "reusado": False,
            }
        )
    return resultado


async def listar_libros(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    total = await db.scalar(
        select(func.count()).select_from(LibroOficial).where(
            LibroOficial.empresa_id == empresa_id,
            LibroOficial.ejercicio == ejercicio,
        )
    )
    libros = (
        await db.scalars(
            select(LibroOficial)
            .where(
                LibroOficial.empresa_id == empresa_id,
                LibroOficial.ejercicio == ejercicio,
            )
            .order_by(LibroOficial.tipo)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [
            {
                "id": str(b.id),
                "ejercicio": b.ejercicio,
                "tipo": b.tipo.value,
                "sha256": b.sha256,
                "size_bytes": b.size_bytes,
                "url": f"/api/v1/libros/{b.id}/descarga",
            }
            for b in libros
        ],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
    }


async def obtener_libro(db: AsyncSession, *, empresa_id: int, libro_id) -> LibroOficial | None:
    return await db.scalar(
        select(LibroOficial).where(
            LibroOficial.empresa_id == empresa_id,
            LibroOficial.id == libro_id,
        )
    )