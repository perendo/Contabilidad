# Quickstart: Plantillas de Asientos (SPEC-018)

**Branch**: `018-plantillas-asientos` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

Validación ejecutable de los escenarios clave. No incluye código de implementación; referencia `contracts/api-contracts.md` y `data-model.md`.

## Prerrequisitos

- Repositorio ContabilidadV1 con backend (FastAPI + asyncpg) y frontend (Next.js) del plan raíz.
- PostgreSQL 16+ con migraciones de `templates/` aplicadas.
- Motor de asientos multilínea (SPEC-002/006) y plan de cuentas (SPEC-001) operativos para la empresa de prueba.
- pytest instalado en el entorno del backend.

## Escenario 1 — Crear una plantilla reutilizable (US1)

### Pasos
1. AUTENTICARSE como contador de **Empresa A**; cabecera de empresa activa = A.
2. `POST /api/v1/plantillas` con una línea fija (Debe, cuenta de gasto, `importe_fijo: "1000.0000"`) y una línea variable (Haber, cuenta 572, `variable_id`), declarando la variable.
3. `GET /api/v1/plantillas/{id}` → ver líneas con importe fijo/variable resuelto.

### Verificación
- Resp 201 con `version_actual=1`; la plantilla queda lista para generar.
- Autenticado como **Empresa B**, `GET /api/v1/plantillas` no muestra la plantilla (aislamiento).

```bash
curl -X POST "$BASE/api/v1/plantillas" -H "Authorization: Bearer $TOKEN" -H "X-Empresa-Activa: A" \
  -H "Content-Type: application/json" \
  -d '{"nombre":"Pago proveedor","lineas":[{"orden":1,"cuenta_id":620,"posicion":"debe","importe_fijo":"1000.0000"},{"orden":2,"cuenta_id":572,"posicion":"haber","variable_id":1}],"variables":[{"nombre":"Importe a pagar"}]}'

# pytest de fixture equivalente:
pytest backend/tests/integration/test_plantilla_tenant.py -q
```

Resultado esperado: 201 + 200 detalle; `test_plantilla_tenant.py` verde (B no ve la plantilla de A).

## Escenario 2 — Generar asiento balanceado (US2)

### Pasos
1. `POST /api/v1/plantillas/{id}/generar` con `fecha_asiento` en ejercicio abierto y `variables: {"1": "1000.0000"}`.
2. Consultar el asiento generado (diario): Debe=1000.0000, Haber=1000.0000, número correlativo asignado.

### Verificación
- Asiento balanceado con precisión `Decimal`; en la empresa activa y en el ejercicio correcto.
- Variables ausentes → 422 con listado de faltantes.

```bash
pytest backend/tests/unit/test_generacion_balance.py -q
```

Resultado esperado: 201, balance estricto; verde.

## Escenario 3 — Bloqueos de generación (US2/US1 límites)

### Pasos
1. `POST /generar` con variable sin valor → **422** (faltante).
2. Plantilla con `Sum(Debe) != Sum(Haber)` al resolver → **409** del motor (no cuadra).
3. Desactivar la plantilla (`POST /inactivar`) y re-generar → **409** inactiva.
4. `fecha_asiento` en ejercicio cerrado (SPEC-004) → **409**.

### Verificación
- Ninguna generación inválida produce escritura parcial (atomicidad).

```bash
pytest backend/tests/unit/test_generacion_bloqueos.py -q
```

Resultado esperado: 422/409 documentados y verdes.

## Escenario 4 — Inmutabilidad del generado frente a ediciones (US3)

### Pasos
1. `PATCH /api/v1/plantillas/{id}` cambiando la línea fija a otro importe (resp `version_actual` incrementada).
2. Re-consultar el asiento generado en el Escenario 2 → conserva sus líneas originales.
3. Generar de nuevo → se usa la versión nueva (asiento distinto).

### Verificación
- Los asientos generados no cambian retroactivamente (FR-006/SC-003).

```bash
pytest backend/tests/integration/test_plantilla_versiones_inmutable.py -q
```

Resultado esperado: verde; el asiento original no se modifica y el nuevo usa la versión actual.

## Escenario 5 — Validación de cuentas contra el plan (US2)

### Pasos
1. `PATCH` la plantilla con una `cuenta_id` inexistente o inactiva en el plan de A.
2. Intentar `POST /generar` → **422** (cuenta no válida).
3. Repetir con cuenta válida → genera.

### Verificación
- La cuenta se valida antes de generar (FR-004).

```bash
pytest backend/tests/unit/test_generacion_cuenta_plan.py -q
```

Resultado esperado: 422 → 201; verde.

## Escenario 6 — Aislamiento multi-tenant completo (transversal)

### Pasos
1. Empresa A crea plantilla y genera asiento en su ejercicio abierto.
2. Empresa B intenta: listar plantillas de A, obtener detalle por id, generar desde la plantilla de A → todas **404**.
3. Empresa B genera su propia plantilla → funciona sin colisionar con la numeración de A.

### Verificación
- Numeración correlativa independiente por (empresa, ejercicio) (motor SPEC-002).

```bash
pytest backend/tests/integration/test_plantillas_full_tenant_isolation.py -q
```

Resultado esperado: verde; 404 cross-tenant y numeración independiente.