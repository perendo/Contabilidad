# Quickstart Validation Guide: Conciliación Bancaria (SPEC-013)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, plan de cuentas con cuenta 572, un asiento 572 POSTED, cuenta bancaria de prueba). Contratos en [contracts/](contracts/), modelo en [data-model.md](data-model.md).

## Scenario 1 — Importar un extracto válido (norma 43/19)

```bash
# 1) Importar fichero de extracto de la cuenta 572 de la empresa activa
curl -X POST "$BASE/api/v1/extractos" -H "Authorization: Bearer $TOK" \
  -F "file=@backend/tests/fixtures/extracto_43_19_valido.txt" -F "layout=norma_43_1919"
# Espera: 201, id, saldo_inicial/final, n_movimientos=3, estado=importado

# 2) Reimportar el mismo fichero
curl -X POST "$BASE/api/v1/extractos" ... # mismo POST
# Espera: 409 {"error":"extracto_duplicado","extracto_existente_id":"..."} — no se dobla carga

# 3) Listar
curl "$BASE/api/v1/extractos" -H "Authorization: Bearer $TOK"
# Espera: items con el extracto importado
```

Validación pytest:
- `test_parser_norma_43`: parsea el fixture y verifica nº de movimientos, saldos y cuadre de control.
- `test_importacion_duplicado`: reimportar el fixture → 409; no hay doble carga.
- `test_importacion_aislamiento`: fichero con cuenta de otra empresa → rechazado (constitución III).

## Scenario 2 — Importar un extracto malformado

```bash
curl -X POST "$BASE/api/v1/extractos" -H "Authorization: Bearer $TOK" \
  -F "file=@backend/tests/fixtures/extracto_43_19_malformado.txt" -F "layout=norma_43_1919"
# Espera: 422 {"error":"layout_invalido","registro":n,"campo":"longitud|cuadre"} — nada persiste
```

Validación pytest:
- `test_importacion_malformado`: rechazo 422; `test_transaccion_atomica`: tras el fallo no hay extracto ni movimientos parciales.

## Scenario 3 — Proponer cruces y conciliar manualmente

```bash
# 1) Abrir conciliación sobre el extracto importado
curl -X POST "$BASE/api/v1/conciliaciones" -H "Authorization: Bearer $TOK" \
  -d '{"cuenta_id":"<cuenta_572>","fecha_inicio":"2026-09-01","fecha_fin":"2026-09-30","extracto_id":"<extracto_id>"}'
# 201, diferencia inicial = importe de apuntes sin cruzar

# 2) Generar propuestas automáticas
curl -X POST "$BASE/api/v1/conciliaciones/$CONC_ID/propuestas" -H "Authorization: Bearer $TOK"
# 200, propuestas por importe+signo; prioridad propuesto si coincide concepto

# 3) Confirmar una propuesta
curl -X POST "$BASE/api/v1/conciliaciones/$CONC_ID/cruces" -H "Authorization: Bearer $TOK" \
  -d '{"cruces":[{"movimiento_id":"<m1>","apunte_id":"<a1>","origen":"auto"}]}'
# 201, cruce confirmado con fecha_cruce y actor; apunte POSTED intacto

# 4) Deshacer antes de archivar
curl -X DELETE "$BASE/api/v1/conciliaciones/$CONC_ID/cruces/$CRUCE_ID" -H "Authorization: Bearer $TOK"
# 204; el cruce vuelve a pendiente
```

Validación pytest:
- `test_matching_importe_signo`: movimientos con importe idéntico y signo contrario a apuntes → propuesta.
- `test_cruce_trazabilidad`: confirmar registra fecha_cruce/usuario; verificar que el `JournalEntry` POSTED no fue modificado (constitución II).
- `test_cruce_aislamiento`: empresa B no ve cruces de A; intento de cruzar desde B → 404.

## Scenario 4 — Confirmar cobro de remesa (acoplamiento SPEC-020)

```bash
# 1) Dado un recibo de remesa (SPEC-020) remesado con su apunte 572 de cobro...
# 2) ...su movimiento aparece como propuesta en la conciliación
curl -X POST "$BASE/api/v1/conciliaciones/$CONC_ID/propuestas" -H "Authorization: Bearer $TOK"
# 3) Al confirmar el cruce:
curl -X POST "$BASE/api/v1/conciliaciones/$CONC_ID/cruces" -H "Authorization: Bearer $TOK" \
  -d '{"cruces":[{"movimiento_id":"<m_cobro>","apunte_id":"<a_cobro>","origen":"auto"}]}'
# 201, "confirmado_por_remesa":true
# 4) Verificar en SPEC-020: GET remesa/recibo → estado=cobrado (consultar contratos SPEC-020)
```

Validación pytest:
- `test_confirmacion_cobro_remesa`: tras confirmar el cruce, `ReciboRemesa.estado=cobrado` y NO se crea un segundo asiento (el apunte ya existía).
- `test_confirmacion_remesa_atomica`: si la notificación a remesas falla, el cruce completo se revierte (misma transacción ACID).

## Scenario 5 — Cerrar con diferencia cero y archivar

```bash
# 1) Conciliar todos los movimientos y apuntes (diferencia = 0.0000)
curl -X POST "$BASE/api/v1/conciliaciones/$CONC_ID/cerrar" -H "Authorization: Bearer $TOK"
# Espera: 200, periodo_id, numero_periodo=1, diferencia="0.0000"

# 2) Intentar deshacer un cruce del período archivado
curl -X DELETE "$BASE/api/v1/conciliaciones/$CONC_ID/cruces/$CRUCE_ID" ...
# Espera: 409 (período archivado inmutable, constitución II)

# 3) Consultar períodos archivados
curl "$BASE/api/v1/periodos-conciliados" -H "Authorization: Bearer $TOK"
# items[0].numero_periodo=1
```

Validación pytest:
- `test_cierre_diferencia_cero`: diferencia `0.0000` → archiva con numero_periodo correlativo.
- `test_cierre_imutabilidad`: DELETE de cruce del período archivado → 409.
- `test_cierre_pendientes`: cierre con pendientes → 409 con lista de pendientes, sin archivar.

## Scenario 6 — Aislamiento multi-empresa (constitución III)

```bash
# Empresa A importa extracto y concilia; empresa B consulta lo mismo
curl -X GET "$BASE/api/v1/extractos/$EXTRACTO_A" -H "Authorization: Bearer $TOK_B"
# Espera: 404 — nunca filtra datos de otra empresa
```