# ContabilidadV1

Sistema de contabilidad multiempresa (multi-tenant) para el Plan General Contable
(PGC) español. Backend en Python/FastAPI con PostgreSQL 16+, frontend en Next.js
(TypeScript).

> **Estado actual (2026-09-28)**: Hay 31 feature specs y 1.506 tareas. Las **31 specs
> están completas** (001–031) con 1.506/1.506 tareas marcadas. La suite completa dio
> **2.942 passed / 23 skipped**; la prueba `test_suggest_perf`, flaky conocido bajo carga,
> quedó verde aislada. Contra **PostgreSQL 18.6 real** el contrato de esquema dio
> **19 passed** con las migraciones 000–022 aplicadas. ruff + mypy están limpios (416
> fuentes) y `next build` genera **110 páginas**. No queda ninguna spec diseñada sin
> implementar; consultar [AGENTS.md](AGENTS.md) para el inventario canónico.


## Funcionalidad principal

- **Navegación por superficies (Material Design 3)**: seis superficies (Contabilidad,
  Facturación, Tesorería, Informes, Fiscal y Maestros) con rail fijo, panel contextual,
  barra inferior en móvil y una zona de contexto que muestra siempre con qué usuario,
  en qué empresa y en qué ejercicio se está contabilizando. Cada superficie tiene su
  landing con un resumen del ejercicio activo.
- **Motor de asientos contables** con partida doble estricta (Debe == Haber), diario
  inalterable y auditoría legal inmutable.
- **Multi-tenancy estricto**: aislamiento total de datos por empresa, derivado de la
  sesión autenticada (nunca de datos del cliente).
- **Plan General Contable español** jerárquico (5 niveles, subcuentas auxiliares) con
  seeding automático por empresa.
- **Informes y cierre**: balance de sumas y saldos, libro mayor con saldo acumulado,
  cierre de ejercicio atómico (regularización 6/7 → 129 y bloqueo del periodo).
- **Cierre intermedio y reapertura controlada**: cierre mensual/trimestral con
  balance de comprobación como snapshot inmutable y bloqueo real de la
  contabilización del periodo (servicio + trigger de base de datos), cierre anual
  completo (regularización, cierre de saldos y apertura del ejercicio siguiente) y
  reapertura excepcional con justificación, aprobación, un solo periodo a la vez y un
  asiento rectificativo `ADJUSTMENT`/`REVERSAL` que deja el original intacto.

- **Maestro de terceros** (clientes/proveedores) con validación de NIF/CIF/NIE e IBAN
  (ISO 13616), subcuentas automáticas y saldo derivado.
- **Cobros y pagos** totales y parciales con asiento balanceado e informe de antigüedad.
- **Remesas SEPA** (PAIN.008/CORE/B2B, CSB 19.19), descuentos por pronto pago y
  devoluciones R19/C19 con REVERSAL.
- **Import/export masivo de asientos** (CSV/XLSX) con previsualización dry-run.
- **Asientos multilínea**: creación, anulación (rectificativo REVERSAL con original
  inmutable) e import/export de asientos con N partidas por lado; entrada por teclado
  (Enter añade fila, Ctrl+Supr elimina) con balance en tiempo real.
- **Conciliación bancaria**: importación de extractos (norma 43/19 o CSV), propuestas
  automáticas de cruce, cruce manual trazable, cálculo de diferencia y cierre/archivo
  del período conciliado.
- **Cuentas anuales**: Balance de Situación, Cuenta de Pérdidas y Ganancias y Estado de
  Flujos de Efectivo (EFE) por actividades, con formulación oficial inmutable por
  ejercicio cerrado (snapshot + hash SHA-256).
- **Libros de IVA y modelos fiscales**: libros de emitidas/recibidas/intracomunitarias
  derivados de las facturas, modelos 303/347/349 cuadrados con los libros, exportación con
  trazabilidad y regímenes de recargo de equivalencia y criterio de caja (interfaz SII declarada).
