-- ============================================================================
-- Módulo de CAMPAÑAS dentro de la plataforma unificada.
--
-- Principio: una sola fuente de verdad por entidad.
--   * usuarios, clientes, notificaciones y bitácora YA existen y se comparten;
--     aquí NO se duplican, solo se extienden.
--   * Las credenciales de la cuenta publicitaria son las mismas de Facebook que
--     el cliente ya tiene (clientes.correo_fb_enc / password_fb_enc, AES-GCM):
--     no existe una segunda tabla de cuentas.
--   * La campaña cuelga del cliente y, opcionalmente, del ciclo/paquete que la
--     respalda (paquetes_cliente), conectando venta -> campaña.
-- ============================================================================

-- ---- datos de pago/cuenta que antes vivían solo en el sistema de campañas ----
ALTER TABLE clientes
    ADD COLUMN tipo_cuenta TEXT,
    ADD COLUMN metodo_pago TEXT,
    ADD COLUMN forma_pago  TEXT;

-- ------------------------------------------------------------------ campañas
CREATE TABLE campanas (
    id                  SERIAL PRIMARY KEY,
    cliente_id          INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    paquete_cliente_id  INTEGER REFERENCES paquetes_cliente(id) ON DELETE SET NULL,
    nombre              TEXT NOT NULL,
    tipo                TEXT NOT NULL CHECK (tipo IN ('local','nacional','otro')),
    presupuesto         NUMERIC(12,2) NOT NULL CHECK (presupuesto > 0),
    presupuesto_esquema TEXT NOT NULL DEFAULT 'mensual'
                        CHECK (presupuesto_esquema IN ('mensual','semanal','diario')),
    formato_post        BOOLEAN NOT NULL DEFAULT FALSE,
    formato_3d          BOOLEAN NOT NULL DEFAULT FALSE,
    formato_boton       BOOLEAN NOT NULL DEFAULT FALSE,
    formato_otro        BOOLEAN NOT NULL DEFAULT FALSE,
    lugar               TEXT,
    fecha_inicio        DATE NOT NULL,
    fecha_renovacion    DATE NOT NULL,
    estado              TEXT NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa','vencida','cerrada')),
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (fecha_renovacion >= fecha_inicio)
);
CREATE INDEX ix_campanas_cliente ON campanas (cliente_id, estado);
CREATE INDEX ix_campanas_renovacion ON campanas (fecha_renovacion) WHERE estado = 'activa';

-- ---------------------------------------------------------- datos semanales
-- Semana operativa sábado -> viernes. La captura se bloquea al terminar la semana.
CREATE TABLE semanas (
    id                       SERIAL PRIMARY KEY,
    campana_id               INTEGER NOT NULL REFERENCES campanas(id) ON DELETE CASCADE,
    inicio                   DATE NOT NULL,
    fin                      DATE NOT NULL,
    mensajes                 INTEGER CHECK (mensajes >= 0),
    costo_por_resultado      NUMERIC(10,2) CHECK (costo_por_resultado >= 0),
    importe_gastado          NUMERIC(10,2) CHECK (importe_gastado >= 0),
    editable                 BOOLEAN NOT NULL DEFAULT TRUE,
    edicion_habilitada_hasta TIMESTAMPTZ,
    capturado_por            INTEGER REFERENCES usuarios(id),
    actualizado_en           TIMESTAMPTZ,
    UNIQUE (campana_id, inicio),
    CHECK (fin = inicio + 6)
);

