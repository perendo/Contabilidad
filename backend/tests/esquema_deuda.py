"""La deuda de esquema que se admite a sabias.

Un solo sitio. No uno por test.

El motivo esta en `reparacion.md` y en la seccion 52 de `AGENTS.md`: SPEC-013 se
cerro con 54/54 tareas, sus seis puertas en verde y sus seis tablas sin existir en
PostgreSQL, porque la puerta que habia comprobaba las migraciones **declaradas** y
no las **faltantes**. Dos inventarios, uno en un test y otro en otro, vuelven a
separarse en cuanto uno se actualiza y el otro no. Uno solo, importado por los dos,
no puede.

## Como se usa esta lista

Es una lista de deuda verificada, no de "fallo conocido". Dos reglas y ninguna
tercera:

1. **Solo puede encogerse.** Cuando una tabla (o una columna) se migra, se borra de
   aqui. Anadir es siempre un fallo.
2. **No puede mentir en ninguna de las dos direcciones.** Si la lista nombra algo
   que ya esta bien, hay que borrarlo (un guard lo comprueba). Si deja de nombrar
   algo que esta mal, el otro guard lo comprueba (esta en un solo sitio, asi que
   no hay "otro": lo comprueba el guard que cruza los modelos con el esquema).

Cada entrada dice de que spec es, porque la deuda sin duenno es deuda que nadie
se hace cargo.
"""

from __future__ import annotations

#: Tablas que los modelos declaran y que ninguna migracion crea todavia.
#:
#: **Vacio desde el 2026-09-29.** Estuvo en 27 y se han migrado todas, en cinco ficheros:
#:
#: - `027_maestros_comerciales.sql`: `tercero`, `tercero_subcuenta`, `serie_factura`,
#:   `factura`, `factura_linea` (SPEC-007, SPEC-008)
#: - `028_cobros_vencimientos.sql`: `vencimiento`, `cobro_pago` (SPEC-011)
#: - `029_remesas_complemento.sql`: `secuencia_remesa`, `mandato_sepa`,
#:   `condicion_pronto_pago`, `blob_fichero`, `remesa`, `recibo_remesa`,
#:   `devolucion_recibo`, `reclamacion`, `cobro_conciliado` (SPEC-020)
#: - `030_inmovilizado_completo.sql`: `activo_inmovilizado`, `plan_amortizacion`,
#:   `amortizacion_generada`, `baja_activo` (SPEC-014)
#: - `031_informes_iva.sql`: `configuracion_informe`, `formulacion_cuentas_anuales`,
#:   `clasificacion_efe`, `periodo_fiscal`, `exportacion_modelo`, `configuracion_sii`,
#:   `iva_diferido_caja` (SPEC-010, SPEC-012)
#:
#: El conjunto se queda, aunque vacio, y sus dos guards tambien: son los que impediran
#: que vuelva a crearse un modelo sin su migracion. Un conjunto vacio con guard es
#: distinto de ningun conjunto, que es como estaba esto antes de que
#: `test_toda_tabla_del_orm_tiene_migracion` viera la SPEC-013.
TABLAS_SIN_MIGRACION: set[str] = set()

#: Columnas que la migracion crea de una manera y el modelo de otra.
#:
#: `(tabla, columna)`. Mismo contrato que `TABLAS_SIN_MIGRACION`: solo encoge.
#:
#: **Vacio desde el 2026-09-29.** La unica entrada que ha tenido fue
#: `manifiesto_exportacion.n_bloques`: el modelo declara `default=0` y
#: `migrations/020_export.sql` la creo sin defecto. Corregido en
#: `026_manifiesto_n_bloques.sql`, que existe precisamente para eso: editar 020 no la
#:: deshacia, y reaplicarla revienta.
COLUMNAS_INCONSISTENTES: set[tuple[str, str]] = set()

