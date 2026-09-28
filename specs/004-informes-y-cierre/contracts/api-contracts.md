# API Contracts: Contabilidad Habitual, Informes y Cierre de Ejercicio (SPEC-004)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo **`/api/v1`**. La empresa activa se deriva **exclusivamente de la sesión/cabecera autenticada** (definida en SPEC-003); **nunca** se acepta `empresa_id`/`tenant_id` en path ni body. Importes siempre como **strings decimales** (p. ej. `"123.4500"`), nunca números de coma flotante. Errores estándar: `401`, `403`, `404`, `409`, `422`.

## Informes

### GET `/api/v1/reports/trial-balance?date_from={yyyy-mm-dd}&date_to={yyyy-mm-dd}&level={1..5}`
Balance de Sumas y Saldos de la empresa activa.
- Query: `date_from`, `date_to` (obligatorios), `level` (opcional, default 4).
- Reglas: agrega `Debe`/`Haber` por cuenta al nivel indicado (roll-up por prefijo de código del plan); si el plan tiene menos niveles que `level`, se agrega al mayor disponible sin error; **Sum(Debe) == Sum(Haber)** siempre; solo asientos con efecto de la empresa activa (POSTED y CANCELLED con su REVERSAL).
- 200: `{ "date_from", "date_to", "level", "total_debe": "…", "total_haber": "…", "cuadra": true, "items": [ { "codigo", "nombre", "nivel", "suma_debe": "…", "suma_haber": "…", "saldo_deudor": "…", "saldo_acreedor": "…" } ] }`
- 422: rango de fechas ausente o invertido; `level` fuera de 1..5.

### GET `/api/v1/reports/ledger/{account_id}?date_from={yyyy-mm-dd}&date_to={yyyy-mm-dd}`
Libro Mayor de una subcuenta de la empresa activa, con saldo acumulado cronológico.
- Reglas: solo esa subcuenta y la empresa activa; movimientos ordenados por `(fecha, numero)`; saldo acumulado exacto en `Decimal`; subcuenta sin movimientos → `movimientos: []` sin error; subcuenta de otra empresa → 404.
- 200: `{ "cuenta": { "id", "code", "name", "is_selectable" }, "saldo_inicial": "0.0000", "movimientos": [ { "fecha", "numero", "concepto", "debe": "…", "haber": "…", "saldo_acumulado": "…" } ], "saldo_final": "…" }`
- 404: subcuenta inexistente en la empresa activa. 422: rango mal formado.

## Ejercicios contables

### GET `/api/v1/fiscal-years`
Listar ejercicios de la empresa activa (solo lectura; la gestión/alta está fuera de alcance).
- 200: `{ "items": [ { "id", "year", "date_start", "date_end", "is_closed", "closed_at", "regularizacion_entry_id", "cierre_entry_id" } ] }`

## Cierre de ejercicio

### POST `/api/v1/fiscal-years/{year}/close`
Cerrar el ejercicio de forma **atómica**: asiento de regularización (grupos 6/7 → 129), asiento de cierre (saldar balance) y `is_closed = True`, todo en una única transacción.
- Reglas: el desarrollo valida dentro de la transacción: ejercicio existe y abierto (lock `SELECT ... FOR UPDATE` sobre el `fiscal_year`); no quedan asientos `DRAFT` pendientes en el ejercicio (los borradores deben asentarse o anularse antes); los asientos generados quedan `POSTED` e inmutables; auditoría `CLOSE_YEAR` en la misma transacción. Un cierre concurrente falla (segundo → 409).
- 200: `{ "fiscal_year_id", "year", "is_closed": true, "regularizacion_entry_id": "…", "cierre_entry_id": "…", "suma_debe": "…", "suma_haber": "…" }`
- 409: ejercicio ya cerrado (no genera asientos duplicados); cierre concurrente en curso. 404: ejercicio inexistente en la empresa activa. 422: existen asientos `DRAFT` sin asentar en el rango.

## Facturas (entidad persistida por servicio; API de gestión diferida)

En esta feature **no** se exponen endpoints CRUD de facturas (assumption de la spec): la entidad `invoice` se persiste mediante el servicio `invoice_service` y se valida por pruebas unitarias/integración en `backend/tests/unit/test_invoice_*.py` y `backend/tests/integration/test_invoice_*.py`. La numeración correlativa, la precisión exacta y el vínculo con el asiento se verifican a nivel de servicio. La API REST de alta/listado facturas se planificará en una feature posterior.

## Tratamiento de errores (resumen)

| Código | Escenario |
|--------|-----------|
| 401 | Sesión no autenticada o expirada |
| 403 | Sin acceso a la empresa del contexto (o cabecera de empresa ausente) |
| 404 | Ejercicio o subcuenta inexistente en la empresa activa (otra empresa → 404, sin revelar existencia) |
| 409 | Ejercicio ya cerrado; cierre concurrente; conflicto de numeración (`UNIQUE (empresa, ejercicio, numero)` de facturas) |
| 422 | Rango/level mal formado; borradores pendientes al cerrar; validación de factura (total ≠ base + cuota) |
| 400 | Asiento con fecha en ejercicio cerrado o sin ejercicio definido (integración con SPEC-002, FR-007) |

**Notas de seguridad**: la API nunca acepta `empresa_id` desde el cliente; los informes solo operan sobre la empresa activa; el cierre es exclusivo de roles de gestión (ADMIN/ACCOUNTANT) y bloquea `READ_ONLY`.