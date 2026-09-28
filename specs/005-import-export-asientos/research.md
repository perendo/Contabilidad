# Research: Importación y Exportación Masiva de Asientos Contables (SPEC-005)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Formatos de archivo soportados (importación)

- **Decision**: Soportar **CSV** (separador configurable, encoding UTF-8/ISO-8859-1 detectado) y **XLSX** (hoja activa) como formatos de entrada. Ambos se interpretan en una fase de parseo común que devuelve una lista de filas crudas normalizadas.
- **Rationale**: CSV y XLSX son los formatos estándar en contabilidad española; Excel domina en despachos contables. El parseador normaliza a una estructura interna antes de la validación.
- **Alternatives considered**: Soportar solo CSV (pierde usuarios Excel); añadir ODS (bajo uso en España); Parseo con pandas (dependencia pesada innecesaria para este volumen).

## D2. Esquema de columnas del archivo de importación

- **Decision**: El esquema mínimo incluye las columnas: `fecha` (YYYY-MM-DD), `numero_asiento` (opcional, para agrupar líneas de un mismo asiento), `concepto`/`detalle`, `cuenta` (código del plan), `debe` (string decimal), `haber` (string decimal). Para asientos multilínea (SPEC-006), varias filas con el mismo `numero_asiento` o grupo forman un solo asiento. Se valida que el archivo tiene todas las columnas requeridas antes de procesar.
- **Rationale**: El esquema se fija en la plantilla estándar que acompaña a la feature; la spec asume un esquema mínimo con esos campos.
- **Alternatives considered**: Esquema libre con columnas posicionales (frágil); esquema con ID de asiento en la primera fila del grupo (más explícito pero menos intuitivo).

## D3. Estrategia de validación dry-run (previsualización)

- **Decision**: La previsualización parsea el archivo en memoria, valida cada asiento contra la base de datos (existencia de cuentas, apuntabilidad, ejercicio abierto, partida doble) y devuelve un `ResultadoImportacion` con totales y lista de errores por fila. **No se escribe nada** en la base de datos durante la previsualización.
- **Rationale**: Cumple FR-002 (dry-run sin escritura) y FR-004 (resumen con errores). El usuario ve errores antes de confirmar.
- **Alternatives considered**: Previsualización parcial por asiento (pierde visión global); validación solo en confirmación (retrasa la detección de errores).

## D4. Manejo de Decimal en parseo de valores del archivo

- **Decision**: Los valores de `debe` y `haber` se parsean con `Decimal(valor.strip())` directamente, sin pasar por `float` en ningún punto. Se aceptan formatos con coma o punto como separador decimal (detectar el más frecuente en el archivo y normalizar). Si el parseo falla (ej. "abc"), se reporta error de formato en la fila.
- **Rationale**: Cumple FR-009 y la norma constitucional de prohibir `float`. La conversión `Decimal(string)` preserva la precisión exacta.
- **Alternatives considered**: Parseo vía `float` y conversión posterior (pierde precisión, viola constitución); parseo con locale (frágil bajo concurrencia).

## D5. Tamaño máximo de archivo y límites de procesamiento

- **Decision**: Tamaño máximo de archivo configurable por empresa (default **10 MB** / **5.000 asientos**). El backend rechaza archivos que superen el límite antes de procesar. El procesamiento es secuencial por asiento para garantizar atomicidad de cada uno.
- **Rationale**: Un límite razonable evita abuso de memoria y tiempos excesivos; el procesamiento secuencial cumple FR-005 (transacción atómica por asiento).
- **Alternatives considered**: Sin límite (riesgo de DoS); límite fijo en código (poco flexible).

## D6. Correlatividad del número de asiento durante importación

- **Decision**: Durante la importación definitiva, se asigna `numero_asiento` correlativo por (empresa_id, ejercicio) con `SELECT ... FOR UPDATE` sobre el contador o secuencia bloqueada, **dentro de la misma transacción** que persiste cada asiento. Si el archivo incluye un `numero_asiento` explícito, se ignora y se asigna el correlativo (el usuario no controla la numeración legal).
- **Rationale**: Cumple constitución IV; evita duplicados/omisiones bajo concurrencia; el usuario no debe preocuparse por la numeración.
- **Alternatives considered**: Reservar un bloque de números antes de la importación (complejo y propenso a gaps si falla a medio camino); usar el número del archivo (rompe correlatividad si el archivo viene de otro sistema).

## D7. Exportación del libro diario (formato y contenido)

- **Decision**: La exportación genera un archivo **CSV** o **XLSX** (a elección del usuario) con columnas: `fecha`, `numero_asiento`, `cuenta`, `concepto`, `debe`, `haber`, `saldo`. Los importes se formatean con exactamente 4 decimales (sin trailing zeros diferentes a los 4). El archivo incluye solo asientos `POSTED` de la empresa activa en el rango de fechas indicado.
- **Rationale**: Cumple FR-008 (precisión de 4 decimales) y FR-001 (aislamiento por empresa). El formato CSV es universal para herramientas de contabilidad externas.
- **Alternatives considered**: Exportación solo en un formato (menos flexible); exportación con formato de moneda localizado (problemas de encoding).

## D8. Gestión de errores durante la importación definitiva

- **Decision**: Si un asiento falla durante la ejecución (por ejemplo, ejercicio cerrado entre la previsualización y la confirmación, o cuenta eliminada), **ese asiento se omite** sin afectar a los demás (FR-003 edge case). La operación continua con los asientos restantes válidos y el resultado final lista los asientos importados y los omitidos con motivo.
- **Rationale**: Un solo error no debe bloquear toda la importación; la omisión sin estado parcial es segura dado que cada asiento es una transacción atómica independiente.
- **Alternatives considered**: Rechazo total ante el primer error (frustrante para archivos grandes); reintento automático (complejo y riesgo de duplicados).

## D9. Interfaz de usuario (drag-and-drop + vista previa)

- **Decision**: El frontend ofrece una zona de drag-and-drop para subir el archivo. Tras la subida, el backend procesa la previsualización y el frontend muestra una tabla con los totales (válidos, erróneos) y el detalle de errores resaltados. Un botón "Confirmar importación" solo se habilita si hay asientos válidos. La confirmación llama al endpoint de importación definitiva.
- **Rationale**: Cumple FR-010 (interfaz con vista previa de errores); la UI informativa no reemplaza la validación del backend.
- **Alternatives considered**: Flujo de dos pasos separados (subir + previsualizar manualmente); vista previa solo en tabla (menos intuitiva para archivos grandes).

## D10. Integridad y atomicidad de la importación definitiva

- **Decision**: Cada asiento se persiste como una transacción atómica (`async with async_session.begin()`) que incluye cabecera + líneas + incremento del contador correlativo + registro de auditoría. Si la transacción falla, se hace rollback completo del asiento y se omite de la lista de importados.
- **Rationale**: Cumple FR-005 (transacción atómica por asiento) y la constitución (auditoría en la misma transacción ACID).
- **Alternatives considered**: Transacción de lote entero (un error bloquea todo); sin transacciones explícitas (riesgo de estado parcial).
