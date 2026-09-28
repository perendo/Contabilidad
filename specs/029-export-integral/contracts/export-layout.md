# Export File Layout: Export Integral del Tenant (SPEC-029)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Especificación del formato del ZIP de exportación y del manifiesto interior. Todos los importes de los bloques JSON se serializan como **strings con precisión de 4 decimales** (p. ej. `"123.4500"`). El orden de los ficheros dentro del ZIP es **determinista** (orden alfabético de las rutas) para que el hash SHA-256 sea reproducible entre ejecuciones idénticas de un mismo estado.

## 1. Estructura del ZIP

```text
export_{empresa_id}_{numero_exportacion}_{AAAAMMDD}.zip
├── manifest.json                     # inventario y huella de integridad
└── bloques/
    ├── 001_plan_cuentas.json         # SPEC-001 (cuentas)
    ├── 002_plan_cuentas_versiones.json  # SPEC-025 (versiones del PGC)
    ├── 003_asientos.json             # SPEC-002 (JournalEntry)
    ├── 004_apuntes.json              # SPEC-002 (JournalEntryLine)
    ├── 005_terceros.json             # SPEC-008
    ├── 006_facturas.json             # SPEC-007 (cabeceras)
    ├── 007_lineas_factura.json       # SPEC-007 (líneas)
    ├── 008_vencimientos.json         # SPEC-011
    ├── 009_cobros_pagos.json         # SPEC-011
    ├── 010_remesas.json              # SPEC-020
    ├── 011_devoluciones.json         # SPEC-020
    ├── 012_amortizaciones.json       # SPEC-014
    ├── 013_cierres.json              # SPEC-028 (PeriodoCerrado, CierreEjercicio, BalanzaPeríodo)
    ├── 014_presupuestos.json         # SPEC-026
    ├── 015_previsiones.json          # SPEC-027
    ├── 016_libros_iva.json           # SPEC-012 (libros y modelos)
    ├── 017_configuracion.json        # configuración general de la empresa
    └── datos_sii/                    # SOLO si tipo=SII (o obligado_sii=true)
        ├── facturas_emitidas.json
        └── facturas_recibidas.json
```

Los prefijos numéricos `001_..017_` ordenan los bloques en el ZIP y permiten un inventario estable. Cada bloque JSON es un objeto con cabecera mínima y `registros`:

```json
{
  "bloque": "asientos",
  "entidades_exportadas": ["JournalEntry"],
  "conteo_registros": 12500,
  "ejercicio_min": 2024,
  "ejercicio_max": 2026,
  "registros": []
}
```

## 2. manifest.json (interior del ZIP)

```json
{
  "formato_version": "1.0.0",
  "fecha_generacion": "2026-09-16T12:00:00Z",
  "tenant_id": 42,
  "ejercicio_desde": 2024,
  "ejercicio_hasta": 2026,
  "bloques": [
    { "bloque": "plan_cuentas", "entidades_exportadas": ["CuentaContable"], "conteo_registros": 150, "ejercicio_min": null, "ejercicio_max": null },
    { "bloque": "asientos", "entidades_exportadas": ["JournalEntry"], "conteo_registros": 12500, "ejercicio_min": 2024, "ejercicio_max": 2026 }
  ],
  "sha256_fichero": "ab12cd...ef"
}
```

- `tenant_id` reitera `empresa_id` de forma redundante para la verificación cruzada (una exportación jamás puede contener otro `tenant_id`).
- `sha256_fichero` = SHA-256 del **contenido binario del ZIP completo** (datos + manifiesto), como indica la Assumption de la spec.

## 3. Serialización de importes (Decimal)

- Todo campo monetario se serializa como string con **4 decimales**: `"123.4500"`, `"-5.0000"`, `"0.0000"`.
- Prohibido cualquier valor JSON numérico para importes (`123.45` o `1.2345E3`).
- Códigos (NIF, cuenta, serie), identificadores (UUID) y fechas (ISO 8601) se serializan sin transformación de precisión.

## 4. Bloque SII (datos_sii)

Registros normalizados con los campos exigidos por el SII de la AEAT, listos para subida manual al portal:

| Campo | Tipo | Ejemplo |
|-------|------|---------|
| NIF | string(9) | `B12345678` |
| NombreRazon | string | `PROVEEDOR SL` |
| TipoFactura | ENUM | `F1` (factura)/`F2` (abreviatura)/`R1` ... |
| FechaOperacion | date ISO | `2026-03-15` |
| FechaExpedicion | date ISO | `2026-03-01` |
| NumeroFactura | string | `FAC-2026-001` |
| ClaveRegimen | string(2) | `01` |
| BaseImponible | "1234.5000" | |
| TipoImpositivo | string | `21.00` |
| CuotaRepercutida | "259.2450" | |
| ImporteTotal | "1493.7450" | |
| EstadoCuadre | ENUM | `CUADRADO`/`DESCUADRADO` |

El bloque de SII se calcula como subconjunto de `facturas` (SPEC-007) y `libros_iva` (SPEC-012); la presentación telemática queda fuera de alcance (subida manual del usuario al portal AEAT).

## 5. Reglas de validación del ZIP

- El ZIP generado debe tener **saltos de directorio determinista**: `bloques/` y `datos_sii/` siempre presentes (aunque vacíos) según `tipo`.
- `manifest.json` MUST estar en la raíz del ZIP.
- La verificación de integridad (US2) comprueba: (1) `sha256_fichero` del manifiesto == SHA-256 del ZIP completo; (2) el conteo de registros de cada bloque del manifiesto == conteo en el JSON del bloque; (3) `tenant_id` == `empresa_id` de la sesión que verifica.
- La regeneración de un estado idéntico produce un ZIP idéntico byte a byte (orden determinista; los timestamps de los ZIP en modo streaming no forman parte del hash si se usa `zipfile` con `ZipInfo` fija para determinismo — see reseña técnica en tasks).