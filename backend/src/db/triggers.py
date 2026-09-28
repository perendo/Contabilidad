"""Database-level immutability and structure triggers (constitución I, II, III).

PostgreSQL receives the canonical rules from ``backend/migrations/*.sql``; the
test suite runs on SQLite, so equivalent triggers are installed here to make the
guarantee verifiable without a PostgreSQL instance.

Rules:
- ``journal_entry`` rows in ``POSTED``/``CANCELLED`` reject UPDATE and DELETE.
- ``journal_entry_line`` rows whose parent entry is ``POSTED``/``CANCELLED``
  reject UPDATE and DELETE.
- ``audit_log`` is append-only (WORM): rejects UPDATE and DELETE.
- ``evento_auditoria_acceso`` is append-only (SPEC-015): rejects UPDATE/DELETE.
- ``tipo_cambio`` sealed rows (sellado = 1) reject ratio/divisa/fecha UPDATE and
  DELETE (SPEC-016, constitución II).
- ``diferencia_cambio`` is append-only (SPEC-016, constitución II): rejects
  UPDATE/DELETE (the valoración is persisted, corrections are new rows).
- ``imputacion_centro`` (SPEC-017, constitución II): rejects UPDATE/DELETE when
  the parent entry is POSTED/CANCELLED; draft entries may be re-imputed.
- ``centro_coste`` (SPEC-017 FR-005): rejects physical DELETE when the center
  has imputations or descendants (only deactivation is allowed).
- ``asiento_generado`` (SPEC-018, constitución II): append-only trace of
  template-generated entries; rejects UPDATE/DELETE.
- ``plantilla_asiento`` (SPEC-018 FR-006): rejects physical DELETE when the
  template has generated entries (only deactivation is allowed).
- ``efecto`` (SPEC-021, constitución II): rows in final state
  (``cobrado``/``impagado``) reject UPDATE and DELETE (the impago correction
  is a new REVERSAL entry plus re-emission).
- ``companies`` insert seeds the SPEC-015 catalog, base roles and default
  matrix for the new company (trg_companies_rbac_seed), mirroring the
  PostgreSQL trigger of ``migrations/007_rbac.sql`` and the ORM idempotent
  seeding of ``services/security``.
- ``account_plan`` structure validation (chk_account_plan_structure).
- ``account_plan`` selectable sync (sync_account_plan_selectable).
- ``account_plan`` protection (chk_account_plan_protected).
- ``catalogo_version`` (SPEC-025 FR-006/SC-004): rejects INSERT/UPDATE whose
  vigencia range overlaps another non-anulled version of the same company
  (trg_catalogo_version_vigencia, SQLite mirror of ``016_catalogo.sql``).
- ``desviacion`` (SPEC-026, constitución II): el snapshot del cierre es
  append-only; rechaza UPDATE y DELETE (espejo de ``017_presupuestos.sql``).
- ``informe_efe`` / ``linea_efe`` (SPEC-027, constitucion II): el EFE formulado
  es un snapshot inmutable; rechazan UPDATE y DELETE (espejo de
  ``018_cashflow.sql``).
- ``balanza_periodo`` / ``balanza_periodo_linea`` (SPEC-028, constitucion II): el
  balance de comprobacion de un periodo cerrado es un snapshot inmutable;
  rechazan UPDATE y DELETE (espejo de ``019_cierres.sql``).
- ``journal_entry`` (SPEC-028 FR-001, research D9): rechaza el INSERT de una
  fecha que cae en un ``periodo_cerrado`` bloqueante de la misma empresa
  (espejo de ``chk_journal_entry_fecha_abierta``). Los tipos de cierre
  (``REGULARIZACION``/``CIERRE``/``OPENING``/``OPENING_REVERSAL``) estan
  exentos: el cierre anual se fecha el ultimo dia del ejercicio.
- ``exportacion`` (SPEC-029, research D9): una vez en estado ``lista`` o
  ``fallida`` la exportacion es un snapshot inmutable y rechaza UPDATE y
  DELETE; solo se admite la transicion ``en_proceso -> lista|fallida`` que
  resuelve la propia generacion (espejo de ``020_export.sql``).
- ``manifiesto_exportacion``, ``manifiesto_bloque`` y ``blob_exportacion``
  (SPEC-029): append-only en cualquier estado; son la evidencia de integridad.
- ``documento_asiento`` (SPEC-030, constitucion II, research D3): el contenido,
  el nombre, la huella y el resto de la evidencia son inmutables; solo se
  admite el ``UPDATE`` de las cuatro columnas de la baja logica. El ``DELETE``
  fisico se rechaza siempre: la baja es logica (FR-012).
"""


from __future__ import annotations

from sqlalchemy import Connection