- **Amortización del inmovilizado**: alta de activos (21x) con plan lineal/regresivo y
  prorrateo por días, generación automática de asientos 681/281 por período (sin duplicados,
  con reapertura vía REVERSAL trazable) y baja/venta con cálculo de VNC y resultado.
- **Multi-divisa**: divisas funcional y de operación, conversión con redondeo half-even,
  tipos de cambio sellados e inmutables con histórico consultable, asientos en divisa con
  doble cuadre (divisa + funcional) y línea de redondeo automática, y valoración a cierre
  con diferencias de cambio (668/769).
- **Centros de coste**: catálogo jerárquico (departamento/proyecto/subvención/delegación) con
  closure table, imputación opcional de líneas de asiento sin alterar el balance, inmutabilidad
  de la traza en asientos POSTED (rectificación vía ADJUSTMENT) e informes de costes/ingresos por
  centro y período con subtotales por jerarquía y export CSV/JSON.
- **Plantillas de asientos**: catálogo por empresa de apuntes predefinidos con importes fijos y
  variables, generación de asientos balanceados validados por el motor (cuentas del plan, ejercicio
  abierto y numeración correlativa), gestión de versiones y activación/desactivación sin alterar los
  asientos ya generados (traza inmutable `asiento_generado`).
- **Gestión ONG**: subvenciones con control de disponible y justificación de gastos a nivel de
  línea de asiento (informe concedido/gastado/pendiente con huella SHA-256 y export CSV/JSON),
  libros oficiales diario/mayor/balance/PyG en PDF con canon de 4 decimales, legalización del
  ejercicio con fichero `.txt` y huella (bloqueo de asientos posteriores FR-007), y caja/arqueo:
  movimientos de una subcuenta 570 real (asientos del motor) con arqueos que contrastan saldo
  contable vs efectivo y aprueban diferencias con asiento de ajuste.
- **Medios de pago y efectos**: cartera de cheques/pagarés/letras con estados
  (emitido/cobrado/impagado) e inmutabilidad de los estados finales; cobro con asiento
  balanceado 572↔431 y registro de comisiones; cobros por TPV/tarjeta/transferencia con
  asiento neto (572 + 626 | 430); consulta de cartera con filtros por estado/tipo/tercero/fechas
  y agrupación por estado y tipo.
- **Impuesto sobre Sociedades / Modelo 200**: cálculo provisional o definitivo desde el
  resultado contable y los pagos 473, ajustes y deducciones trazables, contabilización
  balanceada 630/473/4752/4709 con asiento inmutable y soporte Modelo 200 de cinco
  bloques con validación, hash SHA-256 y descarga CSV.
- **Retenciones IRPF y modelos 111/115/190**: acumulación trimestral por perceptor desde
  facturas y rectificativas, clasificación de profesionales/arrendamientos, liquidación
  balanceada 4751/572, NIF obligatorio en el modelo anual, hash SHA-256 y descargas CSV
  autenticadas.
- **Catálogo versionado del plan de cuentas**: versiones numeradas con vigencia sin
  solapes por empresa (garantía a nivel DB), resolución de la versión vigente en una
  fecha, importación de manifiestos CSV/JSON con mapeo automático y reporte de
  pendientes, y reclasificación de saldos al cambiar de normativa con asientos
  `ADJUSTMENT` correlativos y balanceados que dejan intactos los asientos históricos.
- **Presupuestos y desviaciones**: presupuesto anual por combinación cuenta/centro
  de coste/ejercicio con rechazo de duplicados a nivel de base de datos, importación
  masiva CSV/JSON atómica, seguimiento presupuesto vs real con desviación absoluta
  y relativa a 4 decimales (convención de signos por grupo PGC), cuentas sin
  presupuesto marcadas como tales, informes acumulados por centro/cuenta y cierre
  de periodo con snapshot inmutable de la desviación que bloquea nuevas
  modificaciones hasta abrir un periodo nuevo.
