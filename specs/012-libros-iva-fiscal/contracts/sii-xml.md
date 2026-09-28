# SII XML: Interfaz de Suministro Inmediato de Informacion (SPEC-012)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Interfaz declarada del enlace SII, habilitable por empresa. En esta feature NO se realiza envio: se genera el XML pendiente para su integracion con SPEC-029 (export integral). Esquemas de referencia: `SuministroLrFacturasEmitidas` y `SuministroLrFacturasRecibidas` de la AEAT (version 1.1/1.2).

## 1. Configuracion por empresa

- `habilitado`: booleano, por defecto false.
- `obligatorio`: booleano, si la empresa esta obligada (criterio legal: facturacion > 6M EUR, grupo IVA, etc.).
- Si `habilitado`, el modelo 303 debe calcularse en periodicidad `MES` (regla SII). El sistema ajusta la periodicidad con advertencia.
- Sin habilitar, la empresa opera en regimen general trimestral; el endpoint de XML devuelve 409 `sii_no_habilitado`.

## 2. Esquema de las facturas emitidas (`SuministroLrFacturasEmitidas`)

```xml
<SuministroLF>
  <Cabecera>
    <IDVersionSii>1.2</IDVersionSii>
    <Titular>
      <NombreRazon>EMPRESA S.L.</NombreRazon>
      <NIF>B12345678</NIF>
    </Titular>
    <TipoComunicacion>0</TipoComunicacion>  <!-- 0=A00 alta, 4=modificacion -->
    <Ejercicio>2026</Ejercicio>
    <Periodo>01</Periodo>
  </Cabecera>
  <RegistroLrFE>
    <PeriodoLiquidacion><Ejercicio>2026</Ejercicio><Periodo>01</Periodo></PeriodoLiquidacion>
    <IDFactura>
      <IDEmisorFactura><NIF>B12345678</NIF></IDEmisorFactura>
      <NumSerieFacturaEmisor>F2026-001</NumSerieFacturaEmisor>
      <FechaExpedicionFacturaEmisor>2026-01-15</FechaExpedicionFacturaEmisor>
    </IDFactura>
    <FacturaExpedida>
      <TipoDesglose>
        <DesgloseTipoOperacion>
          <TipoOperacion>01</TipoOperacion>
          <DesgloseIVA>
            <DetalleIVA>
              <TipoImpositivo>21.00</TipoImpositivo>
              <BaseImponible>10000.0000</BaseImponible>
              <CuotaRepercutida>2100.0000</CuotaRepercutida>
            </DetalleIVA>
          </DesgloseIVA>
        </DesgloseTipoOperacion>
      </TipoDesglose>
      <Contraparte>
        <NombreRazon>CLIENTE S.A.</NombreRazon>
        <NIF>A12345678</NIF>
      </Contraparte>
    </FacturaExpedida>
  </RegistroLrFE>
</SuministroLF>
```

### Reglas de la interfaz emitidas

- Una linea por factura con su desglose por tipo impositivo.
- Tipos de operacion: `01` (entrega/bienes, 02 servicios, 03/04 intracomunitarias, 08 criterio de caja, recargo de equivalencia en `CuotaRecargoEquivalencia`).
- Recargo de equivalencia: `CuotaRecargoEquivalencia` separado por tipo impositivo.
- Criterio de caja: las facturas con IVA diferido no se comunican hasta el devengo real (fecha de cobro).

## 3. Esquema de las facturas recibidas (`SuministroLrFacturasRecibidas`)

```xml
<SuministroLR>
  <Cabecera> (igual estructura con la empresa como receptora) </Cabecera>
  <RegistroLrFR>
    <PeriodoLiquidacion><Ejercicio>2026</Ejercicio><Periodo>01</Periodo></PeriodoLiquidacion>
    <IDFactura>
      <IDEmisorFactura><NIF>B99999999</NIF></IDEmisorFactura>
      <NumSerieFacturaEmisor>001</NumSerieFacturaEmisor>
      <FechaExpedicionFacturaEmisor>2026-01-20</FechaExpedicionFacturaEmisor>
    </IDFactura>
    <FacturaRecibida>
      <DesgloseFactura>
        <TipoDesglose>
          <DesgloseIVA>
            <DetalleIVA>
              <TipoImpositivo>21.00</TipoImpositivo>
              <BaseImponible>5000.0000</BaseImponible>
              <CuotaSoportada>1050.0000</CuotaSoportada>
            </DetalleIVA>
          </DesgloseIVA>
        </TipoDesglose>
      </DesgloseFactura>
      <Contraparte>...</Contraparte>
    </FacturaRecibida>
  </RegistroLrFR>
</SuministroLR>
```

### Reglas de la interfaz recibidas

- Base y cuota por tipo impositivo; IVA no deducible se refleja con su clave (el desglose se adapta).
- Operaciones intracomunitarias de bienes/servicios con sus claves especificas.


## 4. Reglas comunes de generacion

- El XML generado no se envia; se devuelve por el endpoint `GET /api/v1/sii/operaciones/{tipo}` con su hash sha256 y numero de operaciones.
- El contenido del XML corresponde EXACTAMENTE al libro del periodo (correccion: mismas bases/cuotas).
- La presentacion ejecutada (envio con certificado) queda fuera de esta feature y se integra con SPEC-029.
- Empresas no obligadas pueden habilitar SII de forma voluntaria.

## 5. Validaciones del XML generado

- Cumple el XSD de SuministroInfo (version 1.2), validable con el esquema publicado por la AEAT.
- Un solo `RegistroLrFE`/`RegistroLrFR` por factura (con su desglose).
- Importes con 2 o 4 decimales permitidos por el esquema (se usan 4 en base y cuota, 2 en tipos).
- `TipoComunicacion` = 0 (alta) por defecto; las rectificativas usan tipo 4 o complementaria segun el periodo.