# Modelos Fiscales: Esquema de Ficheros (303 / 347 / 349)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Formato de los ficheros generados por la exportacion de modelos (SPEC-012). Los importes se redondean a 2 decimales (regla legal AEAT) SOLO en el fichero; el almacenamiento y los cuadres usan `NUMERIC(18,4)`.

## 1. Modelo 303 (autoliquidacion del IVA, trimestral/mensual)

### Fichero de presentacion (formato AEAT de autoliquidacion)

Cabecera por registro con identificador de la empresa (NIF) y periodo (CCNN: trimestre `01-04` o `11,12,...` mes), ejercicio AAAA.

| Bloque | Campos principales |
|--------|--------------------|
| Identificacion | NIF, ejercicio, periodo |
| Devengado (corriente) | Casillas: base y cuota por tipo (21/10/5/0), regimenes especiales |
| Devengado (adquisiciones intracomunitarias) | base/cuota por tipo |
| Deducible (cuotas soportadas) | base/cuota deducible por tipo |
| Recargo de equivalencia | cuota de recargo (separada del IVA) |
| Rectificaciones | cuotas a deducir/compensar por rectificativas |
| Resultado | a ingresar / a compensar (arrastre) |

**Reglas de cuadre (verificadas en backend)**:
1. `Suma(cuotas devengadas por tipo) == Suma(cuotas del libro emitidas del periodo)` (operaciones corrientes).
2. `Suma(cuotas deducibles) == Suma(cuotas del libro recibidas del periodo)` (deducibles).
3. `Recargo == Suma(recargo_cuota del libro del periodo)`.
4. El IVA diferido por criterio de caja NO aparece en las casillas hasta su fecha de devengo real.

### CSV de exportacion (legible)

```csv
ejercicio;periodo;tipo_casilla;base;cuota
2026;01;21;10000.00;2100.00
2026;01;10;5000.00;500.00
...
```

## 2. Modelo 347 (resumen anual de operaciones con terceros)

Agregacion por NIF y clave operacional del ejercicio completo. Solo operaciones con importe anual > 3.005,06 EUR por tercero.

### Claves operacionales habituales

| Clave | Descripcion |
|-------|-------------|
| A | Bienes/servicios a/ de clientes/proveedores |
| B | Adquisiciones intracomunitarias de bienes |
| C | Entregas intracomunitarias de bienes |
| D | Ventas a o compras a otros sujetos (no anuales) |
| E | Transmisiones a o adquisiciones de inmuebles |
| G | Operaciones de seguros |
| Z | Otras (arrendamiento, prestamos, etc.) |

### Reporte (JSON + HTML/PDF legible)

```json
{
  "ejercicio": 2026,
  "operaciones": [
    { "nif_tercero": "B12345678", "nombre": "Proveedor 1", "clave_operacion": "A",
      "importe_acumulado": "12000.0000", "n_operaciones": 5 }
  ],
  "total_general": "12000.0000"
}
```

**Regla**: solo se incluyen terceros con `importe_acumulado > 3005.06` (cuantificado con Decimal exacto).

## 3. Modelo 349 (declaracion recapitulativa de operaciones intracomunitarias)

Agregacion por NIF del periodo (trimestre o mes) de las operaciones intracomunitarias.

| Campo | Tipo |
|-------|------|
| NIF operador | VARCHAR(9) |
| Clave de operacion | `B` bienes / `C` servicios (y variantes) |
| Pais destino | VARCHAR(2) |
| Importe | NUMERIC(18,4) -> 2 decimales en fichero |
| Fecha de la operacion | DATE |
| Bienes: naturaleza operacion / declara todo | segun la comunicacion |

### Fichero XML de presentacion (349 AEAT)

```xml
<Modelo349>
  <Identificador><NIF>...</NIF><Ejercicio>2026</Ejercicio><Periodo>01</Periodo></Identificador>
  <Registro>
    <NIF>...</NIF><ClaveOperacion>B</ClaveOperacion>
    <Importe>1234.56</Importe>
    <Operaciones>1</Operaciones>
  </Registro>
</Modelo349>
```

## 4. Reglas comunes de los ficheros

- Identificacion de periodo y empresa en todos los ficheros (FR-004).
- Los totales del fichero coinciden con los cuadres del backend (303: libros del periodo; 347: ejercicio; 349: periodo).
- Hash sha256 del fichero generado almacenado en `ExportacionModelo.contenido_hash`.
- Si el periodo ya esta exportado, al regenerar se crea nueva exportacion con trazabilidad (estado `regenerado`) y advertencia al usuario.
- Importes en el fichero con redondeo legal a 2 decimales; los JSON de API mantienen 4 decimales.