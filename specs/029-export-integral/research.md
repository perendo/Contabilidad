# Research: Export Integral del Tenant (Backup y Portabilidad) (SPEC-029)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Formato del archivo de exportación (ZIP con JSON por bloque)

- **Decision**: El archivo de exportación es un **ZIP** que contiene: (1) `manifest.json` con inventario de bloques, metadatos de la exportación y huella del propio archivo; (2) un directorio `bloques/` con un fichero JSON por bloque de datos exportado (`bloques/cuentas.json`, `bloques/asientos.json`, etc.); (3) si la exportación es de tipo SII, un directorio `datos_sii/` con registros preparados para el SII de la AEAT. Los ficheros del ZIP están en formato **JSON** (no XML) para preservar la estructura jerárquica de los datos y la serialización correcta de `Decimal` strings. El manifiesto interior (`manifest.json`) es el que lleva la huella SHA-256 del fichero completo.
- **Rationale**: ZIP es estándar, comprimido, ampliamente soportado; JSON por bloque facilita la verificación independiente de cada sección y la reutilización de datos por bloques; la spec (Assumption) indica "formato estándar (JSON o XML) y comprimido (ZIP)".
- **Alternatives considered**: XML plano (pierde la compresión por bloque, más complejo de parsear en verificación); JSON único sin ZIP (fichero muy grande para tenants grandes, sin compresión); CSV por bloque (sin jerarquía de datos). Se descartaron por inadecuación.

## D2. Catálogo de bloques de datos (FR-004)

- **Decision**: Se define un catálogo extensible `BLOQUES` en `services/export/bloques.py` con los siguientes bloques obligatorios para la exportación INTEGRAL: `plan_cuentas` (SPEC-001: cuentas), `plan_cuentas_versiones` (SPEC-025: versiones del PGC), `asientos` (SPEC-002: JournalEntry), `apuntes` (SPEC-002: JournalEntryLine), `terceros` (SPEC-008), `facturas` (SPEC-007), `lineas_factura` (líneas de factura), `vencimientos` (SPEC-011), `cobros_pagos` (SPEC-011), `remesas` (SPEC-020), `devoluciones` (SPEC-020), `amortizaciones` (SPEC-014), `cierres` (SPEC-028 + CierreEjercicio + PeriodoCerrado + BalanzaPeriodo), `presupuestos` (SPEC-026), `previsiones` (SPEC-027), `libros_iva` (SPEC-012), `configuracion` (config general de la empresa). Bloques opcionales: `datos_sii` (cuando `tipo= SII`). Cada bloque declara: función query (async generator paginado), nombre de fichero en el ZIP, entidades incluidas, y posible filtro por rango de ejercicio.
- **Rationale**: Cumple FR-004 con la lista explícita de bloques; el catálogo extensible permite añadir bloques futuros sin cambiar el servicio; la paginación evita volcar toda la tabla en RAM.
- **Alternatives considered**: Generar un JSON único de todo el tenant (inmanejable para grandes volúmenes); omitir algunos bloques (incumple la FR-004 que enumera específicamente los bloques); ambas se descartaron.

## D3. Filtro por rango de ejercicios (FR-005)

- **Decision**: La exportación INTEGRAL acepta parámetros opcionales `ejercicio_desde` y `ejercicio_hasta` (años). Cada bloque que tiene un campo `ejercicio` o `fecha` aplica el filtro; los bloques atemporales (`configuracion`, `plan_cuentas` completo, `terceros`) se exportan íntegros independientemente del rango. Si no se especifica rango, se exporta el tenant completo. El `ManifestBloque` registra `ejercicio_min` y `ejercicio_max` de los datos exportados para verificación.
- **Rationale**: Cumple FR-005 y el edge case de la spec ("¿Qué ocurre si la empresa tiene datos de varios ejercicios? → Se exporta todo; el usuario puede filtrar por rango").
- **Alternatives considered**: Rango obligatorio (incumple la exportación completa del tenant como backup de portabilidad); filtro por fechas exactas (más granular pero más complejo para el usuario).

## D4. Multi-tenancy en export: aislamiento de datos

- **Decision**: Cada consulta de cada bloque se ejecuta con `WHERE empresa_id = :empresa_id` derivado de la sesión autenticada; la función `recopilar_bloque` recibe la sesión y `empresa_id` y lo aplica en cada query; el ZIP solo contiene datos de la empresa activa. El `Exportacion` lleva `empresa_id` en PK y en todos los accesos. La descarga del fichero requiere que la petición pertenezca a la misma empresa activa (404 cross-tenant). Las pruebas de aislamiento verifican que el ZIP de empresa A contiene 0 registros de empresa B en todos los bloques.
- **Rationale**: Cumple FR-003 (excluir datos de otros tenants) y la constitución III; el filtro se aplica a nivel de consulta SQL y se verifica con tests.
- **Alternatives considered**: Exportar todo el tenant de todas las empresas y filtrar post-hoc (ineficiente y violate de aislamiento); exportar solo el esquema (incumple la portabilidad de datos).

## D5. Generación del ZIP y streaming (performance)

