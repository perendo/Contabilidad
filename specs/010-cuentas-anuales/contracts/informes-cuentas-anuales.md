# Fichas de Cuentas Anuales: Esquema de Informes (SPEC-010)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Esquema de los informes que componen las cuentas anuales, generados a partir de saldos del plan de cuentas (SPEC-001) y verificados en backend.

## 1. Balance de Situacion

Estructura por masas patrimoniales del PGC espanol, agrupada a partir de la configuracion del plan de cuentas (ConfiguracionInforme). Los importes son `NUMERIC(18,4)`.

### ACTIVO

- **A. Activo No Corriente**
  - I. Inmovilizado intangible (grupo 20)
  - II. Inmovilizado material (grupo 21-23)
  - III. Inversiones inmobiliarias (grupo 22)
  - IV. Inmovilizado financiero a largo plazo (grupo 24-25)
  - **Total Activo No Corriente** (suma I-IV)

- **B. Activo Corriente**
  - I. Existencias (grupo 30-35)
  - II. Deudores comerciales y otras cuentas a cobrar (grupo 43, 44)
  - III. Inversiones a corto plazo (grupo 26)
  - IV. Caja y cuentas corrientes en bancos (grupo 57, 55)
  - **Total Activo Corriente** (suma I-IV)

- **TOTAL ACTIVO** = A + B

### PASIVO Y PATRIMONIO NETO

- **C. Pasivo No Corriente**
  - I. Deudas a largo plazo (grupo 10, 17 a largo plazo)
  - II. Otras pasivos no corrientes
  - **Total Pasivo No Corriente**

- **D. Pasivo Corriente**
  - I. Proveedores y otras cuentas a pagar (grupo 40, 41)
  - II. Deudas a corto plazo (grupo 51, 52)
  - III. Cuentas de provisiones a corto plazo (grupo 46)
  - **Total Pasivo Corriente**

- **E. Patrimonio Neto**
  - I. Fondos propios (grupo 100-103, 110-114)
  - II. Reservas (grupo 110-114)
  - III. Resultado del ejercicio (derivado de PyG)
  - **Total Patrimonio Neto**

- **TOTAL PASIVO + PATRIMONIO NETO** = C + D + E

**Verificacion**: `TOTAL_ACTIVO == TOTAL_PASIVO + TOTAL_PATRIMONIO` (en backend, con Decimal exacto).

### JSON de respuesta (ejemplo parcial)

```json
{
  "ejercicio": 2026,
  "cuadre": true,
  "total_activo": "150000.0000",
  "total_pasivo": "80000.0000",
  "total_patrimonio": "70000.0000",
  "masas": [
    { "nombre": "Activo No Corriente", "importe": "90000.0000",
      "partidas": [
        { "nombre": "Inmovilizado intangible", "importe": "15000.0000", "cuentas": ["200","201"] },
        { "nombre": "Inmovilizado material", "importe": "75000.0000", "cuentas": ["210","211","213"] }
      ]
    }
  ],
  "comparativo_anterior": null
}
```

## 2. Cuenta de Perdidas y Ganancias

### Estructura (modelo de area de gestión por gastos/ingresos)

- **A. Gastos de la empresa**
  - I. Gastos de personal (grupo 64)
  - II. Otros gastos de explotacion (grupo 60-63)
  - III. Amortizaciones (grupo 68)
  - IV. Provisiones (grupo 69)
  - V. Otras perdidas operativas
  - **Total Gastos de Explotacion** = I-V

- **B. Ingresos de la empresa**
  - I. Ingresos de explotacion (grupo 70)
  - II. Otros ingresos operativos
  - **Total Ingresos de Explotacion** = I-II

- **A-B. Resultado de la explotacion (EBIT)**

- **C. Resultados financieros**
  - I. Gastos financieros (grupo 66)
  - II. Ingresos financieros (grupo 76)
  - **Resultado neto financiero** = II - I

- **D. Resultado antes de impuestos** = (A-B) + (C.II - C.I)

- **E. Impuestos sobre beneficios** (grupo 695)

- **RESULTADO DEL EJERCICIO** = D - E

**Verificacion**: `RESULTADO_EJERCICIO == resultado del asiento de regularizacion/cierre (SPEC-004)`. Si difiere, se advierte `descuadre_cierre` y la formulacion oficial se bloquea.

### JSON de respuesta (ejemplo parcial)

```json
{
  "ejercicio": 2026,
  "total_ingresos": "250000.0000",
  "total_gastos": "200000.0000",
  "resultado_ejercicio": "50000.0000",
  "resultado_cierre": "50000.0000",
  "coincide_cierre": true,
  "partidas": [
    { "grupo": "64", "nombre": "Gastos de personal", "importe": "80000.0000" },
    { "grupo": "60-63", "nombre": "Otros gastos de explotacion", "importe": "60000.0000" },
    { "grupo": "70", "nombre": "Ingresos de explotacion", "importe": "250000.0000" }
  ]
}
```

## 3. Estado de Flujos de Efectivo (EFE)

Estructura por actividades (método directo), derivada de movimientos de las cuentas de tesoreria (grupo 5) y clasificacion por actividad.

### Saldo de tesoreria al inicio del ejercicio

Cuentas 570/572/573 al inicio del ejercicio.

### A. Actividades operativas

- Cobros por ventas de bienes/servicios
- Pagos a proveedores y empleados
- Intereses recibidos/pagados
- Impuestos pagados
- **Flujo neto de actividades operativas**

### B. Actividades de inversion

- Adquisicion de inmovilizado
- Enajenacion de inmovilizado
- **Flujo neto de actividades de inversion**

### C. Actividades de financiacion

- Obtencion de prestamos
- Devolucion de prestamos
- Aportaciones de socios
- Dividendos pagados
- **Flujo neto de actividades de financiacion**

### Variacion neta de tesoreria

= A + B + C

### Saldo de tesoreria al cierre

= Saldo inicial + Variacion neta

**Verificacion**: `saldo_final == saldo_inicial + variacion_neta` Y `variacion == variacion_tesoreria_balance` (la diferencia de saldos de grupo 5 entre inicio y fin del ejercicio, calculada desde el Balance de Situacion).

## 4. Formulacion Oficial (snapshot)

La formulacion oficial congela los tres informes anteriores en un unico registro `FormulacionCuentasAnuales` con:

- `contenido_hash`: SHA-256 serializado de los tres informes JSON
- `estado`: `formulada` o `anulada`
- Traza completa: usuario, fecha UTC, motivo de anulacion (si aplica)
- Solo ejercicios `cerrado`

El hash se calcula sobre la concatenacion determinista de: ejercicio + Balance JSON + PyG JSON + EFE JSON.
