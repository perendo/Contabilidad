"""SPEC-018 T030: los asientos generados son inmutables ante ediciones."""

from datetime import date
from uuid import UUID

from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from models.templates.asiento_generado import AsientoGenerado
from services.acct.seed import seed_default_pgc
from services.journal.motor import obtener_asiento
from services.templates.generacion import generar_asiento
from services.templates.plantillas import actualizar_plantilla, crear_plantilla


async def _prepare(db, empresa_id: int = 10) -> dict[str, int]:
    db.add(Company(company_id=empresa_id, nif=f"T{empresa_id:08d}", razon_social=f"Empresa {empresa_id}"))
    await db.flush()
    await seed_default_pgc(db, empresa_id)
    cuentas: dict[str, int] = {}
    for code in ("6000", "5720"):
        account = await db.scalar(select(AccountPlan).where(AccountPlan.tenant_id == empresa_id, AccountPlan.code == code))
        assert account is not None
        cuentas[code] = account.id
    return cuentas


async def _plantilla_fija(db, cuentas, importe: str = "100.0000"):
    return await crear_plantilla(
        db,
        empresa_id=10,
        nombre="Fija versionada",
        descripcion=None,
        categoria=None,
        variables=[],
        lineas=[
            {"orden": 1, "cuenta_id": cuentas["6000"], "posicion": "debe", "importe_fijo": importe},
            {"orden": 2, "cuenta_id": cuentas["5720"], "posicion": "haber", "importe_fijo": importe},
        ],
    )


async def test_editar_plantilla_no_altera_generado(db_session):
    cuentas = await _prepare(db_session)
    plantilla = await _plantilla_fija(db_session, cuentas, "100.0000")
    primero = await generar_asiento(
        db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 4, 1), variables={}
    )
    asiento_primero_id = UUID(primero["asiento"]["id"])

    await actualizar_plantilla(
        db_session,
        empresa_id=10,
        plantilla_id=plantilla.id,
        nombre=None,
        descripcion=None,
        categoria=None,
        variables=None,
        lineas=[
            {"orden": 1, "cuenta_id": cuentas["6000"], "posicion": "debe", "importe_fijo": "400.0000"},
            {"orden": 2, "cuenta_id": cuentas["5720"], "posicion": "haber", "importe_fijo": "400.0000"},
        ],
    )
    assert plantilla.version_actual == 2

    anterior = await obtener_asiento(db_session, empresa_id=10, entry_id=asiento_primero_id)
    assert anterior["total_debe"] == "100.0000"
    assert anterior["total_haber"] == "100.0000"

    segundo = await generar_asiento(
        db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 4, 2), variables={}
    )
    assert segundo["asiento"]["total_debe"] == "400.0000"
    assert segundo["version_plantilla"] == 2

    generados = (await db_session.scalars(select(AsientoGenerado).where(AsientoGenerado.plantilla_id == plantilla.id))).all()
    versiones = sorted(item.version_plantilla for item in generados)
    assert versiones == [1, 2]


async def test_editar_solo_nombre_no_incrementa_version(db_session):
    cuentas = await _prepare(db_session)
    plantilla = await _plantilla_fija(db_session, cuentas)
    await actualizar_plantilla(
        db_session,
        empresa_id=10,
        plantilla_id=plantilla.id,
        nombre="Nombre nuevo",
        descripcion="Detalle",
        categoria="otra",
        variables=None,
        lineas=None,
    )
    assert plantilla.nombre == "Nombre nuevo"
    assert plantilla.version_actual == 1