_TRIGGERS_SQLITE: tuple[str, ...] = (
    """
    CREATE TRIGGER IF NOT EXISTS trg_journal_entry_immutable_update
    BEFORE UPDATE ON journal_entry
    FOR EACH ROW
    WHEN OLD.estado IN ('POSTED', 'CANCELLED')
      AND NOT (OLD.estado = 'POSTED' AND NEW.estado = 'CANCELLED')
    BEGIN
        SELECT RAISE(
            ABORT,
            'journal_entry: asiento POSTED/CANCELLED inmutable (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_journal_entry_immutable_delete
    BEFORE DELETE ON journal_entry
    FOR EACH ROW
    WHEN OLD.estado IN ('POSTED', 'CANCELLED')
    BEGIN
        SELECT RAISE(
            ABORT,
            'journal_entry: asiento POSTED/CANCELLED inmutable (DELETE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_journal_entry_line_immutable_update
    BEFORE UPDATE ON journal_entry_line
    FOR EACH ROW
    WHEN (
        SELECT estado FROM journal_entry WHERE id = OLD.journal_entry_id
    ) IN ('POSTED', 'CANCELLED')
    BEGIN
        SELECT RAISE(
            ABORT,
            'journal_entry_line: linea de asiento POSTED/CANCELLED inmutable (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_journal_entry_line_immutable_delete
    BEFORE DELETE ON journal_entry_line
    FOR EACH ROW
    WHEN (
        SELECT estado FROM journal_entry WHERE id = OLD.journal_entry_id
    ) IN ('POSTED', 'CANCELLED')
    BEGIN
        SELECT RAISE(
            ABORT,
            'journal_entry_line: linea de asiento POSTED/CANCELLED inmutable (DELETE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_audit_log_immutable_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'audit_log: el log de auditoria es inmutable (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_audit_log_immutable_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'audit_log: el log de auditoria es inmutable (DELETE denegado)'
        );
    END
    """,
    # evento_auditoria_acceso append-only (SPEC-015 FR-005)
    """
    CREATE TRIGGER IF NOT EXISTS trg_evento_auditoria_acceso_immutable_update
    BEFORE UPDATE ON evento_auditoria_acceso
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'evento_auditoria_acceso: el log de accesos es inmutable (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_evento_auditoria_acceso_immutable_delete
    BEFORE DELETE ON evento_auditoria_acceso
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'evento_auditoria_acceso: el log de accesos es inmutable (DELETE denegado)'
        );
    END
    """,
    # empresas -> catálogo + roles + matriz por defecto (SPEC-015)
    """
    CREATE TRIGGER IF NOT EXISTS trg_companies_rbac_seed
    AFTER INSERT ON companies
    FOR EACH ROW
    BEGIN
        INSERT OR IGNORE INTO permiso_operacion (id, modulo, operacion, descripcion, requiere_datos_contables)
        SELECT lower(hex(randomblob(16))), m.modulo, o.operacion,
               o.operacion || ' ' || m.modulo,
               CASE WHEN m.modulo = 'rbac' OR o.operacion = 'ver' THEN 0 ELSE 1 END
          FROM (
               SELECT 'acct' AS modulo UNION ALL SELECT 'ar' UNION ALL
               SELECT 'treasury' UNION ALL SELECT 'bank' UNION ALL
               SELECT 'inmovilizado' UNION ALL SELECT 'divisas' UNION ALL
               SELECT 'reporting' UNION ALL SELECT 'fiscal' UNION ALL
               SELECT 'invoicing' UNION ALL SELECT 'centros' UNION ALL
                SELECT 'ngo' UNION ALL SELECT 'presupuestos' UNION ALL
                SELECT 'cierres' UNION ALL
                SELECT 'export' UNION ALL
                SELECT 'rbac'

          ) m,
          (
               SELECT 'ver' AS operacion UNION ALL SELECT 'crear' UNION ALL
               SELECT 'editar' UNION ALL SELECT 'aprobar' UNION ALL
               SELECT 'importar_exportar' UNION ALL SELECT 'configurar' UNION ALL
               SELECT 'baja' UNION ALL SELECT 'cerrar'
          ) o
          WHERE NOT (m.modulo = 'rbac' AND o.operacion NOT IN ('ver', 'configurar'))
            AND NOT (m.modulo = 'export'
                     AND o.operacion NOT IN ('ver', 'crear', 'configurar'));
        INSERT OR IGNORE INTO roles (id, empresa_id, nombre, es_global_flag)
        VALUES (lower(hex(randomblob(16))), NEW.company_id, 'ADMIN', 0),
               (lower(hex(randomblob(16))), NEW.company_id, 'ACCOUNTANT', 0),
               (lower(hex(randomblob(16))), NEW.company_id, 'READ_ONLY', 0);
        INSERT OR IGNORE INTO matriz_permiso (id, empresa_id, rol_id, permiso_id)
        SELECT lower(hex(randomblob(16))), r.empresa_id, r.id, p.id
          FROM roles r, permiso_operacion p
         WHERE r.empresa_id = NEW.company_id
           AND (
                (r.nombre = 'ADMIN')
                OR (p.modulo = 'rbac' AND p.operacion = 'ver')
                OR (r.nombre = 'ACCOUNTANT' AND p.modulo != 'rbac'
                    AND p.operacion IN ('ver', 'crear', 'editar', 'baja'))
                OR (r.nombre = 'READ_ONLY' AND p.modulo != 'rbac'
                    AND p.operacion = 'ver')
           );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_journal_entry_balance_post
    AFTER UPDATE OF estado ON journal_entry
    FOR EACH ROW
    WHEN NEW.estado IN ('POSTED', 'CANCELLED')
    BEGIN
        SELECT CASE
            WHEN (
                SELECT COUNT(*) FROM journal_entry_line
                WHERE empresa_id = NEW.empresa_id
                  AND journal_entry_id = NEW.id
                  AND debe > 0
            ) = 0
            OR (
                SELECT COUNT(*) FROM journal_entry_line
                WHERE empresa_id = NEW.empresa_id
                  AND journal_entry_id = NEW.id
                  AND haber > 0
            ) = 0
            OR (
                SELECT COALESCE(SUM(debe), 0) FROM journal_entry_line
                WHERE empresa_id = NEW.empresa_id
                  AND journal_entry_id = NEW.id
            ) != (
                SELECT COALESCE(SUM(haber), 0) FROM journal_entry_line
                WHERE empresa_id = NEW.empresa_id
                  AND journal_entry_id = NEW.id
            )
            THEN RAISE(ABORT, 'journal_entry: asiento desbalanceado')
        END;
    END
    """,
    # account_plan structure validation (chk_account_plan_structure)
    # Using WHEN clauses for conditions (SQLite doesn't support IF/ELSE in triggers)
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_structure_insert
    BEFORE INSERT ON account_plan
    FOR EACH ROW
    WHEN NEW.code GLOB '*[^0-9]*'  -- contains non-digit
    BEGIN
        SELECT RAISE(ABORT, 'account_plan: código debe ser numérico');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_structure_insert_level
    BEFORE INSERT ON account_plan
    FOR EACH ROW
    WHEN (NEW.level BETWEEN 1 AND 4 AND LENGTH(NEW.code) != NEW.level)
       OR (NEW.level = 5 AND (LENGTH(NEW.code) < 5 OR LENGTH(NEW.code) > 8))
    BEGIN
        SELECT RAISE(ABORT, 'account_plan: nivel/longitud inconsistentes');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_structure_insert_parent
    BEFORE INSERT ON account_plan
    FOR EACH ROW
    WHEN NEW.parent_id IS NOT NULL
      AND (
        NOT EXISTS (
          SELECT 1 FROM account_plan
          WHERE id = NEW.parent_id
            AND tenant_id = NEW.tenant_id
            AND level = NEW.level - 1
            AND is_active = 1
        )
        OR NOT EXISTS (
          SELECT 1 FROM account_plan p
          WHERE p.id = NEW.parent_id AND NEW.code LIKE p.code || '%'
        )
      )
    BEGIN
        SELECT RAISE(ABORT, 'account_plan: padre inválido o de otra empresa');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_structure_insert_no_parent
    BEFORE INSERT ON account_plan
    FOR EACH ROW
    WHEN NEW.parent_id IS NULL AND NEW.level != 1
    BEGIN
        SELECT RAISE(ABORT, 'account_plan: cuenta de nivel > 1 sin padre');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_structure_update
    BEFORE UPDATE ON account_plan
    FOR EACH ROW
    WHEN NEW.code GLOB '*[^0-9]*'
    BEGIN
        SELECT RAISE(ABORT, 'account_plan: código debe ser numérico');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_structure_update_level
    BEFORE UPDATE ON account_plan
    FOR EACH ROW
    WHEN (NEW.level BETWEEN 1 AND 4 AND LENGTH(NEW.code) != NEW.level)
       OR (NEW.level = 5 AND (LENGTH(NEW.code) < 5 OR LENGTH(NEW.code) > 8))
    BEGIN
        SELECT RAISE(ABORT, 'account_plan: nivel/longitud inconsistentes');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_structure_update_parent
    BEFORE UPDATE ON account_plan
    FOR EACH ROW
    WHEN NEW.parent_id IS NOT NULL
      AND (
        NOT EXISTS (
          SELECT 1 FROM account_plan
          WHERE id = NEW.parent_id
            AND tenant_id = NEW.tenant_id
            AND level = NEW.level - 1
            AND is_active = 1
        )
        OR NOT EXISTS (
          SELECT 1 FROM account_plan p
          WHERE p.id = NEW.parent_id AND NEW.code LIKE p.code || '%'
        )
      )
    BEGIN
        SELECT RAISE(ABORT, 'account_plan: padre inválido o de otra empresa');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_structure_update_no_parent
    BEFORE UPDATE ON account_plan
    FOR EACH ROW
    WHEN NEW.parent_id IS NULL AND NEW.level != 1
    BEGIN
        SELECT RAISE(ABORT, 'account_plan: cuenta de nivel > 1 sin padre');
    END
    """,
    # account_plan selectable sync (sync_account_plan_selectable)
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_selectable_insert
    AFTER INSERT ON account_plan
    FOR EACH ROW
    WHEN NEW.parent_id IS NOT NULL
    BEGIN
        UPDATE account_plan
           SET is_selectable = 0
         WHERE id = NEW.parent_id AND tenant_id = NEW.tenant_id;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_selectable_insert_self
    AFTER INSERT ON account_plan
    FOR EACH ROW
    BEGIN
        UPDATE account_plan
           SET is_selectable = CASE WHEN NEW.level >= 4 THEN 1 ELSE 0 END
         WHERE id = NEW.id AND tenant_id = NEW.tenant_id;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_selectable_update
    AFTER UPDATE OF parent_id ON account_plan
    FOR EACH ROW
    WHEN OLD.parent_id IS NOT NULL AND OLD.parent_id != NEW.parent_id
    BEGIN
        -- Old parent may regain selectable if no more children
        UPDATE account_plan
           SET is_selectable = CASE
                WHEN NOT EXISTS (
                    SELECT 1 FROM account_plan WHERE parent_id = OLD.parent_id AND tenant_id = OLD.tenant_id
                ) AND level >= 4 THEN 1 ELSE 0
            END
         WHERE id = OLD.parent_id AND tenant_id = OLD.tenant_id;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_selectable_update_new_parent
    AFTER UPDATE OF parent_id ON account_plan
    FOR EACH ROW
    WHEN NEW.parent_id IS NOT NULL
    BEGIN
        UPDATE account_plan
           SET is_selectable = 0
         WHERE id = NEW.parent_id AND tenant_id = NEW.tenant_id;
    END
    """,
    # account_plan protection (chk_account_plan_protected)
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_protected_update
    BEFORE UPDATE ON account_plan
    FOR EACH ROW
    WHEN OLD.is_active = 1 AND NEW.is_active = 0
      AND EXISTS (
        SELECT 1 FROM journal_entry_line
        WHERE account_id = OLD.id AND empresa_id = OLD.tenant_id
      )
    BEGIN
        SELECT RAISE(ABORT, 'account_plan: no se puede desactivar una cuenta con asientos asociados');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_protected_delete
    BEFORE DELETE ON account_plan
    FOR EACH ROW
    WHEN EXISTS (
      SELECT 1 FROM account_plan WHERE parent_id = OLD.id AND tenant_id = OLD.tenant_id
    )
    BEGIN
        SELECT RAISE(ABORT, 'account_plan: no se puede eliminar la cuenta (tiene hijas)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_account_plan_protected_delete_entries
    BEFORE DELETE ON account_plan
    FOR EACH ROW
    WHEN EXISTS (
      SELECT 1 FROM journal_entry_line
      WHERE account_id = OLD.id AND empresa_id = OLD.tenant_id
    )
    BEGIN
        SELECT RAISE(ABORT, 'account_plan: no se puede eliminar la cuenta (tiene imputaciones)');
    END
    """,
    # tipo_cambio sellado inmutable (SPEC-016 FR-003 / constitución II)
    """
    CREATE TRIGGER IF NOT EXISTS trg_tipo_cambio_sellado_ratio_update
    BEFORE UPDATE OF ratio ON tipo_cambio
    FOR EACH ROW
    WHEN OLD.sellado = 1 AND NOT (NEW.ratio IS OLD.ratio)
    BEGIN
        SELECT RAISE(
            ABORT,
            'tipo_cambio: ratio de tipo sellado inmutable (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_tipo_cambio_sellado_delete
    BEFORE DELETE ON tipo_cambio
    FOR EACH ROW
    WHEN OLD.sellado = 1
    BEGIN
        SELECT RAISE(
            ABORT,
            'tipo_cambio: tipo sellado inmutable (DELETE denegado)'
        );
    END
    """,
    # diferencia_cambio inmutabilidad (SPEC-016 / constitución II)
    """
    CREATE TRIGGER IF NOT EXISTS trg_diferencia_cambio_immutable_update
    BEFORE UPDATE ON diferencia_cambio
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'diferencia_cambio: la valoración es inmutable (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_diferencia_cambio_immutable_delete
    BEFORE DELETE ON diferencia_cambio
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'diferencia_cambio: la valoración es inmutable (DELETE denegado)'
        );
    END
    """,
    # imputacion_centro append-only: inmutable cuando el asiento es POSTED/CANCELLED
    # (SPEC-017 FR-005 / constitución II); en borrador se puede reasignar/quitar.
    """
    CREATE TRIGGER IF NOT EXISTS trg_imputacion_centro_immutable_update
    BEFORE UPDATE ON imputacion_centro
    FOR EACH ROW
    WHEN (
        SELECT estado FROM journal_entry WHERE id = OLD.asiento_id
    ) IN ('POSTED', 'CANCELLED')
    BEGIN
        SELECT RAISE(
            ABORT,
            'imputacion_centro: la imputacion de un asiento POSTED/CANCELLED es inmutable'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_imputacion_centro_immutable_delete
    BEFORE DELETE ON imputacion_centro
    FOR EACH ROW
    WHEN (
        SELECT estado FROM journal_entry WHERE id = OLD.asiento_id
    ) IN ('POSTED', 'CANCELLED')
    BEGIN
        SELECT RAISE(
            ABORT,
            'imputacion_centro: la imputacion de un asiento POSTED/CANCELLED es inmutable'
        );
    END
    """,
    # centro_coste: no se puede borrar un centro con imputaciones o descendientes (FR-005)
    """
    CREATE TRIGGER IF NOT EXISTS trg_centro_coste_no_delete
    BEFORE DELETE ON centro_coste
    FOR EACH ROW
    WHEN EXISTS (
        SELECT 1 FROM imputacion_centro
        WHERE empresa_id = OLD.empresa_id AND centro_coste_id = OLD.id
    )
    OR EXISTS (
        SELECT 1 FROM jerarquia_centro
        WHERE empresa_id = OLD.empresa_id
          AND ancestro_id = OLD.id AND descendiente_id <> OLD.id
    )
    BEGIN
        SELECT RAISE(
            ABORT,
            'centro_coste: no se puede eliminar un centro con imputaciones o descendientes'
        );
    END
    """,
    # asiento_generado es append-only (SPEC-018 FR-006 / constitución II):
    # la traza plantilla→asiento no se reescribe ni se borra.
    """
    CREATE TRIGGER IF NOT EXISTS trg_asiento_generado_immutable_update
    BEFORE UPDATE ON asiento_generado
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'asiento_generado: la traza generada es inmutable (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_asiento_generado_immutable_delete
    BEFORE DELETE ON asiento_generado
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'asiento_generado: la traza generada es inmutable (DELETE denegado)'
        );
    END
    """,
    # plantilla_asiento: no se borra físicamente si tiene asientos generados
    # (SPEC-018 FR-006 / D6); solo se inactiva.
    """
    CREATE TRIGGER IF NOT EXISTS trg_plantilla_asiento_no_delete
    BEFORE DELETE ON plantilla_asiento
    FOR EACH ROW
    WHEN EXISTS (
        SELECT 1 FROM asiento_generado
        WHERE empresa_id = OLD.empresa_id AND plantilla_id = OLD.id
    )
    BEGIN
        SELECT RAISE(
            ABORT,
            'plantilla_asiento: no se puede eliminar una plantilla con asientos generados'
        );
    END
    """,
    # SPEC-019 (ONG): append-only de libro_oficial y movimiento_caja;
    # legalizacion no se borra (constitución II). gasto_imputado admite DELETE
    # porque la desimputación de US1 se audita y la inmutabilidad real reside
    # en el diario.
    """
    CREATE TRIGGER IF NOT EXISTS trg_libro_oficial_immutable_update
    BEFORE UPDATE ON libro_oficial
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'libro_oficial: el PDF del libro es inmutable (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_libro_oficial_immutable_delete
    BEFORE DELETE ON libro_oficial
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'libro_oficial: el PDF del libro es inmutable (DELETE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_movimiento_caja_immutable_update
    BEFORE UPDATE ON movimiento_caja
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'movimiento_caja: la traza de caja es inmutable (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_movimiento_caja_immutable_delete
    BEFORE DELETE ON movimiento_caja
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'movimiento_caja: la traza de caja es inmutable (DELETE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_legalizacion_immutable_delete
    BEFORE DELETE ON legalizacion
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'legalizacion: la legalización no se borra (DELETE denegado)'
        );
    END
    """,
    # SPEC-019 FR-007: una legalización vigente bloquea nuevos asientos con
    # fecha dentro del ejercicio legalizado (refuerza el cierre de SPEC-004).
    """
    CREATE TRIGGER IF NOT EXISTS trg_journal_entry_legalizado_insert
    BEFORE INSERT ON journal_entry
    FOR EACH ROW
    WHEN EXISTS (
        SELECT 1 FROM legalizacion l
        WHERE l.empresa_id = NEW.empresa_id
          AND l.ejercicio = CAST(strftime('%Y', NEW.fecha) AS INTEGER)
          AND l.valido = 1
    )
    BEGIN
        SELECT RAISE(
            ABORT,
            'journal_entry: ejercicio legalizado. No admite nuevos asientos (FR-007)'
        );
    END
    """,
    # SPEC-021 (efectos): los estados `cobrado`/`impagado` son finales; un efecto
    # en estado final no se modifica ni se borra. La corrección de un impago se
    # gestiona con un REVERSAL nuevo (igual que el diario) y una re-emisión.
    """
    CREATE TRIGGER IF NOT EXISTS trg_efecto_final_immutable_update
    BEFORE UPDATE ON efecto
    FOR EACH ROW
    WHEN OLD.estado IN ('cobrado', 'impagado')
    BEGIN
        SELECT RAISE(
            ABORT,
            'efecto: un efecto cobrado/impagado es final (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_efecto_final_immutable_delete
    BEFORE DELETE ON efecto
    FOR EACH ROW
    WHEN OLD.estado IN ('cobrado', 'impagado')
    BEGIN
        SELECT RAISE(
            ABORT,
            'efecto: un efecto cobrado/impagado es final (DELETE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_calculo_is_contabilizado_immutable_update
    BEFORE UPDATE ON calculo_is
    FOR EACH ROW
    WHEN OLD.estado = 'contabilizado'
    BEGIN
        SELECT RAISE(
            ABORT,
            'calculo_is: un calculo contabilizado es final (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_calculo_is_contabilizado_immutable_delete
    BEFORE DELETE ON calculo_is
    FOR EACH ROW
    WHEN OLD.estado = 'contabilizado'
    BEGIN
        SELECT RAISE(
            ABORT,
            'calculo_is: un calculo contabilizado es final (DELETE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_ajuste_extracontable_contabilizado_insert
    BEFORE INSERT ON ajuste_extracontable
    FOR EACH ROW
    WHEN EXISTS (
        SELECT 1 FROM calculo_is
        WHERE id = NEW.calculo_is_id
          AND empresa_id = NEW.empresa_id
          AND estado = 'contabilizado'
    )
    BEGIN
        SELECT RAISE(
            ABORT,
            'ajuste_extracontable: el calculo padre esta contabilizado (INSERT denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_ajuste_extracontable_contabilizado_update
    BEFORE UPDATE ON ajuste_extracontable
    FOR EACH ROW
    WHEN EXISTS (
        SELECT 1 FROM calculo_is
        WHERE id = OLD.calculo_is_id
          AND empresa_id = OLD.empresa_id
          AND estado = 'contabilizado'
    )
    OR EXISTS (
        SELECT 1 FROM calculo_is
        WHERE id = NEW.calculo_is_id
          AND empresa_id = NEW.empresa_id
          AND estado = 'contabilizado'
    )
    BEGIN
        SELECT RAISE(
            ABORT,
            'ajuste_extracontable: el calculo padre esta contabilizado (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_ajuste_extracontable_contabilizado_delete
    BEFORE DELETE ON ajuste_extracontable
    FOR EACH ROW
    WHEN EXISTS (
        SELECT 1 FROM calculo_is
        WHERE id = OLD.calculo_is_id
          AND empresa_id = OLD.empresa_id
          AND estado = 'contabilizado'
    )
    BEGIN
        SELECT RAISE(
            ABORT,
            'ajuste_extracontable: el calculo padre esta contabilizado (DELETE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_modelo_200_append_only_update
    BEFORE UPDATE ON modelo_200
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'modelo_200: el modelo es append-only (UPDATE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_modelo_200_append_only_delete
    BEFORE DELETE ON modelo_200
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'modelo_200: el modelo es append-only (DELETE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_liquidacion_retenciones_final_update
    BEFORE UPDATE ON liquidacion_retenciones
    FOR EACH ROW
    WHEN OLD.estado = 'liquidado'
    BEGIN
        SELECT RAISE(
            ABORT,
            'liquidacion_retenciones: estado liquidado es final (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_liquidacion_retenciones_final_delete
    BEFORE DELETE ON liquidacion_retenciones
    FOR EACH ROW
    WHEN OLD.estado = 'liquidado'
    BEGIN
        SELECT RAISE(
            ABORT,
            'liquidacion_retenciones: estado liquidado es final (DELETE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_modelo_111_append_only_update
    BEFORE UPDATE ON modelo_111
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'modelo_111: el modelo es append-only (UPDATE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_modelo_111_append_only_delete
    BEFORE DELETE ON modelo_111
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'modelo_111: el modelo es append-only (DELETE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_modelo_115_append_only_update
    BEFORE UPDATE ON modelo_115
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'modelo_115: el modelo es append-only (UPDATE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_modelo_115_append_only_delete
    BEFORE DELETE ON modelo_115
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'modelo_115: el modelo es append-only (DELETE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_modelo_190_append_only_update
    BEFORE UPDATE ON modelo_190
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'modelo_190: el modelo es append-only (UPDATE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_modelo_190_append_only_delete
    BEFORE DELETE ON modelo_190
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'modelo_190: el modelo es append-only (DELETE denegado)');
    END
    """,
    # vigencia sin solapes por empresa (SPEC-025 FR-006/SC-004)
    """
    CREATE TRIGGER IF NOT EXISTS trg_catalogo_version_vigencia_insert
    BEFORE INSERT ON catalogo_version
    WHEN NEW.estado <> 'anulada' AND EXISTS (
        SELECT 1 FROM catalogo_version
        WHERE empresa_id = NEW.empresa_id
          AND estado <> 'anulada'
          AND fecha_inicio <= COALESCE(NEW.fecha_fin, '9999-12-31')
          AND COALESCE(fecha_fin, '9999-12-31') >= NEW.fecha_inicio
    )
    BEGIN
        SELECT RAISE(ABORT, 'catalogo_version: solape de vigencia por empresa');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_catalogo_version_vigencia_update
    BEFORE UPDATE ON catalogo_version
    WHEN NEW.estado <> 'anulada' AND EXISTS (
        SELECT 1 FROM catalogo_version
        WHERE empresa_id = NEW.empresa_id
          AND id <> OLD.id
          AND estado <> 'anulada'
          AND fecha_inicio <= COALESCE(NEW.fecha_fin, '9999-12-31')
          AND COALESCE(fecha_fin, '9999-12-31') >= NEW.fecha_inicio
    )
    BEGIN
        SELECT RAISE(ABORT, 'catalogo_version: solape de vigencia por empresa');
    END
    """,
    # snapshot de desviaciones append-only (SPEC-026 constitucion II)
    """
    CREATE TRIGGER IF NOT EXISTS trg_desviacion_append_only_update
    BEFORE UPDATE ON desviacion
    BEGIN
        SELECT RAISE(ABORT, 'desviacion: el snapshot del cierre es inmutable (UPDATE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_desviacion_append_only_delete
    BEFORE DELETE ON desviacion
    BEGIN
        SELECT RAISE(ABORT, 'desviacion: el snapshot del cierre es inmutable (DELETE denegado)');
    END
    """,
    # snapshot del EFE formulado append-only (SPEC-027 constitucion II)
    """
    CREATE TRIGGER IF NOT EXISTS trg_informe_efe_append_only_update
    BEFORE UPDATE ON informe_efe
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'informe_efe: el EFE formulado es inmutable (UPDATE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_informe_efe_append_only_delete
    BEFORE DELETE ON informe_efe
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'informe_efe: el EFE formulado es inmutable (DELETE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_linea_efe_append_only_update
    BEFORE UPDATE ON linea_efe
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'linea_efe: el EFE formulado es inmutable (UPDATE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_linea_efe_append_only_delete
    BEFORE DELETE ON linea_efe
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'linea_efe: el EFE formulado es inmutable (DELETE denegado)');
    END
    """,
    # snapshot de la balanza de comprobacion de un periodo cerrado (SPEC-028
    # constitucion II): el balance registrado es inmutable; una correccion es
    # un cierre nuevo, nunca la edicion del anterior.
    """
    CREATE TRIGGER IF NOT EXISTS trg_balanza_periodo_append_only_update
    BEFORE UPDATE ON balanza_periodo
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'balanza_periodo: el balance del periodo es inmutable (UPDATE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_balanza_periodo_append_only_delete
    BEFORE DELETE ON balanza_periodo
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'balanza_periodo: el balance del periodo es inmutable (DELETE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_balanza_periodo_linea_append_only_update
    BEFORE UPDATE ON balanza_periodo_linea
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'balanza_periodo_linea: el balance del periodo es inmutable (UPDATE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_balanza_periodo_linea_append_only_delete
    BEFORE DELETE ON balanza_periodo_linea
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'balanza_periodo_linea: el balance del periodo es inmutable (DELETE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_cierre_ejercicio_no_delete
    BEFORE DELETE ON cierre_ejercicio
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'cierre_ejercicio: el cierre anual es un registro auditable (DELETE denegado)');
    END
    """,
    # SPEC-028 FR-001 / research D9: espejo SQLite de chk_journal_entry_fecha_abierta.
    # Solo bloquean los estados `cerrado` y `cerrado_ajustado`: un periodo en
    # `reabierto_ajuste` admite el asiento de rectificacion.
    """
    CREATE TRIGGER IF NOT EXISTS chk_journal_entry_fecha_abierta
    BEFORE INSERT ON journal_entry
    FOR EACH ROW
    WHEN NEW.tipo NOT IN ('REGULARIZACION', 'CIERRE', 'OPENING', 'OPENING_REVERSAL')
      AND EXISTS (
        SELECT 1 FROM periodo_cerrado p
        WHERE p.empresa_id = NEW.empresa_id
          AND p.estado IN ('cerrado', 'cerrado_ajustado')
          AND p.fecha_ini <= NEW.fecha
          AND p.fecha_fin >= NEW.fecha
    )
    BEGIN
        SELECT RAISE(
            ABORT,
            'journal_entry: la fecha cae en un periodo cerrado (FR-001 periodo_cerrado)'
        );
    END
    """,
    # SPEC-029 (research D9, constitucion II): la exportacion es un snapshot
    # inmutable. Solo se admite la transicion `en_proceso -> lista|fallida` que
    # resuelve la propia generacion; una vez `lista` (o `fallida`) no admite
    # UPDATE ni DELETE. Espejo de `020_export.sql`.
    """
    CREATE TRIGGER IF NOT EXISTS chk_exportacion_immutable_update
    BEFORE UPDATE ON exportacion
    FOR EACH ROW
    WHEN OLD.estado IN ('lista', 'fallida')
      AND NOT (OLD.estado = 'en_proceso')
    BEGIN
        SELECT RAISE(
            ABORT,
            'exportacion: la exportacion es un snapshot inmutable (UPDATE denegado)'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS chk_exportacion_immutable_delete
    BEFORE DELETE ON exportacion
    FOR EACH ROW
    WHEN OLD.estado IN ('lista', 'fallida')
    BEGIN
        SELECT RAISE(
            ABORT,
            'exportacion: la exportacion es un snapshot inmutable (DELETE denegado)'
        );
    END
    """,
    # El manifiesto, sus lineas y el blob son append-only: forman la evidencia
    # de integridad y no admiten UPDATE ni DELETE en ningun estado.
    """
    CREATE TRIGGER IF NOT EXISTS trg_manifiesto_exportacion_append_only_update
    BEFORE UPDATE ON manifiesto_exportacion
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'manifiesto_exportacion: el manifiesto es inmutable (UPDATE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_manifiesto_exportacion_append_only_delete
    BEFORE DELETE ON manifiesto_exportacion
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'manifiesto_exportacion: el manifiesto es inmutable (DELETE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_manifiesto_bloque_append_only_update
    BEFORE UPDATE ON manifiesto_bloque
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'manifiesto_bloque: la linea de manifiesto es inmutable (UPDATE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_manifiesto_bloque_append_only_delete
    BEFORE DELETE ON manifiesto_bloque
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'manifiesto_bloque: la linea de manifiesto es inmutable (DELETE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_blob_exportacion_append_only_update
    BEFORE UPDATE ON blob_exportacion
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'blob_exportacion: el binario de la exportacion es inmutable (UPDATE denegado)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_blob_exportacion_append_only_delete
    BEFORE DELETE ON blob_exportacion
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'blob_exportacion: el binario de la exportacion es inmutable (DELETE denegado)');
    END
    """,
    # ============================================================
    #  SPEC-030: documento_asiento (constitucion II, research D3)
    # ============================================================
    # La evidencia (contenido, nombre, huella, anclaje, clasificacion e
    # importe informativo) no se reescribe NUNCA. Lo unico que puede cambiar es
    # la baja logica: `estado`, `baja_motivo`, `baja_usuario` y `baja_at`, que
    # el CHECK `chk_documento_asiento_baja` exige ademas completas. Espejo de
    # `021_adjuntos_asiento.sql`.
    """
    CREATE TRIGGER IF NOT EXISTS trg_documento_asiento_contenido_inmutable_update
    BEFORE UPDATE ON documento_asiento
    FOR EACH ROW
    WHEN OLD.empresa_id IS NOT NEW.empresa_id
        OR OLD.journal_entry_id IS NOT NEW.journal_entry_id
        OR OLD.contenido IS NOT NEW.contenido
        OR OLD.sha256 IS NOT NEW.sha256
        OR OLD.nombre_original IS NOT NEW.nombre_original
        OR OLD.content_type IS NOT NEW.content_type
        OR OLD.extension IS NOT NEW.extension
        OR OLD.size_bytes IS NOT NEW.size_bytes
        OR OLD.num_paginas IS NOT NEW.num_paginas
        OR OLD.tipo_documento IS NOT NEW.tipo_documento
        OR OLD.descripcion IS NOT NEW.descripcion
        OR OLD.importe_informativo IS NOT NEW.importe_informativo
        OR OLD.created_by IS NOT NEW.created_by
        OR OLD.created_at IS NOT NEW.created_at
    BEGIN
        SELECT RAISE(ABORT, 'documento_asiento inmutable: el contenido no se reescribe');
    END
    """,
    # FR-012: el borrado fisico no existe como operacion. El soporte contable se
    # conserva durante el plazo legal (art. 30 LGT); la baja es logica.
    """
    CREATE TRIGGER IF NOT EXISTS trg_documento_asiento_inmutable_delete
    BEFORE DELETE ON documento_asiento
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'documento_asiento inmutable: la baja es logica (DELETE denegado)');
    END
    """,
)



def instalar_triggers_sqlite(connection: Connection) -> None:
    """Install the SQLite immutability triggers; safe to run repeatedly."""
    for statement in _TRIGGERS_SQLITE:
        connection.exec_driver_sql(statement)