- **Previsión de tesorería, EFE y alertas de liquidez**: proyección de saldos y
  movimientos por día/semana/mes a partir de los vencimientos pendientes y de un
  plan manual (pagos recurrentes, cobros estimados) persistente, con exclusión
  trazada de vencidos/cobrados/sin fecha; alertas por periodo con saldo proyectado
  negativo y acciones de reprogramar un pago o incorporar un ingreso; e informe
  **EFE por cuenta y bloque de actividad** (operativa/inversión/financiación) con
  cuadre verificado contra la variación real del diario, cruce con la conciliación
  bancaria como aviso que no bloquea y formulación con overrides de clasificación
  que deja un snapshot inmutable.
- **Exportación integral del tenant (backup y portabilidad)**: genera un ZIP
  descargable con los **17 bloques de datos** de la empresa activa (plan de cuentas y
  sus versiones, asientos, apuntes, terceros, facturas y líneas, vencimientos,
  cobros/pagos, remesas, devoluciones, amortizaciones, cierres, presupuestos,
  previsiones, libros fiscales y configuración), con **manifiesto de inventario** y
  **huella SHA-256 verificable**: la verificación recalcula el hash del binario,
  comprueba el `tenant_id`, los conteos de cada bloque y la huella de contenido, y
  detecta cualquier alteración; admite **filtro por rango de ejercicios** (los
  maestros se exportan íntegros), numeración correlativa por empresa y año, y
  persistencia **inmutable** del snapshot (cabecera, manifiesto y blob rechazan
  UPDATE/DELETE en la base de datos). Añade un bloque de datos normalizados para el
  **SII de la AEAT** (NIF, tipo de factura, base, IVA y total con 4 decimales,
  estado de cuadre) para subida manual al portal; la presentación telemática queda
  fuera de alcance.
- **Documentos adjuntos al asiento** *(SPEC-030, cerrada)*: adjuntar
  uno o varios PDF o imágenes a un asiento del diario, con huella SHA-256, contenido
  inalterable a nivel de base de datos, baja lógica solo en asientos en borrador y traza de
  altas y bajas en la auditoría inmutable. La adjunción es siempre opcional: ningún asiento
  está obligado a tener documentos.
- Pendientes de implementar: documentos adjuntos al asiento (ver
  [AGENTS.md](AGENTS.md) §20).


## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.11+ · FastAPI (async) · SQLAlchemy 2.x async + asyncpg · Pydantic v2 |
| Base de datos | PostgreSQL 16+ (`NUMERIC(18,4)` para importes; prohibido `float`) |
| Frontend | Next.js (App Router) + TypeScript |
| Tests | pytest (`backend/tests/{unit,integration}`; PostgreSQL opt-in vía `TEST_DATABASE_URL`) |

## Estructura del repositorio

```
plan.md                                 # Plan técnico raíz (SPEC-001, PGC)
backend/
  src/
    models/{acct,ar,audit,iam,treasury,fiscal,invoice,inmovilizado,reporting,
             monedas,rbac,costcenters,templates,ngo,catalog,budget,closing,export}
                                         # Modelos SQLAlchemy 2.x (multi-tenant)
    services/                            # journal, acct, auth, reports, closing,
                                         # invoicing, remittance, thirdparty,
                                         # treasury, importexport, audit,
                                         # reconciliation, cycle, vat,
                                          # reporting, inmovilizado, security, forex,
                                          # costcenters, templates, ngo, fiscal,
                                          # catalog, budget, cashflow, export

    api/{acct,auth,journal,reports,treasury,thirdparty,importexport,
         invoicing,fiscal,ciclo,reconciliation,cuentas_anuales,inmovilizado,
          rbac,forex,costcenters,templates,ngo,catalogo,presupuestos,tesoreria,
          closing,export}
                                         # Routers /api/v1
    main.py · config.py · database.py
  migrations/                            # 000_audit_log … 020_export (PostgreSQL)

  tests/{unit,integration,contract}      # pytest (SQLite in-memory + PG opt-in)
  pytest.ini · mypy.ini
  .env                                    # Credenciales locales (ignorado por git);
                                         # la plantilla sin secretos es .env.example
frontend/
  src/app/                               # Next.js App Router: login, cuentas, asientos,
                                         # informes, cierre, terceros, vencimientos,
                                         # cobros, antigüedad, remesas, devoluciones,
                                         # empresas, import-export, conciliación,
                                         # cuentas-anuales, libros-iva, modelos,
                                         # exportaciones, facturacion, inmovilizado,
                                         # permisos, divisas, centros, plantillas, ong,
                                         # efectos, tesoreria (previsiones, efe,
                                         # alertas), anticipos, cesiones,
                                          # impuesto-sociedades, modelo-200, retenciones,
                                          # modelos/190, catalogo (listado, detalle,
                                          # importar, reclasificar), presupuestos
                                          # (definicion, seguimiento, informes),
                                          # cierres (intermedio, anual, reaperturas),
                                          # exportaciones (listado, nueva, detalle)
  src/components/{acct,journal,reporting,treasury,rbac,thirdparty,invoicing,
                  importexport,vat,inmovilizado,forex,costcenters,templates,ngo,export,
                  fiscal,catalog,budget,cashflow,closing}

  src/services/client.ts                 # Cliente HTTP (JWT + X-Empresa-Activa)
specs/
  001-plan-general-contable              # 30 feature specs con: spec.md, plan.md,
  ...                                    # research.md, data-model.md, quickstart.md,
  030-documentos-asiento                 # tasks.md, contracts/
.specify/
  memory/constitution.md                # Constitución del proyecto (NO NEGOCIABLE)
  feature.json                          # Feature activa del Spec Kit
AGENTS.md                               # Guía para agentes de IA
```

