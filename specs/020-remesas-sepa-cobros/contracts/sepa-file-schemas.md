# File Schemas: Remesas SEPA y Soporte Magnético (SPEC-020)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

## 1. XML SEPA DD (PAIN.008.001.02)

Fichero de domiciliación de recibos SEPA, publicación EPC, esquema `pain.008.001.02`.

- **Cabecera** (`GrpHdr`): `MsgId` (ID único de mensaje), `CreDtTm` (UTC), `NbOfTxs`, `CtrlSum` (suma de importes, mgrilla 2 decimales), InitgPty.
- **Pago** (`PmtInf`): un bloque por combinación de tipo de adeudo y fecha de cargo, con `PmtInfId`, `PmtMtd=DD`, `BtchBookg`, `NbOfTxs`, `CtrlSum`, `PmtTpInf` (`SvcLvl=SEPA`, `LclInstrm=CORE` o `B2B`), `ReqdColltnDt` (**fecha de cargo**), `Cdtr` (empresa), `CdtrAcct` (IBAN empresa).
- **Instrucción (`DrctDbtTxInf`)** por recibo:
  - `PmtId.EndToEndId` = referencia recibo (correlativa).
  - `InstdAmt` = importe con 2 decimales (Ccy=EUR).
  - `DrctDbtTx` → `MndtRltdInf` (`MndtId` = mandato, `DtOfSgntr` = fecha firma, `AmdmntInd=false`).
  - `Dbtr` (nombre del tercero), `DbtrAcct.IBAN`, `DbtrAgt.BIC` (opcional pero recomendado).
- **Validación de plazos** (antes de emitir): primera presentación **CORE** con anticipación mínima **D-2 días hábiles**; presentaciones CORE recurrentes aplican la regla vigente del mandato/banco; **B2B** exige **D-1 día hábil** y mandato firmado con `MndtId` y `DtOfSgntr`.

## 2. Soporte magnético AEB CSB 19.19

Fichero texto plano de remesa de recibos (cuaderno 19 de AEB), una línea por registro:

- **Registro tipo 1 (cabecera emisor)**: `1` + NIF del ordenante (9) + sufijo (3) + datos del ordenante (nombre, dirección, CP) + fecha de presentación (8, AAAAMMDD) + **importe total** en céntimos (12) + número de recibos (6) + banco/branch (8+8) + campo libre.
- **Registro tipo 2 (cabecera banco receptor)**: `2` + datos del banco receptor (cuenta cargo).
- **Registro tipo 3 (recibo)**: `3` + número de recibo (12) + fecha de cargo (AAAMMDD) + importe en céntimos (12) + referencia 1 + referencia 2 + referencia documento mercancía + datos del deudor (NIF 9+sufijo 3, banco 8+branch 8, DC 2, cuenta 10, nombre/dirección) + tipo de adeudo.
- **Registro tipo 5 (pie)**: `5` + importe total en céntimos (12) + número de recibos (6) + cheque DF + fecha.
- **Encode**: ASCII/ISO-8859-15, campos numéricos sin signo, importes en céntimos sin decimales.

## 3. Devoluciones R19 y bajas C19

Ficheros de retorno de la entidad bancaria (AEB, cuaderno 19, retorno):

- **Registro tipo 1 (cabecera emisor = entidad receptora)** y línea por movimiento:
- **Registro tipo 3' (devolución R19)**: `3` + **código de rechazo** (1-3) + clave de devolución + número de recibo original + fecha de cargo + importe en céntimos + motivo (descripción) + datos del deudor.
- **Registro tipo 3'' (baja C19)**: idéntica estructura con código de baja.
- Códigos R19 frecuentes que el sistema debe reconocer: `MD01` (referencia no encontrada), `MD02` (deudor fallecido), `MD05` (cuenta errónea), `MD06` (mandato rechazado), `AC04` (IBAN inválido), `AC06` (deudor imposible), `AM05` (adendo no autorizado), `R-RJCT` (rechazo general), `R-CUST` (rechazado por deudor).

## 4. Reglas de validación comunes del fichero

- Importes en el fichero y en asientos en `Decimal`; SEPA usa 2 decimales en `InstdAmt` (el esquema EPC no permite 4); el CSB 19.19 usa céntimos (12 dígitos numéricos).
- `CtrlSum` (SEPA) e "importe total" (CSB) MUST coincidir con la suma de los recibos incluidos.
- La correlatividad de `MsgId`/`EndToEndId` y de los números de recibo se garantiza a nivel de la transacción que persiste la remesa.
- Todo fichero generado se almacena en `BlobFichero` con `sha256`; el `quickstart.md` valida la regeneración determinista del binario.