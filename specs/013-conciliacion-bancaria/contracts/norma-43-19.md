# Formato Externo: Fichero de Extracto Bancario (norma 43/19) — SPEC-013

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Contrato del fichero de extracto que acepta `POST /api/v1/extractos`. El parser es configurable por layout (`norma_43_1919` | `csv_normalizado`); este documento define el layout de referencia y el mapeo al modelo ([data-model](../data-model.md)).

## Norma 43/19 — Texto de ancho fijo (ISO-8859-1)

Fichero de texto plano con registros de longitud fija, uno por línea, CR/LF opcional al final.

### Registro de cabecera (código `01`)

| Posición | Campo | Ejemplo | Reglas |
|----------|-------|---------|--------|
| 1-2 | Código de registro | `01` | fijo |
| 3-22 | Referencia del tercero/empresa | `ES000000000000` | solo informativo |
| 23-30 | Fecha de los datos (AAMMDD) | `260915` | |
| 31-... | Datos de la entidad y cuenta | | CCC/IBAN |
| ...-N | Saldo inicial (con separador implícito) | `0000000123450000` | 4 decimales, sin separador |
| ... | Saldo final | `0000000134500000` | 4 decimales |

> Nota: las posiciones exactas de saldos varían por entidad; el parser lee un **mapa de offsets** declarado por layout (ver `backend/src/services/reconciliation/layouts.py`). NEEDS CLARIFICATION: confirmar el/los diccionario(s) de offsets por entidad en la primera implantación.

### Registro de operación (código `21` débito / `22` crédito)

| Posición | Campo | Ejemplo | Reglas |
|----------|-------|---------|--------|
| 1-2 | Código de registro | `21`/`22` | define `signo` (D/H) |
| 3-4 | Código de concepto bancario | `331` | informativo |
| 5-12 | Fecha de operación (AAMMDD) | `260910` | → `fecha_operacion` |
| 13-20 | Fecha de valor (AAMMDD) | `260911` | → `fecha_valor` |
| 21-... | Concepto (alfanumérico, fijo) | `TRANSFERENCIA` | → `concepto` |
| ...-N | Importe sin signo, 4 decimales | `0000000150000000` | → `importe` > 0, dirección por el registro |
| ...-M | Referencia | `REF20260910-1` | → `referencia` |

### Registro de control (código `98`)

| Posición | Campo | Reglas |
|----------|-------|--------|
| 1-2 | Código de registro | `98` |
| 3-10 | Número de registros de operación | debe coincidir con las líneas leídas |
| ... | Suma de importes (4 decimales) | debe coincidir con Σ importes del extracto parseado |

### Validaciones del layout de referencia

1. Longitud de línea constante (rechazo 422 con nº de registro si varía).
2. Suma de importes (con signo) == `saldo_final − saldo_inicial` declarados en cabecera (salvo que la entidad declare parciales). Si el rechazo no puede verificarse por el fichero → NEEDS CLARIFICATION: config de la entidad.
3. `importe > 0` siempre; la orientación se transmite por el código de registro (21 débito / 22 crédito).
4. Códigos de registro solo `01`, `21`, `22`, `98` (rechazo 422 en otro caso).

## CSV normalizado (UTF-8)

Fichero CSV con cabecera y separador `;`:

```
numero;fecha_operacion;fecha_valor;concepto;importe;signo;referencia
1;2026-09-10;2026-09-11;TRANSFERENCIA;1500.0000;H;REF20260910-1
```

- `importe` como string decimal con hasta 4 decimales; `signo` = `D`/`H`.
- La línea de totales (opcional) usa `numero=0;concepto=TOTALES;...` y debe cuadrar con Σ importes.

## Mapeo al modelo

| Fichero (norma 43/19) | MovimientoBancario |
|-----------------------|--------------------|
| código 21/22 | `signo` = D/H |
| fecha de operación | `fecha_operacion` |
| fecha de valor | `fecha_valor` |
| concepto | `concepto` (normalizado antes de matching, D3 de research) |
| importe (4 decimales) | `importe` NUMERIC(18,4) |
| referencia | `referencia` |

## Duplicados

- `sha256` del fichero (bytes tal como se envían) único por empresa → 409 `extracto_duplicado`.
- Solapamiento por (cuenta_id, rango_de_fechas, saldo_inicial, saldo_final, n_movimientos) con distinta huella → 409 idem.

## Fixtures de referencia

- `backend/tests/fixtures/extracto_43_19_valido.txt` — 1 cabecera, 3 operaciones (2 débito, 1 crédito), 1 control, cuadre exacto.
- `backend/tests/fixtures/extracto_43_19_duplicado.txt` — mismo contenido con distinto nombre.
- `backend/tests/fixtures/extracto_43_19_otra_empresa.txt` — cuenta 572 de otra empresa.
- `backend/tests/fixtures/extracto_43_19_malformado.txt` — longitud de línea rota y suma descuadrada.
- `backend/tests/fixtures/extracto_csv_normalizado.csv` — variante CSV equivalente.