## Estado de implementación

**30 specs completas** (1.432/1.432 tareas marcadas):

| Spec | Tema | Tareas |
|---|---|---|
| 001 | Plan General Contable | 42/42 |
| 002 | Motor de asientos contables | 43/43 |
| 003 | Multiempresa y RBAC | 36/36 |
| 004 | Informes y cierre de ejercicio | 53/53 |
| 005 | Import/export de asientos | 43/43 |
| 006 | Asientos multilínea | 40/40 |
| 007 | Facturación operativa | 56/56 |
| 008 | Maestro de terceros | 50/50 |
| 011 | Cobros y pagos | 45/45 |
| 013 | Conciliación bancaria | 54/54 |
| 014 | Amortización del inmovilizado | 49/49 |
| 020 | Remesas SEPA y soporte magnético | 69/69 |
| 009 | Apertura del ejercicio | 37/37 |
| 010 | Cuentas anuales (Balance, PyG y EFE) | 45/45 |
| 012 | Libros de IVA y modelos fiscales | 56/56 |
| 015 | Matriz de permisos por rol | 48/48 |
| 016 | Multi-divisa | 48/48 |
| 017 | Centros de coste | 48/48 |
| 018 | Plantillas de asientos | 42/42 |
| 019 | Gestión ONG (subvenciones, libros y caja) | 53/53 |
| 020 | Remesas SEPA y soporte magnético | 69/69 |
| 021 | Medios de pago y efectos | 44/44 |
| 022 | Anticipos, fondos a cuenta y cesión de cobros | 48/48 |
| 023 | Impuesto sobre Sociedades / Modelo 200 | 44/44 |
| 024 | Retenciones IRPF y modelos 111/115/190 | 48/48 |
| 025 | Catálogo versionado del plan de cuentas | 47/47 |
| 026 | Presupuestos y desviaciones | 42/42 |
| 027 | Previsión de tesorería, EFE y alertas de liquidez | 45/45 |
| 028 | Cierre intermedio y reapertura controlada | 57/57 |
| 029 | Exportación integral del tenant y enlace SII | 52/52 |
| 030 | Documentos adjuntos al asiento | 48/48 |

- Backend verificado el 2026-09-27: **2.659 pytest pass / 21 skipped**; las 2 pruebas
  `test_suggest_perf` del lote principal quedaron verdes aisladas. Contra
  **PostgreSQL 18.6 real**: **2.678 pass / 1 skipped** en la suite completa y
  **18 passed** en el contrato de esquema. ruff + mypy limpios (406 fuentes).
