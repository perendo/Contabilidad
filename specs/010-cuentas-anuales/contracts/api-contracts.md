# API Contracts: Cuentas Anuales (SPEC-010)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1/...` (empresa activa derivada de sesion en cabecera; empresa_id nunca en body/path como dato de seleccion). Respuestas JSON; importes como strings decimales, nunca numeros de coma flotante. Los informes calculados se devuelven con su estructura de masas y el flag de cuadre verificado en backend.

## Balance de Situacion

### GET `/api/v1/cuentas-anuales/{ejercicio}/balance`
Formular (calcular) el Balance de Situacion provisional o del ejercicio.
- Query params: `comparativo=bool` (default false), `modo=provisional|oficial` (default provisional).
- 200: `{ "ejercicio", "cuadre": true, "total_activo", "total_pasivo", "total_patrimonio", "masas": [{ "nombre", "importe", "partidas": [...] }], "comparativo_anterior": null }`
- 422: `balance_descuadrado` (cuadre no verificado).
- 409: `ejercicio_cerrado_descuadre` si el ejercicio cerrado no cuadra, revision manual.

## Cuenta de Perdidas y Ganancias

### GET `/api/v1/cuentas-anuales/{ejercicio}/pyg`
Formular la Cuenta de Perdidas y Ganancias.
- Query params: `modo=provisional|oficial`.
- 200: `{ "ejercicio", "total_ingresos", "total_gastos", "resultado_ejercicio", "resultado_cierre", "coincide_cierre": true, "partidas": [...] }`
- 409: `descuadre_cierre` (resultado != cierre) en modo oficial, bloqueo de formulacion.

## Estado de Flujos de Efectivo

### GET `/api/v1/cuentas-anuales/{ejercicio}/efe`
Formular el EFE por actividades.
- Query params: `modo=provisional|oficial`.
- 200: `{ "ejercicio", "saldo_inicial_tesoreria", "actividades": { "operativa": { "cobros", "pagos", "neto" }, "inversion": {...}, "financiacion": {...} }, "saldo_final_tesoreria", "variacion_balance", "cuadre": true }`
- 409: `efe_descuadrado` en modo oficial (no cuadra con variacion del balance).

### PATCH `/api/v1/cuentas-anuales/{ejercicio}/efe/clasificacion`
Reasignar la clasificacion por actividad de un movimiento de tesoreria antes de formular.
- Body: `{ "movimiento_id": "<uuid>", "actividad": "operativa" | "inversion" | "financiacion", "motivo": "string" }`
- 200: `{ "movimiento_id", "actividad" }`
- 409: si el ejercicio esta formalmente formulado ya.

## Formulacion Oficial

### POST `/api/v1/cuentas-anuales/{ejercicio}/formular`
Formular oficialmente las cuentas anuales del ejercicio cerrado.
- Body: `{ "observaciones": "string" }`
- Reglas: ejercicio debe estar `cerrado`, balance y PyG deben cuadrar, EFE si esta configurado tambien. Genera `FormulacionCuentasAnuales` inmutable con hash sha256 del contenido.
- 201: `{ "formulacion_id", "numero_formulacion", "fecha_formulacion", "contenido_hash", "estado": "formulada" }`
- 409: `ejercicio_no_cerrado`, `balance_no_cuadra`, `pyg_no_cuadra`, `efe_no_cuadra`, `ya_formulada`.

### POST `/api/v1/cuentas-anuales/{ejercicio}/anular-formulacion`
Anular una formulacion oficial (requiere permiso de administrador).
- Body: `{ "motivo": "string" }`
- 200: `{ "formulacion_id", "estado": "anulada", "motivo_anulacion" }`
- 409: `sin_formulacion`, `ejercicio_no_cerrado`.

### GET `/api/v1/cuentas-anuales/{ejercicio}/formulaciones`
Historico de formulaciones del ejercicio (incluye anuladas con trazabilidad).
- 200: `{ "items": [{ "formulacion_id", "numero_formulacion", "fecha", "usuario", "estado", "contenido_hash" }] }`

## Configuracion

### POST/PATCH `/api/v1/cuentas-anuales/configuracion`
Configurar la agrupacion de cuentas para balance/PyG/EFE por empresa.
- Body: `{ "informe_tipo": "BALANCE|PYG|EFE", "agrupaciones": [{ "agrupacion_id", "cuenta_ini", "cuenta_fin", "actividad_efe" }] }`
- 200: `{ "configuraciones_creadas": n }`

## Tratamiento de errores

- `401/403`: autenticacion/permisos (SPEC-003).
- `404`: recurso inexistente en la empresa activa.
- `409`: conflicto de estado (ejercicio no cerrado, balance descuadrado, formulacion duplicada).
- `422`: validacion de negocio (descuadre, cuentas sin agrupar).
