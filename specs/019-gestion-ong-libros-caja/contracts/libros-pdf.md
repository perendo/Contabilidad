# Contracto: PDF de Libros Oficiales (SPEC-019)

**Branch**: `019-gestion-ong-libros-caja` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

Formato del documento PDF generado por el endpoint `POST /api/v1/libros/{ejercicio}/generar`. Es la representación imprimible de los libros oficiales (FR-005). Debe reflejar fielmente el diario/mayor inmutable del ejercicio cerrado con precisión decimal exacta (SC-002).

## 1. Tipos de libro

| `tipo` | Contenido |
|---|---|
| `diario` | Todos los asientos del ejercicio en orden de número correlativo (motor SPEC-002), con sus líneas (cuenta, descripción, Debe, Haber), numeración y suma de cierre. |
| `mayor` | Por cuenta del plan (SPEC-001): todos los apuntes del ejercicio ordenados cronológicamente con saldo inicial/acumulado y saldo final; para cuentas con movimiento. |
| `cuentas_anuales` | Si están definidas (SPEC-001/004): estados (balance de situación, cuenta de pérdidas y ganancias) con saldos agregados del ejercicio. Opcional. |

## 2. Reglas del contenido

- **Solo ejercicios cerrados** (SPEC-004): la generación se rechaza con 409 si el ejercicio está abierto.
- **Orden**: número de asiento correlativo (diario); código de cuenta y dentro de cuenta fecha/número (mayor).
- **Precisión**: todos los importes en 4 decimales, formato `d.dddd` sin notación científica; suma de cierre del diario Debe == Haber (partida doble, constitución I) y debe imprimirse en el pie.
- **Datos**: fecha de generación, rango de asientos cubierto, empresa (razón social/NIF) y ejercicio.
- **Huella**: el `sha256` se calcula sobre el contenido textual canónico (la secuencia de asientos/líneas en 4 decimales + metadatos), no sobre el binario PDF, para permitir comparación estable entre re-emisiones (D3/D4).
- El PDF es una captura del diario inmutable: no se re-ordenan ni se omiten asientos del ejercicio.

## 3. Estructura del PDF

```text
Página 1 — Cabecera:
  Empresa (razón social, NIF), Ejercicio, Tipo (DIARIO/MAYOR/CUENTAS ANUALES)
  Rango de asientos: Nº 1 — Nº 1200 | Fecha de generación: YYYY-MM-DD

Cuerpo (diario):
  Asiento Nº <n> | Fecha YYYY-MM-DD | Concepto
    Cuenta | Descripción | Debe (18,4) | Haber (18,4)
    ...
    Total asiento: Debe = Haber

Cuerpo (mayor):
  Cuenta <código> | Descripción
    Nº | Fecha | Concepto | Debe | Haber | Saldo
    Saldo final de la cuenta

Pie de cada página: página X / Y | suma parcial Debe | suma parcial Haber
Página final — Suma total: Debe = Haber (diario)
```

## 4. Validaciones del contrato (tests de contrato)

- `backend/tests/contract/test_libros_pdf_esquema.py`: genera PDF de un ejercicio de fixtures y verifica (a) todas las páginas contienen cabecera/pie válidos, (b) los importes aparecen con 4 decimales, (c) la suma de cierre Debe == Haber, (d) el número de asientos del PDF == nº asientos del diario del ejercicio, (e) la huella calculada coincide con `libro_oficial.sha256`.
- Un PDF de un ejercicio distinto o con asiento omitido no pasa (c) ni (d).