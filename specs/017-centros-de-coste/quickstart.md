# Quickstart: Centros de Coste (SPEC-017)

**Branch**: `017-centros-de-coste` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

Validación ejecutable de los escenarios clave. No incluye código de implementación; referencia `contracts/api-contracts.md` y `data-model.md`.

## Prerrequisitos

- Repositorio ContabilidadV1 con backend (FastAPI + asyncpg) y frontend (Next.js) del plan raíz.
- PostgreSQL 16+ con migraciones de los modelos `costcenters/` y columna `centro_coste_id` en `JournalEntryLine` aplicadas.
- Funcionalidad de sesión/autenticación del plan raíz con cabecera de empresa activa.
- pytest instalado en el entorno del backend.

## Escenario 1 — Alta y jerarquía de centros (US1)

### Pasos
1. Levantar backend + frontend (`uvicorn` + `npm run dev`).
2. AUTENTICARSE como contador de **Empresa A**; fijar cabecera de empresa activa = A.
3. `POST /api/v1/centros` con `{codigo: "PROY-X", nombre: "Proyecto X", tipo: "proyecto"}` (resp 201).
4. `POST /api/v1/centros` con `{codigo: "PROY-X-1", nombre: "Línea 1", tipo: "proyecto", parent_id: <id PROY-X>}`.
5. `GET /api/v1/centros/arbol` → ver PROY-X con hijo PROY-X-1.

### Verificación
- Letra a: árbol muestra el par padre/hijo (cerradura materializada `jerarquia_centro`).
- Letra b: el centro NO aparece autenticado como **Empresa B** (`GET /api/v1/centros` → vacío).

```bash
curl -X POST "$BASE/api/v1/centros" -H "Authorization: Bearer $TOKEN" -H "X-Empresa-Activa: A" \
  -H "Content-Type: application/json" -d '{"codigo":"PROY-X","nombre":"Proyecto X","tipo":"proyecto"}'

curl "$BASE/api/v1/centros/arbol" -H "Authorization: Bearer $TOKEN" -H "X-Empresa-Activa: A"

# pytest de fixture equivalente (aislamiento multi-tenant):
pytest backend/tests/integration/test_centro_tenant.py -q
```

Resultado esperado: 201 + árbol con jerarquía; `test_centro_tenant.py` verde (empresa B no ve los centros de A).

## Escenario 2 — Imputación por apunte sin romper balance (US2)

### Pasos
1. Tomar un asiento borrador multilínea de la empresa A (SPEC-002/006) con Debe==Haber.
2. `POST /api/v1/asientos/{asiento_id}/lineas/{linea_id}/imputar` con `{centro_coste_id}`.
3. Consultar el asiento: la línea conserva `centro_coste_id`.
4. Intentar `POST` el mismo endpoint con `centro_coste_id` de otra empresa → 404.

### Verificación
- Importes Debe==Haber del asiento no cambian (dimensión de metadatos).
- La línea quedó vinculada y el asiento intacto y balanceado.

```bash
pytest backend/tests/unit/test_imputacion_balance.py -q
pytest backend/tests/integration/test_imputacion_tenant.py -q
```

Resultado esperado: ambos verdes — balance estricto tras imputar y rechazo cross-tenant.

## Escenario 3 — Rectificación de imputación sobre asiento posteado (US2/inmutabilidad)

### Pasos
1. Asentar (`POSTED`) el asiento anterior.
2. Intentar `DELETE` o `PATCH` la imputación de la línea posteada → **409** (constitución II).
3. Crear un asiento `ADJUSTMENT` enlazado que anule y reimpute al otro centro (motor SPEC-002).

### Verificación
- Tras el `ADJUSTMENT`, el informe muestra la corrección; el asiento original quedó intacto.

```bash
pytest backend/tests/integration/test_rectificacion_centro.py -q
```

Resultado esperado: verde; 409 documentado en el test.

## Escenario 4 — Informe de costes por centro y período (US3)

### Pasos
1. Imputar varias líneas de gasto (Debe) e ingreso (Haber) a centros del árbol (padre e hijos).
2. `GET /api/v1/informes/costes?ejercicio=2026&centro_id=<padre>`.
3. Comparar `subtotal` del padre vs. suma de cada hijo (decisión D1/D5).

### Verificación
- El subtotal del padre incluye a los hijos (agregación exacta con `Decimal`).
- Fecha posterior al cierre (espec. ejercicio) filtra correctamente.

```bash
pytest backend/tests/unit/test_informe_agregacion.py -q
pytest backend/tests/integration/test_informe_tenant.py -q
```

Resultado esperado: verdes; SUM(`NUMERIC`) con 4 decimales, sin errores de redondeo.

## Escenario 5 — Inactivación vs borrado (US2/US1 límites)

### Pasos
1. Intentar `DELETE /api/v1/centros/{id}` de un centro con imputaciones (si existe el endpoint de eliminación física) → rechazado por DB.
2. `POST /api/v1/centros/{id}/inactivar` → 200, estado `inactivo`.
3. Nueva imputación al centro inactivo → 422 (bloqueado).

```bash
pytest backend/tests/integration/test_inactivacion_centro.py -q
```

Resultado esperado: verde; DB impide el borrado físico y la inactivación bloquea nuevas imputaciones.

## Escenario 6 — Vínculo con subvenciones (SPEC-019) (US1/US2 integración)

### Pasos
1. Si existe `Subvencion` de la empresa A (SPEC-019), crear centro `{tipo: "subvencion", subvencion_id: <id>}`.
2. `POST` con `subvencion_id` de empresa B → 409/404.

### Verificación
- Vínculo opcional y validado contra la empresa activa.

```bash
pytest backend/tests/integration/test_centro_subvencion_tenant.py -q
```

Resultado esperado: verde.