- **Decision**: El ZIP se genera **sincrónicamente en el request** (MVP) usando `zipfile.ZipFile` en modo de escritura (`ZIP_DEFLATED`), iterando por cada bloque en orden determinista (`sorted(bloques.keys())`), paginando las queries por bloque en lotes de 10.000 registros para evitar volcar tablas completas en RAM. El SHA-256 se calcula sobre el binario del ZIP completo en memoria. Para tenants muy grandes (> 50 MB), se ofrecerá una opción asíncrona (worker/cola) y streaming de lectura; MVP usa `< 100 MB` como límite razonable. Se devuelve el ZIP con `Content-Type: application/zip` y `Content-Disposition: attachment`.
- **Rationale**: Coherente con el patrón de SPEC-020 (emisión síncrona de fichero SEPA < 5 MB) y con la escala esperada (10.000 asientos < 30 s); streaming previene OutOfMemory para volúmenes grandes.
- **Alternatives considered**: Worker asíncrono con cola y notificación (más complejo para el usuario; MVP lo difiere); generar en frontend (excluye el control de multi-tenancy en backend).

## D6. Huella y manifiesto de integridad (FR-002)

- **Decision**: El manifiesto interior (`manifest.json`) contiene: versión del formato (`formato_version`), fecha de generación UTC, tenant_id (empresa_id), ejercicio_desde/hasta, lista de bloques con (nombre, entidades_exportadas, conteo_registros, sha256_del_bloque), y el campo `sha256_fichero` que es el hash SHA-256 del contenido completo del ZIP (calculado tras construir el ZIP binario). La verificación (US2) recomputa el SHA-256 del ZIP recibido y lo compara con `sha256_fichero` del manifiesto interior; additionally compara que el conteo de registros de cada bloque coincide con los registros almacenados en `ManifiestoBloque`.
- **Rationale**: Cumple SC-002 ("100% de exportaciones generan huella verificable y manifiesto consistente"); la Assumption indica que "la huella se calcula sobre el contenido del archivo completo (datos + manifiesto)".
- **Alternatives considered**: Huella parcial por bloque sin hash global (pierde verificación completa); hash del contenido del directorio `bloques/` sin `manifest.json` (no cubre integridad del manifiesto).

## D7. Precisión decimal en serialización JSON

- **Decision**: Todos los importes del dominio (`NUMERIC(18,4)`) se serializan como strings en los JSON del ZIP: `"importe": "123.4500"` (con precisión de 4 decimales y sin ceros finales truncados). En el backend, `json.dumps` se configura con `cls=DecimalEncoder` (o `use_decimal=False` con `default=str(Decimal)` de Pydantic) para evitar conversión a `float`. El `ManifestBloque` incluye `conteo_registros` con tipos nativos (int) que no requieren serialización decimal.
- **Rationale**: Cumple SC-005 y la regla constitucional de prohibir `float` en importes; la Assumption indica "formato estándar (JSON)".
- **Alternatives considered**: Serializar como float con precisión (incumple la constitución); usar un serializador de texto plano por bloque (pierde la estructura JSON).

## D8. Enlace SII de la AEAT (FR-006, US3 opcional)

- **Decision**: Cuando `tipo=SII`, la exportación incluye un bloque adicional `datos_sii/facturas_emitidas.json` y `datos_sii/facturas_recibidas.json` con un formato normalizado que contiene por cada factura los campos exigidos por el SII: `NIF`, `NombreRazon`, `TipoFactura`, `FechaOperacion`, `FechaExpedicion`, `NumeroFactura`, `ClaveRegimen`, `BaseImponible`, `TipoImpositivo`, `CuotaRepercutida`, `ImporteTotal`, `EstadoCuadre`, etc. La presentación telemática queda fuera de alcance (el usuario la realiza manualmente desde el portal de la AEAT). La configuración SII (`ConfigSii`) registra si la empresa está obligada y su régimen.
- **Rationale**: Cumple FR-006 y el edge case de la spec ("¿Qué ocurre con el SII de la AEAT?"); la funcionalidad es declarada como opcional y prepara los datos para subida manual al portal SII.
- **Alternatives considered**: Generar fichero XML SII estándar AEAT (formato específico con XSD; demasiado costoso para MVP); omitir SII completamente (incumple la FR-006 como bloque declarado).

## D9. Inmutabilidad y auditoría de exportaciones

- **Decision**: Una vez generada, la exportación (`Exportacion`) es inmutable: no admite UPDATE ni DELETE (protección a nivel de servicio y de trigger DB). La verificación de integridad (US2) crea un registro nuevo de auditoría (acción `VERIFICAR`) en la misma transacción ACID. La exportación misma se audita al crearse (acción `GENERAR_EXPORTACION`). El `BlobExportacion` es inmutable tras persistirse (sha256 calculado, contenido BYTEA sin cambios).
- **Rationale**: Cumple la constitución (inmutabilidad de registros auditables, auditoría ACID); la exportación no es un dato de negocio mutable, sino un snapshot inmutable del estado del tenant.
- **Alternatives considered**: Permitir regeneración sobre la misma exportación (rompe la inmutabilidad del snapshot); no auditar la verificación (pierde trazabilidad).

## D10. Correlatividad del número de exportación y stack

- **Decision**: `numero_exportacion` es `BIGINT` correlativo por `(empresa_id, anio_creacion)`, asignado atómicamente en la misma transacción con `SELECT ... FOR UPDATE` sobre una secuencia o contador por (empresa, año). El backend genera la exportación con `async with async_session.begin()`; el frontend ofrece un botón de "Crear exportación" que dispara la generación síncrona, muestra progreso (se puede simular con polling del estado `en_proceso` → `lista`), y un botón de descarga que llama al endpoint de descarga. El endpoint de verificación (US2) es distinto del de creación y opera sobre la exportación ya persistida.
- **Rationale**: Cumple la constitución IV (correlatividad por empresa y año); coherente con el patrón de numeración de remesas de SPEC-020.
- **Alternatives considered**: Número auto-incremental global (rompe correlatividad por empresa); sin número correlativo (incumple la constitución).
