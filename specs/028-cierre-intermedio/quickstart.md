# Quickstart Validation Guide: Cierre Intermedio y Reapertura Controlada (SPEC-028)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, ejercicios 2025/2026, plan de cuentas con grupos 4/5/6/7, asientos POSTED en los periodos). Contratos en [contracts/api-contracts.md](contracts/api-contracts.md); modelo en [data-model.md](data-model.md).

Convención: `$BASE=http://localhost:8000/api/v1`; `$TOK` = token de sesión; la empresa activa se envía como cabecera `X-Empresa-Id: <empresa_id>`.

## Scenario 1 — Cerrar un mes intermedio con bloqueo de contabilización

```bash
# 1) Cerrar el mes 3 de 2026
curl -X POST "$BASE/cierres/intermedios" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP" -H "Content-Type: application/json" \
  -d '{"ejercicio":2026,"tipo":"MES","periodo":3}'
# Espera: 201, estado=cerrado, balanza.cuadra=true, total_debe==total_haber

# 2) Intentar asentar en el periodo cerrado → rechazo
curl -X POST "$BASE/entradas/journals" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP" -d '{"fecha":"2026-03-15", ...}'
# Espera: 409 periodo_cerrado

# 3) Consultar la balanza del periodo
curl "$BASE/cierres/intermedios/$PERIODO_ID/balanza" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP"
# 200: { "total_debe": "1234.5000", "total_haber": "1234.5000", "lineas": [...] }
```

Validación pytest:
- `backend/tests/unit/test_balanza_cuadre.py`: verifica `Sum(Debe)==Sum(Haber)` en el snapshot.
- `backend/tests/integration/test_cierre_intermedio_flujo.py`: cierra mes, intenta asiento → 409, verifica que el diario no fue mutado por el cierre.
- `backend/tests/integration/test_closing_tenant_isolation.py`: empresa B no ve el cierre de A y puede asentar en sus propios periodos.

## Scenario 2 — Cierre de trimestre con saldo a cero (sin anomalía)

```bash
curl -X POST "$BASE/cierres/intermedios" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP" -d '{"ejercicio":2026,"tipo":"TRIMESTRE","periodo":2}'
# Espera: 201, estado=cerrado, total_debe==total_haber=="0.0000" (cierre sin movimiento, sin anomalía)
```

Validación pytest: `backend/tests/unit/test_balanza_cuadre.py` incluye el caso `periodo_sin_movimientos` → balanza a cero con cuadre.

## Scenario 3 — Cierre anual completo (regularización + cierre + apertura)

```bash
# Requiere todos los periodos intermedios del ejercicio cerrados
curl -X POST "$BASE/cierres/anual" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP" -H "Content-Type: application/json" \
  -d '{"ejercicio":2026}'
# Espera: 201, estado=completado, asiento_regularizacion_id, asiento_cierre_id, asiento_apertura_id
# Los asientos generados son POSTED e inmutables; el ejercicio queda is_closed=true

# Reintento → 409 (idempotencia)
```

Validación pytest:
- `backend/tests/unit/test_cierre_anual_balance.py`: Debe==Haber en regularización, cierre y apertura.
- `backend/tests/integration/test_cierre_anual_flujo.py`: atomicidad + idempotencia + bloqueo del ejercicio.

## Scenario 4 — Reapertura controlada con asiento de rectificación

```bash
# 1) Solicitar reapertura con justificación
curl -X POST "$BASE/cierres/reaperturas" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP" -H "Content-Type: application/json" \
  -d '{"ejercicio":2026,"tipo_periodo":"MES","periodo":3,"motivo":"Error en asiento 3"}'
# 201, estado=pendiente, numero_solicitud correlativo

# 2) Aprobar
curl -X POST "$BASE/cierres/reaperturas/$SOL_ID/aprobar" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP"
# 200, estado=aprobada

# 3) Crear el asiento rectificativo vía SPEC-002 (tipo ADJUSTMENT, fecha en el periodo reabierto)
# 4) Cerrar el ajuste → re-cierre automático
curl -X POST "$BASE/cierres/reaperturas/$SOL_ID/rectificar" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP" -H "Content-Type: application/json" \
  -d '{"asiento_id":"<uuid_asiento_rectificacion>"}'
# 200, estado=cerrada, asiento_rectificacion_id; periodo vuelve a bloquearse
```

Validación pytest:
- `backend/tests/unit/test_reapertura_reversal_balance.py`: asiento ADJUSTMENT balanceado; el asiento original NO se modifica.
- `backend/tests/unit/test_reglas_reapertura.py`: motivo obligatorio, uno a la vez, rechazo si legalizado/formulado.
- `backend/tests/integration/test_reapertura_flujo.py`: ciclo completo solicitud→ajuste→re-cierre.

## Scenario 5 — Rechazos: sin justificación, doble solicitud, ejercicio legalizado

```bash
# Sin motivo → 422
curl -X POST "$BASE/cierres/reaperturas" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP" -d '{"ejercicio":2026,"tipo_periodo":"MES","periodo":2}'
# 422 justificacion_requerida

# Segunda solicitud activa en el mismo periodo → 409
# Reapertura de ejercicio con cuentas anuales formuladas (SPEC-010) → 409 legalizado
```

## Scenario 6 — Aislamiento multi-empresa (constitución III)

```bash
# Empresa A cierra su mes 3
curl -X POST "$BASE/cierres/intermedios" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP_A" -d '{"ejercicio":2026,"tipo":"MES","periodo":3}'

# Empresa B consulta el cierre de A → 404 (nunca filtra datos de otra empresa)
curl "$BASE/cierres/intermedios/$PERIODO_A/balanza" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP_B"
# 404
```

Validación pytest: `backend/tests/integration/test_closing_tenant_isolation.py` cubre cierres, balanzas, reaperturas y asientos cruzados entre empresas A y B.