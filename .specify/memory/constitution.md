<!-- SYNC IMPACT REPORT
  Version change: (blank scaffold template) -> 1.0.0
  Modified principles: N/A (first ratification with real content)
  Added sections:
    - Core Principles (I-V; I-IV from Principios Inmutables de Dominio Contable,
      V derived from Criterios de Aceptacion y Auditoria)
    - Stack Tecnologico y Normas de Desarrollo del Backend (FastAPI + PostgreSQL)
    - Normas del Frontend (Next.js)
    - Criterios de Aceptacion y Auditoria
    - Governance
  Removed sections: none
  Deferred TODOs: none
    - RATIFICATION_DATE resolved to 2026-09-16 (constitution ratified today).
-->

# Sistema de Contabilidad Multiempresa (ContabilidadV1) Constitution

## Core Principles

### I. Partida Doble Estricta (NON-NEGOTIABLE)

Todo asiento contable (`JournalEntry`) MUST estar desglosado en apuntes
(`JournalEntryLine`) cuya suma total del Debe sea exactamente igual a la suma
total del Haber dentro de una misma transacción ACID. Queda PROHIBIDO producir,
persistir o exponer un asiento desbalanceado en cualquier estado del ciclo de
vida de la transacción. La validación de balance MUST ejecutarse en el backend,
en el punto más cercano a la persistencia, y nunca delegarse exclusivamente en
la UI. Racional: la partida doble es el invariante fundamental del dominio; un asiento
desbalanceado invalida libros contables, reportes y cierres.

### II. Inmutabilidad del Diario

Los asientos confirmados o asentados (`POSTED`) son inmutables: queda PROHIBIDO
su `UPDATE` o `DELETE` tanto a nivel de API como de base de datos. Toda
corrección posterior MUST realizarse mediante un asiento de anulación o
rectificativo (`REVERSAL` / `ADJUSTMENT`) debidamente enlazado con el asiento
original. Racional: la no inmutabilidad compromete la integridad histórica y la
auditoría del diario. La restricción MUST quedar garantizada a nivel de base de
datos (constraints/triggers), no solo mediante disciplina de aplicación.

### III. Multi-tenancy Estricto

Aislamiento total de datos por `tenant_id` / `empresa_id` a nivel de base de
datos o esquema. Ninguna consulta (SELECT), lectura o mutación
(INSERT/UPDATE/DELETE) puede ejecutarse sin el filtro explícito de la empresa
activa del contexto. El `empresa_id` MUST derivarse exclusivamente del contexto
autenticado y de sesión, nunca de datos no confiables recibidos del cliente, y
MUST formar parte de claves, índices y filtros de toda operación de datos.
Racional: garantiza el secreto y la integridad entre empresas; el aislamiento
MUST verificarse con pruebas de integración que demuestren la imposibilidad de
acceder a datos de otra empresa.

### IV. Numeración y Correlatividad

Secuencia estricta y sin saltos para los números de asiento y los números de
factura, por ejercicio contable y por empresa. La asignación del número
consecutivo MUST ocurrir de forma atómica dentro de la misma transacción en que
se persiste el documento, sobre una secuencia bloqueada o equivalente que
garantice unicidad e integridad bajo concurrencia. El sistema MUST detectar y
rechazar intentos de emitir números duplicados, reutilizados u omitidos.
Racional: correlatividad y ausencia de saltos son requisitos legales y de
auditoría; sin bloqueo atómico la concurrencia rompería la secuencia.

### V. Pruebas Obligatorias como Criterio de Aceptación (NON-NEGOTIABLE)

Ninguna tarea se considera finalizada sin pruebas automáticas (pytest,
unitarias y de integración) que verifiquen, como mínimo: (a) el balance estricto
de la partida doble y (b) la imposibilidad de acceder a datos de otra empresa
(aislamiento multi-tenancy). Ningún merge, despliegue ni cierre de tarea puede
omitir esta verificación. Racional: estas dos verificaciones protegen los tres
invariantes más críticos del sistema (balance, aislamiento y auditabilidad).

## Stack Tecnológico y Normas de Desarrollo del Backend (FastAPI + PostgreSQL)

- Manejo estricto de importes: queda PROHIBIDO el uso de tipos `float` para
  importes contables. MUST usarse `Decimal` en Python y `NUMERIC(18, 4)` en
  PostgreSQL para todos los importes y cálculos monetarios del dominio. La
  aritmética contable MUST ejecutarse con precisión decimal (contexto de alta
  precisión), nunca en coma flotante.
- Trazabilidad y auditoría (Audit Logs): registro obligatorio de cada operación
  de escritura (usuario, timestamp UTC, IP, tipo de operación y delta/payload
  de la entidad). El log de auditoría es inmutable, MUST persistirse en la misma
  transacción ACID que la operación auditada y no puede omitirse bajo ninguna
  condición de error de escritura principal.
- Manejo de transacciones: la indivisibilidad MUST garantizarse con un boundary de
  transacción ACID único y explícito. En este repositorio ese boundary es el generador
  de sesión de la capa de datos (`get_db`), que abre la transacción al entrar,
  confirma al final de la petición y revierte ante excepción; los servicios MUST hacer
  `flush()` dentro de ese boundary y MUST NOT abrir su propia transacción
  (`async with session.begin()`), porque eso rompería la atomicidad con la operación
  que la invoca. Queda PROHIBIDO persistir una cabecera sin sus líneas, o viceversa,
  fuera de esa transacción ACID.

## Normas del Frontend (Next.js)

- Gestión de contexto de empresa: el estado global o la sesión del usuario MUST
  mantener el `empresa_id` activo y enviarlo en las cabeceras de cada petición
  HTTP hacia FastAPI. Un cambio de empresa MUST recalcular el contexto y la
  sesión sin arrastrar datos de la empresa anterior a la posterior.
- Entrada contable optimizada: MUST diseñarse la UI priorizando la usabilidad
  por teclado (teclas de acceso rápido, tabulación fluida y atajos) para la
  introducción masiva de asientos. La validación de balance en la UI es
  informativa y nunca reemplaza la validación obligatoria del backend.

## Criterios de Aceptación y Auditoría

- Ninguna tarea se considerará finalizada si no incluye pruebas automáticas
  (unitarias y de integración en pytest) que verifiquen el balance estricto de
  la partida doble y la imposibilidad de acceder a datos de otra empresa.
- Toda entrega MUST superar las pruebas, el typecheck y el linter configurados
  en el repositorio antes de declararse completa o candidata a despliegue.
- Toda revisión de código (PR) MUST verificar la conformidad de los cambios con
  esta constitución antes de su fusión.

## Governance

- Esta constitución prevalece sobre cualquier otra práctica, documento o
  convención del proyecto; las normas aquí contenidas no pueden relajarse sin
  enmienda formal.
- Las enmiendas requieren documentación del impacto, aprobación y plan de
  migración, y siguen el versionado semántico de esta constitución: MAJOR para
  eliminación o redefinición incompatible de principios; MINOR para nuevos
  principios o secciones; PATCH para aclaraciones y correcciones.
- Revisión de cumplimiento: esperada en cada planificación de sprint o ciclo de
  desarrollo; todos los PRs y tareas ejecutadas según el flujo de desarrollo
  (`/speckit.specify` y subsiguientes) MUST alinear sus entregables con estos
  principios y criterios de aceptación.
- Cualquier código, especificación o tarea en conflicto con esta constitución
  queda sin efecto hasta su ajuste o enmienda.

**Version**: 1.0.1 | **Ratified**: 2026-09-16 | **Last Amended**: 2026-09-27