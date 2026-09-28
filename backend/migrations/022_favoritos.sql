-- SPEC-031: favoritos por usuario y empresa.
--
-- DECISIONES Y POR QUE (data-model.md seccion 1)
--
-- `destino` es la CLAVE del mapa de superficies, no una ruta. Es lo que hace que
-- FR-026 se cumpla: reubicar una opcion cambia su ruta y deja la clave intacta, de
-- modo que los favoritos de los usuarios siguen resolviendo sin migracion.
--
-- `UNIQUE (empresa_id, usuario_id, destino)`: un destino no se marca dos veces. Sin
-- este indice, dos marcas simultaneas desde dos pestanas crean duplicados y el panel
-- muestra el mismo destino dos veces. Es la misma razon por la que existe en
-- `journal_entry` el indice de numeracion.
--
-- `UNIQUE (empresa_id, id)`: convencion de las 30 specs previas, necesaria para las
-- FKs compuestas.
--
-- FK COMPUESTA A `user_companies`: es la garantia de constitution III que importa.
-- No basta con que el servicio filtre por empresa: con esta FK, un favorito de la
-- empresa B para un usuario no vinculado a ella es **invalido**, no invisible. El
-- dato no puede existir en un estado prohibido.
--
-- El orden es `(usuario_id, empresa_id)` porque es el del UNIQUE
-- `uq_user_companies_pair (user_id, company_id)`. La columna de empresa se llama
-- `empresa_id` aqui y `company_id` alla: son el mismo tenant con dos nombres, y por
-- eso la FK las empareja de forma cruzada.
--
-- SIN TRIGGER DE INMUTABILIDAD, a proposito: es la unica entidad de SPEC-031 que
-- admite `DELETE`, porque desmarcar un favorito es la baja de un marcado, no la
-- perdida de evidencia contable. No hay asiento, ni importe, ni referencia a el. La
-- trafica de la marca queda en `audit_log`, que si es append-only (constitution,
-- seccion de stack).
--
-- NO HAY LIMITE DE CINCO EN LA BASE. El limite opera en la LECTURA (CHK025): un
-- sexto favorito se guarda y la lectura recorta. Ponerlo aqui como `CHECK` seria
-- volver al error que la revision del checklist detecto: dejaria al usuario con 5
-- favoritos sin poder anadir el suyo.

CREATE TABLE IF NOT EXISTS favorito_usuario (
    id UUID NOT NULL,
    empresa_id BIGINT NOT NULL,
    usuario_id BIGINT NOT NULL,
    destino VARCHAR(64) NOT NULL,
    "orden" INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_favorito_usuario PRIMARY KEY (id),
    CONSTRAINT uq_favorito_usuario_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_favorito_usuario_destino UNIQUE (empresa_id, usuario_id, destino),
    CONSTRAINT ck_favorito_usuario_orden CHECK ("orden" >= 1),
    CONSTRAINT ck_favorito_usuario_destino_no_vacio CHECK (length(destino) > 0),
    CONSTRAINT fk_favorito_usuario_vinculo
        FOREIGN KEY (usuario_id, empresa_id)
        REFERENCES user_companies (user_id, company_id)
);

-- Lectura del conjunto ordenado del usuario en su empresa.
CREATE INDEX IF NOT EXISTS ix_favorito_usuario_orden
    ON favorito_usuario (empresa_id, usuario_id, "orden");

-- Validar un destino concreto sin cargar el conjunto entero.
CREATE INDEX IF NOT EXISTS ix_favorito_usuario_destino
    ON favorito_usuario (empresa_id, destino);