#: Referencias que el modelo deja como UUID suelto, sin clave foranea.
#:
#: `(tabla, columna)`. Son 51 en todo el ORM, y son deuda **por decision**, no por
#: descuido: el 2026-09-29 se decidio migrar los modelos tal cual, sin anadir claves
#: foraneas que el ORM no declara. Se escribieron a mano las que iban a crearse (las de
#: `TABLAS_SIN_MIGRACION`) y se anyone's las que ya estaban en la base, para que la
#: lista sea el retrato completo y no solo la parte que se esta repairing.
#:
#: Por que no se anaden y ya esta: una FK que el ORM no conoce puede convertir en 500 un
#: `INSERT` que hoy funciona, y la constitucion III ya se cumple en el sitio que
#: importa — toda consulta pasa por `Depends(get_empresa_id)` y filtra por `empresa_id`.
#: Lo que la FK daria aqui es integridad referencial en la base, que es una garantia
#: distinta y mas fuerte, y esa merece su propio analisis.
#:
#: El riesgo concreto que queda: una referencia a una fila de otra empresa no la
#: detectaria la base y habria que detectarla en el servicio. Con las FKs compuestas que
#: si declara el modelo (`factura` -> `serie_factura`, -> `tercero`, -> `journal_entry`, y
#: tambien `factura_original_id`) eso ya no es posible en la parte que mas importa.
#:
#: No es un patron reservado a estas 27: 29 de las 51 son de tablas cuya migracion ya
#: estaba escrita y aplicada. Es una decision del proyecto, heredada de las primeras
#: specs, y por eso se documenta entera en vez de anotarse solo lo que falta.
#:
#: Guard: `test_la_lista_de_referencias_sin_fk_no_miente` y su pareja
#: `test_ninguna_referencia_anotada_declara_ya_clave_foranea`, en
#: `tests/unit/test_migrations.py`. El segundo es el que obliga a cerrar una entrada.
REFERENCIAS_SIN_FK: set[tuple[str, str]] = {
    # --- Las 22 que se van a crear con las 27 tablas pendientes ---------------
    # SPEC-008 (terceros)
    ("tercero_subcuenta", "tercero_id"),
    ("condicion_pronto_pago", "tercero_id"),
    ("mandato_sepa", "tercero_id"),
    # SPEC-011 (cobros y vencimientos)
    ("vencimiento", "tercero_id"),
    ("vencimiento", "factura_id"),
    ("vencimiento", "remesa_id"),
    ("cobro_pago", "vencimiento_id"),
    ("cobro_pago", "journal_entry_id"),
    # SPEC-020 (remesas SEPA)
    ("recibo_remesa", "vencimiento_id"),
    ("recibo_remesa", "tercero_id"),
    ("recibo_remesa", "descuento_id"),
    ("recibo_remesa", "asiento_cobro_id"),
    ("remesa", "fichero_id"),
    ("condicion_pronto_pago", "override_factura_id"),
    ("devolucion_recibo", "asiento_reversal_id"),
    ("cobro_conciliado", "movimiento_id"),
    # SPEC-010 / SPEC-012 (informes y libros de IVA)
    ("clasificacion_efe", "linea_id"),
    ("exportacion_modelo", "periodo_id"),
    ("iva_diferido_caja", "factura_id"),
    ("iva_diferido_caja", "vencimiento_id"),
    # No son UUID: `exportacion_modelo.usuario_id` y
    # `formulacion_cuentas_anuales.usuario_id` son VARCHAR(120) porque el autor no
    # tiene por que ser un usuario del sistema (los asientos de las specs
    # anteriores escriben "system").
    ("exportacion_modelo", "usuario_id"),
    ("formulacion_cuentas_anuales", "usuario_id"),
    # --- Las 29 preexistentes (su migracion ya esta escrita y aplicada) -------
    # SPEC-002 / SPEC-004 (motor de asientos y cierre anual)
    ("journal_entry", "original_id"),
    ("journal_entry", "referencia_cierre_id"),
    ("journal_entry_line", "account_id"),
    ("fiscal_year", "cierre_entry_id"),
    ("fiscal_year", "regularizacion_entry_id"),
    # SPEC-001 / SPEC-003 (plan de cuentas, RBAC, auditoria)
    ("companies", "company_id"),
    ("audit_log", "entidad_id"),
    ("matriz_permiso", "concesion_id"),
    # SPEC-009 (apertura del ejercicio)
    ("ejercicio_contable", "apertura_entry_id"),
    ("ejercicio_contable", "apertura_reversal_entry_id"),
    # SPEC-013 (conciliacion bancaria)
    ("extracto_bancario", "cuenta_id"),
    ("conciliacion", "cuenta_id"),
    ("conciliacion", "extracto_id"),
    ("conciliacion", "periodo_conciliado_id"),
    ("alerta_conciliacion", "movimiento_id"),
    ("cruce_conciliacion", "apunte_id"),
    ("cruce_conciliacion", "usuario_id"),
    ("periodo_conciliado", "cuenta_id"),
    ("periodo_conciliado", "usuario_id"),
    # SPEC-017 / SPEC-019 / SPEC-021 (centros de coste, ONG, medios de pago)
    ("centro_coste", "subvencion_id"),
    ("efecto", "tercero_id"),
    ("efecto", "asiento_cobro_id"),
    ("efecto", "asiento_impago_id"),
    ("cobro_medio", "vencimiento_id"),
    ("cobro_medio", "asiento_cobro_id"),
    # SPEC-028 / SPEC-029 (cierre intermedio, exportacion integral)
    ("periodo_cerrado", "balanza_id"),
    ("config_sii", "entidad_representante_id"),
    ("exportacion", "blob_id"),
    # `manifiesto_exportacion.tenant_id` es redundante a proposito: existe para
    # verificar la multi-tenancy del snapshot, y si lo referenciara la tabla de cabecera
    # dejaria de comprobar nada.
    ("manifiesto_exportacion", "tenant_id"),
}

#: Claves foraneas que el modelo declara de UNA SOLA columna y que apuntan a una
#: tabla que si tiene `empresa_id`, o sea que no la miran.
#:
#: Una FK de este tipo no impide que una fila referencie a otra empresa: la base lo
#: acepta. Se recoge en la auditoria, que es de solo lectura, asi que no permite
#: escribir nada; el riesgo es de lectura, no de integridad.
#:
#: - `evento_auditoria_acceso.rol_id -> roles.id` (SPEC-015, `migrations/007_rbac.sql`).
#:   Encontrado el 2026-09-29 al escribir `test_las_fk_compuestas_por_empresa_no_dejan_
#:   huecos`, que ya existia en otra forma. Corregirlo exige cambiar el modelo y anadir
#:   una migracion nueva sobre una ya aplicada, asi que no se ha hecho aqui: queda
#:   declarado para que la decision sea explicita y no un descuido.
#:
#: **Solo puede encogerse**, igual que las listas de arriba. Anadir una entrada aqui
#: tiene que ser una decision escrita, no un descuido.
FK_CIEGAS_AL_TENANT: set[str] = {
    "evento_auditoria_acceso.rol_id",
}


def deuda_completa() -> set[tuple[str, str | None]]:
    """Las dos listas en una sola, como pares `(tabla, columna)`.

    La columna es `None` cuando lo que falta es la tabla entera. Un solo conjunto
    permite que los guards comparen contra una lista sin tener que reunir las dos
    mitades en cada comparacion.
    """
    tablas = {(t, None) for t in TABLAS_SIN_MIGRACION}
    return tablas | set(COLUMNAS_INCONSISTENTES)
