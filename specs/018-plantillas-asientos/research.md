# Research: Plantillas de Asientos (SPEC-018)

**Branch**: `018-plantillas-asientos` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

Decisiones de diseño (Phase 0) para la feature 018. Cada sección documenta Decisión / Racional / Alternativas. Decisiones marcadas «NEEDS CLARIFICATION» quedan abiertas.

## D1. Modelo de importes: fijos y variables

**Decisión**: Las líneas de plantilla admiten `importe_fijo NUMERIC(18,4) NULL` y `variable_id NULL` (excluyentes: una línea es fija o variable). Las variables se definen como columnas `variable_plantilla` con nombre y tipo `NUMERIC(18,4)`.

**Racional**: FR-002 exige «fijos y variables que se completan al generar». Modelarlo como dos columnas excluyentes da una regla clara: en generación, la línea con variable se sustituye por el valor aportado (validado como `Decimal`); la línea fija se usa tal cual. Los importes parciales en la misma línea (p. ej., «IVA de X») quedan excluidos porque el spec prohíbe fórmulas (Assumption: «no se soportan fórmulas complejas»).

**Alternativas consideradas**:
- Fórmulas expresadas como plantillas de texto («neto + 21 %»): rechazada explícitamente por el spec y frágil (parsing de expresiones).
- Casillas por línea («importe=Débito fijo o variable» sin separación): combinando con discriminantes boolean complica la validación y las versiones.

## D2. Resolución y validación fuera del motor: en el servicio de generación

**Decisión**: El servicio `generacion.py` resuelve la plantilla (sustituye variables, valida cuentas, clasifica línea por posición Debe/Haber con importe 0 desestimado) y **entrega un borrador completo al motor** (SPEC-002/006), que aplica sus reglas (balance, ejercicio, numeración, auditoría). La validación de balance se re-ejecuta dentro de la transacción del motor, nunca solo en el servicio.

**Racional**: El motor debe seguir siendo el único punto de verdad para la persistencia (constitución I, «en el punto más cercano a la persistencia»). El servicio aporta la lógica de plantilla (variables) y el motor verifica la legalidad del asiento resultante. FR-004/FR-005 quedan cubiertos sin duplicar las reglas del motor.

**Alternativas consideradas**:
- El motor conoce el concepto de plantilla y resuelve variables: acopla SPEC-002 a 018 y viola la separación de responsabilidades del plan raíz.
- Validación solo en UI: prohibido por la constitución (I).

## D3. Validación de cuentas contra el plan (SPEC-001)

**Decisión**: Antes de llamar al motor, el servicio valida que cada `cuenta_id` de la línea sea `activa` en el plan de la empresa activa (mismo `empresa_id`). El motor puede aplicar además reglas de cuentas requeridas/permutaciones de su configuración.

**Racional**: FR-004 exige «validar las cuentas contra el plan de la empresa antes de generar». Una cuenta borrada/inactiva (SPEC-001) debe bloquear la generación con 409/422 y un mensaje claro (Edge Case del spec).

**Alternativas consideradas**:
- Validar solo al persistir el asiento: el error llegaría tarde y genérico (viola SC-002 «100 % de las generaciones validan las cuentas»).
- Validar solo en el frontend: nuevamente prohibido.

## D4. Generación solo de plantillas activas; ejercicio abierto

**Decisión**: La generación exige `PlantillaAsiento.estado == activa`. El motor rechaza ejercicios cerrados (SPEC-004) y genera dentro del ejercicio abierto de la empresa (FR-003). `fecha_asiento` aportada por el usuario (junto a las variables) define el período.

**Racional**: Edge Case «plantilla desactivada → se bloquea» y «ejercicio cerrado → bloquea». Estas dos compuertas son independientes y ambas previas a la persistencia.

**Alternativas consideradas**:
- Permitir generar con plantilla inactiva en «solo lectura»: contradice el Edge Case del spec.
- Cerrar ejercicio no considerado: imposible sin violar la dependencia con SPEC-004.

## D5. Versiones y snapshots: asientos generados inmutables

**Decisión**: `PlantillaAsiento` mantiene `version_actual` y un snapshot `asiento_generado` (documento + líneas resueltas persistidas por el motor). Editar la plantilla crea una **versión nueva**; reabrir un asiento generado lee las líneas del propio asiento (inmutable), no de la plantilla. No se mantienen snapshots separados de la plantilla (la versión de la plantilla se referencia por id en el asiento generado).

**Racional**: FR-006/SC-003: los asientos generados permanecen inmutables aunque la plantilla se edite/desactive. Como el asiento genera sus propias líneas (motor), la lectura posterior es del diario; la referencia `plantilla_id`+`version_actual` de la plantilla en el momento de la generación queda en `asiento_generado` para trazabilidad (Rappel gratuito).

