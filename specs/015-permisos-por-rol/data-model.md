# Data Model: Matriz de Permisos por Rol (SPEC-015)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003) en PK/índices y filtros; se deriva de sesión.
- Este módulo no almacena importes monetarios.
- Los eventos de auditoría de acceso son inmutables (sin UPDATE/DELETE) y se persisten en la misma transacción ACID que la operación auditada (o su denegación).

## PermisoOperacion

Catálogo estático de operaciones por módulo (semilla; la API no crea permisos dinámicos).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| modulo | VARCHAR(40) | identificador del módulo (acct, ar, treasury, bank, inmovilizado, divisas, rbac, ...) |
| operacion | ENUM | `ver`, `crear`, `editar`, `aprobar`, `importar_exportar`, `configurar`, `baja`, `cerrar` |
| descripcion | VARCHAR(255) | descripción legible |
| requiere_datos_contables | BOOLEAN | si true, todo allow/deny sobre esta operación se audita (FR-005) |

**Validación**: único por `(modulo, operacion)`; el catálogo es semilla gestionable por migración, no por API de negocio.

## Rol

Rol de un usuario dentro de una empresa (persistido por SPEC-003; esta feature lo referencia).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| nombre | ENUM | `ADMIN`, `ACCOUNTANT`, `READ_ONLY` (base) o personalizado VARCHAR |
| es_global_flag | BOOLEAN | informativo de SPEC-003; no otorga permisos por sí mismo |

**Nota**: el rol y su vínculo usuario-empresa-rol los gobierna SPEC-003; la matriz de esta feature referencia `(empresa_id, rol_id)`.

## MatrizPermiso

Concesión de una operación a un rol en una empresa. Ausencia de fila ⇔ denegado por defecto.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | matriz de la empresa activa; nunca se evalúa cruzando empresas |
| rol_id | UUID FK → Rol (SPEC-003) | rol de la empresa |
| permiso_id | UUID FK → PermisoOperacion | operación del catálogo |
| concesion_id | UUID FK NULL | registro de auditoría de la concesión si aplica |

**Validaciones**: único por `(empresa_id, rol_id, permiso_id)` (constraint UNIQUE + índice para evaluación); el rol y el permiso deben existir (FK); nada se "deniega" explícitamente (ausencia = denegado).

## EventoAuditoriaAcceso

Registro inmutable de intentos denegados y permisos concedidos sobre datos contables.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| usuario_id | UUID FK → SPEC-003 | actor |
| rol_id | UUID FK → SPEC-003 | rol efectivo en la evaluación |
| modulo | VARCHAR(40) | |
| operacion | ENUM | misma enumeración de PermisoOperacion |
| resultado | ENUM | `allow` / `deny` |
| motivo | ENUM | `sin_permiso`, `sin_rol`, `operacion_inexistente`, `sin_empresa`, `concedido` |
| timestamp_utc | TIMESTAMPTZ | UTC (constitución) |
| ip | VARCHAR(45) | |
| payload | JSONB | delta/payload contable afectado como strings decimales si aplica |

**Validación**: sin UPDATE/DELETE (constitución II aplicada a la auditoría; enforced con trigger/constraint de rol no auto-suscribir); se escribe en la misma transacción ACID que la operación o la denegación.

## Resumen de relaciones

```
PermisoOperacion 1 ── n MatrizPermiso
Rol (SPEC-003) 1 ── n MatrizPermiso
Empresa (SPEC-003) 1 ── n MatrizPermiso (empresa_id)
Empresa (SPEC-003) 1 ── n EventoAuditoriaAcceso (empresa_id)
Rol (SPEC-003) 1 ── n EventoAuditoriaAcceso (rol efectivo)
```