"""SEPA Direct Debit PAIN.008.001.02 generator.

Produces a valid XML document grouped by charge date (ReqdColltnDt) and applies
the EPC presentation deadlines (CORE D-2 / B2B D-1 business days) before trusting
the caller to emit (FR-004, SC-007).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from xml.etree import ElementTree

from models.ar.tercero import Tercero
from models.treasury.mandato_sepa import MandatoSepa
from models.treasury.recibo_remesa import ReciboRemesa
from models.treasury.remesa import Remesa, TipoAdeudo
from services.remittance.seleccion import Emisor

NS = "urn:iso:std:iso:20022:tech:xsd:pain.008.001.02"
ElementTree.register_namespace("", NS)

PLAZO_CORE_DIAS = 2
PLAZO_B2B_DIAS = 1


class PlazoPresentacionError(Exception):
    def __init__(self, tipo: TipoAdeudo, fecha_cargo: date, minima: date) -> None:
        super().__init__(
            f"fecha de cargo {fecha_cargo.isoformat()} no cumple el plazo {tipo.value} "
            f"(presentación mínima {minima.isoformat()})"
        )


def fecha_presentacion_minima(tipo: TipoAdeudo, desde: date | None = None) -> date:
    """First business date on or after `desde` + SLA business days."""
    desde = desde or datetime.now(timezone.utc).date()
    pendientes = (
        PLAZO_CORE_DIAS if tipo == TipoAdeudo.CORE else PLAZO_B2B_DIAS
    )
    candidata = desde
    while pendientes > 0:
        candidata += timedelta(days=1)
        if candidata.weekday() < 5:
            pendientes -= 1
    return candidata


def validar_plazo_presentacion(
    tipo: TipoAdeudo, fecha_cargo: date, hoy: date | None = None
) -> None:
    """Raise PlazoPresentacionError if the charge date misses the SLA."""
    minima = fecha_presentacion_minima(tipo, hoy)
    if fecha_cargo < minima:
        raise PlazoPresentacionError(tipo, fecha_cargo, minima)


def _e(parent: ElementTree.Element, tag: str, text: str = "") -> ElementTree.Element:
    element = ElementTree.SubElement(parent, tag)
    element.text = text
    return element


def _importe_cuatro(importe: Decimal) -> str:
    return f"{Decimal(importe).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP):f}"


def _importe_dos(importe: Decimal) -> str:
    return f"{Decimal(importe).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def _totales(recibos: list[ReciboRemesa]) -> tuple[int, Decimal]:
    total = sum((recibo.importe for recibo in recibos), Decimal(0))
    return len(recibos), total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _escribir_instruccion(
    drct_dbt_tx_inf: ElementTree.Element,
    recibo: ReciboRemesa,
    deudor: Tercero | None,
    mandato: MandatoSepa | None,
) -> None:
    pmt_id = _e(drct_dbt_tx_inf, "PmtId")
    _e(pmt_id, "EndToEndId", recibo.recibo_num)

    instd_amt = ElementTree.SubElement(drct_dbt_tx_inf, "InstdAmt")
    instd_amt.set("Ccy", "EUR")
    instd_amt.text = _importe_dos(recibo.importe)

    drct_dbt_tx = _e(drct_dbt_tx_inf, "DrctDbtTx")
    mndt = _e(drct_dbt_tx, "MndtRltdInf")
    if mandato is not None:
        _e(mndt, "MndtId", mandato.mandato_ref)
        _e(mndt, "DtOfSgntr", mandato.fecha_firma.isoformat())
    _e(mndt, "AmdmntInd", "false")

    if deudor is not None and deudor.bic:
        dbtr_agt = _e(drct_dbt_tx_inf, "DbtrAgt")
        fin_instn = _e(dbtr_agt, "FinInstnId")
        _e(fin_instn, "BIC", deudor.bic)
    if deudor is not None:
        dbtr = _e(drct_dbt_tx_inf, "Dbtr")
        _e(dbtr, "Nm", deudor.nombre)
    dbtr_acct = _e(drct_dbt_tx_inf, "DbtrAcct")
    dbtr_acct_id = _e(dbtr_acct, "Id")
    _e(dbtr_acct_id, "IBAN", recibo.iban)


def generar_sepa(
    remesa: Remesa,
    recibos: list[ReciboRemesa],
    deudores: Mapping[uuid.UUID, Tercero],
    mandatos: Mapping[uuid.UUID, MandatoSepa],
    emisor: Emisor,
    hoy: date | None = None,
    *,
    validar: bool = True,
) -> bytes:
    """Generate the PAIN.008.001.02 document, grouped by charge date."""
    if validar:
        for recibo in recibos:
            validar_plazo_presentacion(remesa.tipo_adeudo, recibo.fecha_cargo, hoy)

    root = ElementTree.Element(f"{{{NS}}}Document")
    initn = ElementTree.SubElement(root, "CstmrDrctDbtInitn")

    grp_hdr = ElementTree.SubElement(initn, "GrpHdr")
    total_txs, ctrl_sum = _totales(recibos)
    msg_id = f"REM-{remesa.empresa_id:03d}-{remesa.numero_remesa:06d}"
    _e(grp_hdr, "MsgId", msg_id)
    _e(
        grp_hdr,
        "CreDtTm",
        datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z",
    )
    _e(grp_hdr, "NbOfTxs", str(total_txs))
    _e(grp_hdr, "CtrlSum", _importe_dos(ctrl_sum))
    initg = _e(grp_hdr, "InitgPty")
    _e(initg, "Nm", emisor.nombre)

    grupos: dict[date, list[ReciboRemesa]] = {}
    for recibo in recibos:
        grupos.setdefault(recibo.fecha_cargo, []).append(recibo)

    for indice, (fecha_cargo, grupo) in enumerate(sorted(grupos.items()), start=1):
        pmt_inf = ElementTree.SubElement(initn, "PmtInf")
        _e(pmt_inf, "PmtInfId", f"{msg_id}-{indice:03d}")
        _e(pmt_inf, "PmtMtd", "DD")
        _e(pmt_inf, "BtchBookg", "true")
        n_txs, ctrl = _totales(grupo)
        _e(pmt_inf, "NbOfTxs", str(n_txs))
        _e(pmt_inf, "CtrlSum", _importe_dos(ctrl))
        pmt_tp = _e(pmt_inf, "PmtTpInf")
        svc = _e(pmt_tp, "SvcLvl")
        _e(svc, "Cd", "SEPA")
        lcl = _e(pmt_tp, "LclInstrm")
        _e(lcl, "Cd", remesa.tipo_adeudo.value)
        _e(pmt_inf, "ReqdColltnDt", fecha_cargo.isoformat())
        cdtr = _e(pmt_inf, "Cdtr")
        _e(cdtr, "Nm", emisor.nombre)
        cdtr_acct = _e(pmt_inf, "CdtrAcct")
        cdtr_acct_id = _e(cdtr_acct, "Id")
        _e(cdtr_acct_id, "IBAN", emisor.iban)
        if emisor.bic:
            cdtr_agt = _e(pmt_inf, "CdtrAgt")
            cdtr_agt_fin = _e(cdtr_agt, "FinInstnId")
            _e(cdtr_agt_fin, "BIC", emisor.bic)
        for recibo in grupo:
            _escribir_instruccion(
                ElementTree.SubElement(pmt_inf, "DrctDbtTxInf"),
                recibo,
                deudores.get(recibo.tercero_id),
                mandatos.get(recibo.tercero_id),
            )

    xml_bytes = ElementTree.tostring(root, encoding="UTF-8", xml_declaration=True)
    return xml_bytes


def sha256_fichero(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()