**Alternativas consideradas**:
- Snapshot JSON de la plantilla completa por generación: duplica datos y puede desincronizarse con el diario; solo aporta utilidad si la plantilla se borrase (no es el caso, el spec habilita edición/desactivación, no borrado).
- Historial de versiones de plantilla con diff: complejo y sin requisito en el spec (no pide revertir plantillas).

## D6. Activación/desactivación vs borrado físico

**Decisión**: Las plantillas no se borran físicamente; `estado = activa/inactiva` (bloquea nueva generación). La eliminación física de una plantilla con `AsientoGenerado` queda prohibida por FK y por la trazabilidad exigida.

**Racional**: FR-006 conserva asientos generados ligados a la plantilla; borrar la plantilla rompería el vínculo de auditoría y el mensaje de SC-003. El estado `inactiva` cumple el Edge Case «desactivada → bloquea generar».

**Alternativas consideradas**:
- Borrado con `on_delete=SET NULL` en `asiento_generado.plantilla_id`: pierde la trazabilidad del origen (Assumption «el asiento queda ligado a su plantilla»).
- Soft-delete (`deleted_at`): redundante con `estado`.

## D7. Bloqueo de generación si no cuadra o faltan variables

**Decisión**: El servicio detecta **variables sin valor** (422 con listado de faltantes) y el motor, al validar el borrador, rechaza cualquier `Sum(Debe) != Sum(Haber)` (409 con detalle). La generación es atómica: no queda parcial escritura si falla.

**Racional**: Edge Case «¿no cuadra? → se impide generar; el motor exige balance» y «¿variable no completa? → se bloquea con mensaje de faltante». El doble control (servicio por UX, motor por ley) es consistente con D2/constitución I.

**Alternativas consideradas**:
- El motor resuelve las variables (D2): duplica la lógica y complica los mensajes.
- Permitir generar borrados desbalanceados persistibles temporalmente: prohibido.

## D8. Trazabilidad del asiento generado: `AsientoGenerado`

**Decisión**: El asiento `POSTED` generado se enlaza en `asiento_generado` (empresa_id, asiento_id FK, plantilla_id FK, version_actual, variables_aportadas JSON con `Decimal` como string, fecha_generacion). El vínculo es inmutable y se escribe en la misma transacción ACID.

**Racional**: Assumption «el asiento es inmutable, ligado a su plantilla y herramienta de trazabilidad». Guardar las variables aportadas permite auditar qué entrada produjo cada asiento sin depender de futuras ediciones de la plantilla (coherente con D5).

**Alternativas consideradas**:
- Solo `plantilla_id` sin variables: la huella no es reproducible (¿qué valores se pidieron?).
- Almacenar en el audit log genérico: sin FK navegable para informes.

## D9. Permisos y multi-tenancy estricto

**Decisión**: Plantillas por `empresa_id` en PK/índices; toda operación lee/escribe con el `empresa_id` de sesión; el acceso sigue SPEC-015 (crear/editar/generar contador/admin; consultar roles analistas). Cualquier referencia cross-tenant → 404.

**Racional**: FR-007 y constitución III. La matriz de permisos es dependencia declarada del spec.

**Alternativas consideradas**:
- Plantillas compartidas entre empresas: contradice FR-001/FR-007 («por empresa»).

## D10. UX de entrada contable optimizada (constitución, frontend)

**Decisión**: La UI de generación presenta las variables como campos numéricos pre-poblados con la precedencia del motor (p. ej., rellenar la variable del Haber como complemento si coincide con saldo en Debe), con atajo de teclado y confirmación antes de generar. Sigue siendo informativa: el backend es quien valida.

**Racional**: Constitución (Normas del Frontend) exige entrada optimizada por teclado. La pre-ayuda «rellenar el saldo de la variable restante» reduce errores sin delegar la validación de balance (que solo hace el backend).

**Alternativas consideradas**:
- UI sin ayuda de balance: peor ergonomía; el spec pide agilizar operación repetitiva.

---

## Decisiones en condicional (NEEDS CLARIFICATION si no se confirman)

- **Campos adicionales en cabecera de plantilla**: se modela `descripcion` (libre) y `categoria` (opcional, agrupación). Si el plan raíz exige taxonomía propia, NEEDS CLARIFICATION.
- **Multi-moneda**: fuera del alcance del spec (asume moneda funcional de la empresa). Si SPEC-016 (multi-divisa) avanza, la línea de plantilla deberá admitir moneda; hoy se deja por defecto la de la empresa.
- **Reutilización de `AsientoGenerado`**: si el plan raíz ya define un modelo de «origen/trazabilidad» para asientos, se sustituye la tabla por referencia al existente. Pendiente de confirmar.