CREATE TABLE observaciones (
    id          SERIAL PRIMARY KEY,
    campana_id  INTEGER NOT NULL REFERENCES campanas(id) ON DELETE CASCADE,
    texto       TEXT NOT NULL,
    autor_id    INTEGER REFERENCES usuarios(id),
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------ resúmenes mensuales
CREATE TABLE mensuales (
    id                 SERIAL PRIMARY KEY,
    campana_id         INTEGER NOT NULL REFERENCES campanas(id) ON DELETE CASCADE,
    periodo_inicio     DATE NOT NULL,
    periodo_fin        DATE NOT NULL,
    mensajes_total     INTEGER NOT NULL,
    gasto_total        NUMERIC(12,2) NOT NULL,
    costo_por_mensaje  NUMERIC(10,2) NOT NULL,
    presupuesto        NUMERIC(12,2) NOT NULL,
    sobrante           NUMERIC(12,2),
    rendimiento        TEXT CHECK (rendimiento IN ('bueno','regular','bajo')),
    origen             TEXT NOT NULL DEFAULT 'calculado' CHECK (origen IN ('manual','calculado')),
    creado_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (campana_id, periodo_inicio)
);

-- Los mensuales son INMUTABLES: nadie puede editar el histórico. (El borrado solo
-- ocurre en cascada al eliminar el cliente completo; no hay trigger de delete.)
CREATE FUNCTION fn_mensuales_inmutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'La tabla mensuales es inmutable: no se permite % sobre registros existentes', TG_OP;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_mensuales_no_update BEFORE UPDATE ON mensuales
    FOR EACH ROW EXECUTE FUNCTION fn_mensuales_inmutable();

-- La captura manual de un mensual solo se permite si la campaña no tiene ninguno.
CREATE FUNCTION fn_mensuales_manual_solo_primero() RETURNS trigger AS $$
BEGIN
    IF NEW.origen = 'manual' AND EXISTS (SELECT 1 FROM mensuales WHERE campana_id = NEW.campana_id) THEN
        RAISE EXCEPTION 'Ya existe un mensual para esta campaña: la captura manual solo se permite si no hay ninguno previo';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_mensuales_manual_solo_primero BEFORE INSERT ON mensuales
    FOR EACH ROW EXECUTE FUNCTION fn_mensuales_manual_solo_primero();

-- ------------------------------------------------- umbrales del semáforo
-- Editables sin tocar código. Valores DEFINITIVOS de la agencia (costo por mensaje).
CREATE TABLE metricas_config (
    id                         SERIAL PRIMARY KEY,
    tipo                       TEXT NOT NULL CHECK (tipo IN ('local','nacional','otro')),
    paquete                    TEXT,
    umbral_bueno               NUMERIC(10,2) NOT NULL,
    umbral_regular             NUMERIC(10,2) NOT NULL,
    caida_mensajes_alerta_pct  NUMERIC(5,2) NOT NULL DEFAULT 30.00,
    activo                     BOOLEAN NOT NULL DEFAULT TRUE,
    actualizado_en             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tipo, paquete),
    CHECK (umbral_regular >= umbral_bueno)
);
INSERT INTO metricas_config (tipo, paquete, umbral_bueno, umbral_regular, caida_mensajes_alerta_pct) VALUES
    ('local',    NULL, 19.00, 29.00, 30.00),
    ('nacional', NULL, 14.00, 19.00, 30.00),
    ('otro',     NULL, 19.00, 29.00, 30.00);
-- UNIQUE (tipo, paquete) no distingue NULL: este índice garantiza una sola fila general por tipo.
CREATE UNIQUE INDEX ux_metricas_general ON metricas_config (tipo) WHERE paquete IS NULL;

-- ---------------------------------------------------------------- vistas
CREATE VIEW v_rendimiento_semanal AS
SELECT s.campana_id, s.inicio, s.fin, s.mensajes, s.costo_por_resultado,
       ROW_NUMBER() OVER (PARTITION BY s.campana_id ORDER BY s.inicio) AS num_semana,
       AVG(s.costo_por_resultado) OVER (PARTITION BY s.campana_id ORDER BY s.inicio ROWS UNBOUNDED PRECEDING) AS costo_promedio_acum,
       SUM(s.mensajes) OVER (PARTITION BY s.campana_id ORDER BY s.inicio ROWS UNBOUNDED PRECEDING) AS mensajes_acum
FROM semanas s
WHERE s.mensajes IS NOT NULL;

CREATE VIEW v_mensuales_recientes AS
SELECT m.*, c.cliente_id, cl.cm_id
FROM mensuales m
JOIN campanas c  ON c.id = m.campana_id
JOIN clientes cl ON cl.id = c.cliente_id;

-- ---- notificaciones: nuevos tipos del módulo de campañas (mismo buzón) ----
DO $$
DECLARE c record;
BEGIN
    FOR c IN SELECT conname FROM pg_constraint
             WHERE conrelid = 'notificaciones'::regclass AND contype = 'c'
               AND pg_get_constraintdef(oid) LIKE '%renovacion_3d%'
    LOOP
        EXECUTE format('ALTER TABLE notificaciones DROP CONSTRAINT %I', c.conname);
    END LOOP;
END $$;

ALTER TABLE notificaciones ADD CONSTRAINT notificaciones_tipo_check CHECK (tipo IN (
    'renovacion_3d','paquete_vencido','prorroga_3d','prorroga_vencida','sistema',
    'recordatorio_captura','campana_vencida'));