- Frontend verificado: `tsc`, ESLint y `next build` correctos, con **104 rutas**
  (nuevas de SPEC-029: `/exportaciones`, `/exportaciones/nueva` y
  `/exportaciones/[id]`).
- Migraciones PostgreSQL `000`–`020` (007 = RBAC; 008 = forex; 009 = centros de coste;
  010 = plantillas; 011 = ONG; 012 = efectos; 013 = anticipos/cesiones;
  014 = IS/Modelo 200; 015 = retenciones, modelos 111/115/190, cuenta 4751 y triggers;
  016 = catálogo versionado con trigger de vigencia sin solapes;
  017 = presupuestos/desviaciones con unicidad por combinación cuenta-centro-ejercicio,
  un solo periodo de seguimiento abierto y snapshot de desviación append-only;
  018 = previsión de tesorería, con correlatividad de `numero_prevision`, unicidad de
  alerta por bucket, CHECK de saldo negativo y snapshot del EFE append-only;
  019 = cierres, con clave natural del periodo, CHECK `total_debe = total_haber`,
  snapshot del balance append-only, una sola solicitud de reapertura activa por
  periodo y trigger `chk_journal_entry_fecha_abierta`;
  020 = exportación integral, con unicidad del número por (empresa, año), un único
  manifiesto y un único blob por exportación, `ConfigSii` por empresa y triggers
  `chk_exportacion_immutable_*` (el snapshot es inmutable en `lista`/`fallida`) más
  los append-only de manifiesto y blob).
- CI: `.github/workflows/ci.yml` ejecuta PostgreSQL + pytest, ruff, mypy, typecheck,
  ESLint y build frontend.
- Pendiente: no queda ninguna spec diseñada sin implementar. El trabajo
  transversal del helper de siembra de empresas de `conftest.py` **está hecho**
  (`crear_empresa` / `sembrar_empresa_pgc` / `crear_empresas` /
  `sembrar_empresas_pgc`, con cremalla en `test_guard_siembra_empresa.py`); ver
  [AGENTS.md](AGENTS.md) §47.


### Documentos adjuntos al asiento (SPEC-030)

Evidencia documental en el diario: PDF o imagen (JPEG, PNG, TIFF) anclada a un
asiento, con huella SHA-256, contenido inmutable a nivel de base de datos y
baja logica.

- **Opcional por diseno**: ningun asiento esta obligado a tener documentos y
  ninguna operacion contable, fiscal o de cierre depende de ellos. Un asiento
  sin documentos se contabiliza, anula y exporta con normalidad.
- **Formatos**: PDF (hasta 200 paginas) y JPEG, PNG, TIFF. El contenido se
  valida contra la **firma** del fichero, no contra su extension: un JPEG
  renombrado a `.pdf` se rechaza. Limite de 10 MB por documento y 50 por asiento,
  configurables por entorno.
- **Permisos**: `acct:crear` para adjuntar y `acct:baja` para dar de baja, ambos
  del catalogo de roles ya existente.
- **Rutas**: `POST/GET /api/v1/documentos/asiento/{id}`,
  `GET /api/v1/documentos`, `GET /api/v1/documentos/{id}`,
  `GET /api/v1/documentos/{id}/descarga`, `DELETE /api/v1/documentos/{id}`.
- **Pantallas**: la seccion de documentos en el detalle del asiento
  (`/asientos/[id]`) y el listado global con filtros en `/documentos`.

Los documentos adjuntos **no** se incluyen todavia en la exportacion integral del
tenant (SPEC-029) ni en el libro-diario PDF oficial (SPEC-019): queda
declarado como ampliacion posterior.


## Tests

La suite se ejecuta con pytest sobre SQLite en memoria (`backend/tests/`). Para
arrancar un backend de desarrollo:

```bash
cd backend && python -m uvicorn main:app --reload
```

### Siembra de empresas en tests

`backend/tests/conftest.py` es el **unico** sitio donde se da de alta una empresa
para un test. Cuatro funciones, segun lo que necesite el caso:

| Funcion | Cuando |
|---|---|
| `crear_empresa(db, empresa_id)` | el test planta su propio plan de cuentas |
| `sembrar_empresa_pgc(db, empresa_id)` | empresa + PGC base de 7 grupos (lo habitual) |
| `crear_empresas(db, *ids)` | varias empresas sin PGC |
| `sembrar_empresas_pgc(db, *ids)` | varias empresas con PGC (el par A=10 / B=20) |

El NIF y la razon social se derivan de `empresa_id`; solo se pasan a mano cuando
un test afirma sobre el valor. `tests/unit/test_guard_siembra_empresa.py` falla
si alguien vuelve a construir un `Company` a mano, de modo que el helper no se
puede degradar en opcional.


## Configuracion

Variables de entorno (plantilla en `backend/.env.example`; `backend/.env` esta
cubierto por `.gitignore`):

| Variable | Para | Valor por defecto |
|---|---|---|
| `DATABASE_URL` | conexion de PostgreSQL | `postgresql+asyncpg://postgres:postgres@localhost:5432/contabilidad` |
| `TEST_DATABASE_URL` | habilita los tests de contrato contra PostgreSQL | sin valor (se omiten) |
| `SECRET_KEY` | **clave de firma de los JWT** | vacio: se genera una aleatoria por proceso y se avisa al arrancar |
| `ALGORITHM` | algoritmo HMAC del token | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | vigencia del token | `30` |
| `APP_NAME` / `APP_VERSION` | metadatos de la app | `ContabilidadV1` / `0.1.0` |
| `CORS_ORIGINS` | origenes permitidos (separados por comas) | `http://localhost:3000` |

`SECRET_KEY` es **obligatoria en produccion** y no existe ninguna constante de
desarrollo en el codigo. Generar una con:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Si falta, el backend firma con un secreto aleatorio de un solo proceso y lo
registra como aviso al arrancar: los tokens funcionan, pero no sobreviven a un
reinicio del servidor.

## Principios del dominio (resumen)

1. **Partida doble estricta**: todo asiento valida `SUM(Debe) == SUM(Haber)` en backend.
2. **Inmutabilidad**: los asientos confirmados no se actualizan ni borran; las
   correcciones usan `REVERSAL`/`ADJUSTMENT` enlazados. Auditoría inmutable (WORM) en
   la misma transacción ACID.
3. **Multi-tenancy estricto**: toda consulta/mutación filtra por la empresa activa.
4. **Correlatividad**: numeración sin saltos por (empresa, ejercicio) con bloqueo atómico.
5. **Pruebas obligatorias**: ninguna tarea termina sin pytest de balance + aislamiento multi-tenant.

Detalles completos en `.specify/memory/constitution.md`.

## Comenzar

El núcleo contable está implementado y verificado. El punto de partida recomendado es
[AGENTS.md](AGENTS.md) (contexto para desarrolladores) y, para continuar, la spec pendiente en este orden
sugerido: **030**.
El recuento vivo esta en [pendientes.md](pendientes.md).

```powershell
# Backend (desde backend/)
..\.venv\Scripts\python.exe -m pytest                 # 2659 passed, 21 skipped; perf verde aislado
..\.venv\Scripts\python.exe -m ruff check src tests
..\.venv\Scripts\python.exe -m mypy -p api -p models -p services -p database -p base -p db -p main -p config

# Contra PostgreSQL 18.6 real (credenciales en backend/.env)
$env:PYTHONPATH="src"; ..\.venv\Scripts\python.exe -m db.migrate
$env:PYTHONPATH="src"; $env:TEST_DATABASE_URL="postgresql+asyncpg://postgres:<password>@localhost:5432/contabilidad"
..\.venv\Scripts\python.exe -m pytest                   # 2678 passed, 1 skipped (18 en tests/integration/test_pg_schema.py)

# Servidor
$env:PYTHONPATH="src"; ..\.venv\Scripts\python.exe -m uvicorn main:app --reload

# Frontend (desde frontend/)
node node_modules/typescript/bin/tsc --noEmit
node node_modules/eslint/bin/eslint.js src
$env:NEXT_TELEMETRY_DISABLED="1"; node node_modules/next/dist/bin/next build
```