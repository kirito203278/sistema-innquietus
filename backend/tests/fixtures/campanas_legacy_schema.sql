-- ============================================================================
-- SISTEMA DE GESTIÓN DE CAMPAÑAS · INNquietus
-- Esquema de base de datos (PostgreSQL)
-- ============================================================================
-- Reglas de negocio que este esquema materializa:
--   * Cada CM solo ve sus clientes (aislamiento por cm_id en toda consulta).
--   * Un cliente puede tener varias campañas (dropdown por cliente).
--   * Semana operativa: sábado a viernes. La captura cierra al terminar la
--     semana; el registro queda bloqueado (editable = false).
--   * Al llegar la fecha de renovación (12:00 pm) se calcula el resumen
--     mensual, se archiva, y se borran semanales + observaciones de ESA
--     campaña únicamente.
--   * Máximo 2 meses de comparación en panel CM; 3 meses en panel admin.
--   * Mensuales inmutables; solo el primer mes se captura manualmente.
--   * Credenciales de acceso a la app: hash bcrypt. Credenciales de la
--     cuenta publicitaria del cliente: cifradas (AES-GCM), nunca en claro.
-- ============================================================================

-- ---------------------------------------------------------------- usuarios
CREATE TABLE usuarios (
    id              SERIAL PRIMARY KEY,
    nombre          TEXT NOT NULL,
    username        TEXT NOT NULL UNIQUE,          -- derivado del nombre: "luz.hernandez"
    password_hash   TEXT NOT NULL,                 -- bcrypt; el CM no puede cambiarla
    rol             TEXT NOT NULL CHECK (rol IN ('cm','admin')),
    solo_lectura    BOOLEAN NOT NULL DEFAULT FALSE, -- admins limitados: ven, no editan
    activo          BOOLEAN NOT NULL DEFAULT TRUE,  -- baja lógica al eliminar CM
    primer_ingreso  BOOLEAN NOT NULL DEFAULT TRUE,  -- controla la pantalla "Comenzar"
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Una misma persona con dos roles (p.ej. Luz) = dos filas con usernames
-- distintos ("luz.cm" y "luz.admin"). La unicidad de username lo garantiza.

-- ------------------------------------------------- cuentas publicitarias
-- La credencial NO pertenece al cliente: es una entidad propia. Un dueño con
-- dos negocios = dos clientes vinculados a la MISMA cuenta. El duplicado por
-- error de captura es imposible: si las credenciales ya existen, el sistema
-- no crea otra cuenta; ofrece vincular el cliente a la existente.
CREATE TABLE cuentas_publicitarias (
    id              SERIAL PRIMARY KEY,
    usuario_enc     TEXT NOT NULL,     -- cifrado AES-GCM
    password_enc    TEXT NOT NULL,     -- cifrado AES-GCM
    huella          TEXT NOT NULL UNIQUE,  -- hash(usuario+password): unicidad
                                           -- sin necesidad de descifrar
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- clientes
CREATE TABLE clientes (
    id              SERIAL PRIMARY KEY,
    cm_id           INTEGER NOT NULL REFERENCES usuarios(id),
    cuenta_id       INTEGER REFERENCES cuentas_publicitarias(id),
    nombre          TEXT NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'activo'
                    CHECK (estado IN ('activo','no_renovado')),
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cm_id, nombre)   -- un CM no puede tener dos clientes con igual nombre
);
-- Flujo de captura: el CM escribe usuario y contraseña; el backend calcula la
-- huella. Si no existe -> crea la cuenta y vincula. Si existe -> pregunta
-- "esta cuenta ya está registrada (cliente X); ¿vincular también a este
-- cliente?". Aceptar = vínculo legítimo; cancelar = corregir error de dedo.
-- Al borrar una cuenta publicitaria huérfana (sin clientes vinculados), un
-- job de limpieza la elimina.

-- ---------------------------------------------------------------- campañas
CREATE TABLE campanas (
    id              SERIAL PRIMARY KEY,
    cliente_id      INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    nombre          TEXT NOT NULL,                 -- "LOCAL ADV - JUN 23"
    paquete         TEXT,                          -- Básico / Estándar / Campaña / VIP
    tipo            TEXT NOT NULL CHECK (tipo IN ('local','nacional','otro')),
    presupuesto     NUMERIC(12,2) NOT NULL,        -- monto del ciclo
    presupuesto_esquema TEXT NOT NULL DEFAULT 'mensual'
                    CHECK (presupuesto_esquema IN ('mensual','semanal','diario')),
    formato_post    BOOLEAN NOT NULL DEFAULT FALSE, -- checkboxes del Excel
    formato_3d      BOOLEAN NOT NULL DEFAULT FALSE,
    formato_boton   BOOLEAN NOT NULL DEFAULT FALSE,
    formato_otro    BOOLEAN NOT NULL DEFAULT FALSE,
    lugar           TEXT,                          -- "Mazatlán, Culiacán"
    fecha_inicio    DATE NOT NULL,
    fecha_renovacion DATE NOT NULL,                -- dispara el cierre a las 12 pm
    estado          TEXT NOT NULL DEFAULT 'activa'
                    CHECK (estado IN ('activa','vencida','cerrada')),
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 'vencida' = llegó la fecha de renovación y el CM aún no confirma;
-- en ese estado la interfaz bloquea todo sobre esta campaña.

-- ---------------------------------------------------------- datos semanales
CREATE TABLE semanas (
    id              SERIAL PRIMARY KEY,
    campana_id      INTEGER NOT NULL REFERENCES campanas(id) ON DELETE CASCADE,
    inicio          DATE NOT NULL,                 -- siempre sábado
    fin             DATE NOT NULL,                 -- siempre viernes
    mensajes        INTEGER,
    costo_por_resultado NUMERIC(10,2),
    editable        BOOLEAN NOT NULL DEFAULT TRUE, -- false al terminar la semana
    capturado_por   INTEGER REFERENCES usuarios(id),
    actualizado_en  TIMESTAMPTZ,
    UNIQUE (campana_id, inicio)
);
-- Editable las veces que quiera el CM DENTRO de la semana; el job nocturno
-- del sábado 00:00 pone editable=false a la semana que terminó.

-- --------------------------------------------------------- observaciones
CREATE TABLE observaciones (
    id              SERIAL PRIMARY KEY,
    campana_id      INTEGER NOT NULL REFERENCES campanas(id) ON DELETE CASCADE,
    texto           TEXT NOT NULL,
    autor_id        INTEGER REFERENCES usuarios(id),
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Se borran junto con las semanas al cerrar el ciclo de SU campaña.

-- ------------------------------------------------------ resúmenes mensuales
CREATE TABLE mensuales (
    id              SERIAL PRIMARY KEY,
    campana_id      INTEGER NOT NULL REFERENCES campanas(id) ON DELETE CASCADE,
    periodo_inicio  DATE NOT NULL,
    periodo_fin     DATE NOT NULL,
    mensajes_total  INTEGER NOT NULL,
    gasto_total     NUMERIC(12,2) NOT NULL,
    costo_por_mensaje NUMERIC(10,2) NOT NULL,
    presupuesto     NUMERIC(12,2) NOT NULL,        -- el vigente en ese ciclo
    sobrante        NUMERIC(12,2),                 -- presupuesto - gasto
    rendimiento     TEXT CHECK (rendimiento IN ('bueno','regular','bajo')),
    origen          TEXT NOT NULL DEFAULT 'calculado'
                    CHECK (origen IN ('manual','calculado')),
    -- 'manual' solo se permite si la campaña no tiene ningún mensual previo
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (campana_id, periodo_inicio)
);
-- INMUTABLE: sin UPDATE ni DELETE desde la aplicación (se refuerza con
-- permisos de rol de la base y con un trigger de rechazo).

-- --------------------------------------------------------- no renovados
CREATE TABLE archivo_no_renovados (
    id              SERIAL PRIMARY KEY,
    cliente_id      INTEGER NOT NULL REFERENCES clientes(id),
    cm_id           INTEGER NOT NULL REFERENCES usuarios(id),
    motivo          TEXT,
    archivado_en    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- El cliente que "no renovó pero se conserva" cambia estado='no_renovado'
-- y aparece en este apartado. Sus mensuales se conservan siempre.

-- ------------------------------------------------------------- notificaciones
CREATE TABLE notificaciones (
    id              SERIAL PRIMARY KEY,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    tipo            TEXT NOT NULL CHECK (tipo IN
                    ('recordatorio_captura','vencimiento','sistema')),
    mensaje         TEXT NOT NULL,
    leida           BOOLEAN NOT NULL DEFAULT FALSE,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------- auditoría
CREATE TABLE bitacora (
    id              SERIAL PRIMARY KEY,
    usuario_id      INTEGER REFERENCES usuarios(id),
    accion          TEXT NOT NULL,     -- 'borrar_cliente', 'migrar_cm', 'reset_password'...
    detalle         JSONB,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Las acciones destructivas (borrado permanente, migración de CM, cambios de
-- contraseña) siempre dejan rastro aquí.

-- ============================================================================
-- Vistas de apoyo
-- ============================================================================

-- Rendimiento semanal acumulado de una campaña (semana 1 a la actual)
CREATE VIEW v_rendimiento_semanal AS
SELECT
    s.campana_id,
    s.inicio, s.fin, s.mensajes, s.costo_por_resultado,
    ROW_NUMBER() OVER (PARTITION BY s.campana_id ORDER BY s.inicio) AS num_semana,
    AVG(s.costo_por_resultado) OVER (PARTITION BY s.campana_id
        ORDER BY s.inicio ROWS UNBOUNDED PRECEDING) AS costo_promedio_acum,
    SUM(s.mensajes) OVER (PARTITION BY s.campana_id
        ORDER BY s.inicio ROWS UNBOUNDED PRECEDING) AS mensajes_acum
FROM semanas s
WHERE s.mensajes IS NOT NULL;

-- Comparativo mensual (panel CM: 2 meses / panel admin: 3 meses; se limita
-- en la consulta con LIMIT)
CREATE VIEW v_mensuales_recientes AS
SELECT m.*, c.cliente_id, cl.cm_id
FROM mensuales m
JOIN campanas c  ON c.id = m.campana_id
JOIN clientes cl ON cl.id = c.cliente_id
ORDER BY m.periodo_inicio DESC;

-- ============================================================================
-- Trabajos programados (se implementan en el backend, no en SQL):
--   * SÁBADO 00:00  -> bloquear la semana que terminó (editable=false) y
--                      crear la fila de la semana nueva por campaña activa.
--   * VIERNES 14:00 -> notificación a cada CM con semanas sin capturar
--                      (la fecha límite es viernes 15:00).
--   * DIARIO 12:00  -> campañas con fecha_renovacion = hoy:
--                      1) calcular y archivar el mensual,
--                      2) borrar semanales y observaciones de esa campaña,
--                      3) estado='vencida' y bloquear la campaña en la UI
--                         hasta que el CM confirme renovación o baja.
-- ============================================================================
-- ============================================================================
-- Métricas de rendimiento PARAMETRIZADAS (especificación, sección 7)
-- Los umbrales de la sección 7 son provisionales; esta tabla permite
-- sustituirlos sin tocar código. Se puede tener una fila por tipo, o una fila
-- por (tipo, paquete) si algún día los umbrales varían por paquete.
-- ============================================================================
CREATE TABLE metricas_config (
    id                      SERIAL PRIMARY KEY,
    tipo                    TEXT NOT NULL CHECK (tipo IN ('local','nacional','otro')),
    paquete                 TEXT,           -- NULL = aplica a todos los paquetes de ese tipo
    umbral_bueno            NUMERIC(10,2) NOT NULL,   -- costo_por_resultado <= este valor => 'bueno'
    umbral_regular          NUMERIC(10,2) NOT NULL,   -- <= este valor => 'regular'; por encima => 'bajo'
    caida_mensajes_alerta_pct NUMERIC(5,2) NOT NULL DEFAULT 30.00,
    activo                  BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en               TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tipo, paquete)
);

-- Umbrales provisionales de la sección 7. 'otro' no está definido en la
-- especificación; se deja igual a 'local' como valor por defecto razonable
-- hasta que se defina la métrica real.
INSERT INTO metricas_config (tipo, paquete, umbral_bueno, umbral_regular, caida_mensajes_alerta_pct)
VALUES
    ('local',    NULL, 20.00, 30.00, 30.00),
    ('nacional', NULL, 15.00, 25.00, 30.00),
    ('otro',     NULL, 20.00, 30.00, 30.00)
ON CONFLICT (tipo, paquete) DO NOTHING;

-- ============================================================================
-- Refuerzo de reglas duras a nivel de base de datos
-- ============================================================================

-- Regla 3 (sección 11): mensuales inmutables. Sin UPDATE ni DELETE desde la
-- aplicación una vez creados.
CREATE OR REPLACE FUNCTION fn_mensuales_inmutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'La tabla mensuales es inmutable: no se permite % sobre registros existentes', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_mensuales_no_update
    BEFORE UPDATE ON mensuales
    FOR EACH ROW EXECUTE FUNCTION fn_mensuales_inmutable();

CREATE TRIGGER trg_mensuales_no_delete
    BEFORE DELETE ON mensuales
    FOR EACH ROW EXECUTE FUNCTION fn_mensuales_inmutable();

-- Regla 3: captura manual de mensual solo si la campaña no tiene ninguno.
CREATE OR REPLACE FUNCTION fn_mensuales_manual_solo_primero() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.origen = 'manual' AND EXISTS (
        SELECT 1 FROM mensuales WHERE campana_id = NEW.campana_id
    ) THEN
        RAISE EXCEPTION 'Ya existe un mensual para esta campaña: la captura manual solo se permite si no hay ninguno previo';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_mensuales_manual_solo_primero
    BEFORE INSERT ON mensuales
    FOR EACH ROW EXECUTE FUNCTION fn_mensuales_manual_solo_primero();
-- ============================================================================
-- Se agrega el importe gastado por semana como dato capturado independiente
-- del costo por resultado (igual que en la plataforma publicitaria, "costo
-- por resultado" e "importe gastado" son dos métricas separadas, no una
-- calculada de la otra).
-- ============================================================================
ALTER TABLE semanas ADD COLUMN importe_gastado NUMERIC(10,2);
-- ============================================================================
-- Ajuste: la sección 9-c de la especificación exige que, cuando un cliente
-- "no renueva y se borra", el borrado sea en cascada hasta mensuales
-- ("clientes → campañas → semanas → mensuales"). El trigger original
-- bloqueaba TODO delete sobre mensuales, incluido el disparado por esa
-- cascada legítima. La garantía real de inmutabilidad es que nadie pueda
-- EDITAR el histórico (trg_mensuales_no_update, que se conserva); el
-- borrado solo ocurre como consecuencia de borrar el cliente completo, y no
-- existe ningún endpoint que borre un mensual suelto.
-- ============================================================================
DROP TRIGGER IF EXISTS trg_mensuales_no_delete ON mensuales;
-- ============================================================================
-- Umbrales DEFINITIVOS de rendimiento (sustituyen a los provisionales de la
-- migración 002), confirmados por la agencia. El rendimiento se mide por
-- costo por mensaje: entre más bajo, mejor.
--
--   Local:    bueno 0-19   | regular 20-29  | bajo 30 o más
--   Nacional: bueno 0-14   | regular 15-19  | bajo 20 o más
--   Otro:     igual que Local (no se usa en la práctica; se deja el mismo
--             valor por defecto razonable hasta que se defina uno propio).
--
-- Solo datos, sin cambios de lógica: si esta migración ya se aplicó a mano
-- vía UPDATE directo, este UPDATE es idempotente (deja los mismos valores).
-- ============================================================================
UPDATE metricas_config SET umbral_bueno = 19.00, umbral_regular = 29.00, actualizado_en = now()
    WHERE tipo = 'local' AND paquete IS NULL;

UPDATE metricas_config SET umbral_bueno = 14.00, umbral_regular = 19.00, actualizado_en = now()
    WHERE tipo = 'nacional' AND paquete IS NULL;

UPDATE metricas_config SET umbral_bueno = 19.00, umbral_regular = 29.00, actualizado_en = now()
    WHERE tipo = 'otro' AND paquete IS NULL;
-- ============================================================================
-- Datos de pago del cliente, capturados junto con la cuenta al dar de alta
-- (viven en el cliente, no en la cuenta publicitaria compartida: el tipo de
-- cuenta y la forma de pago son propios de la relación con ESE cliente,
-- incluso si dos clientes comparten el mismo login de la cuenta publicitaria).
-- ============================================================================
ALTER TABLE clientes ADD COLUMN tipo_cuenta TEXT;
ALTER TABLE clientes ADD COLUMN metodo_pago TEXT;
ALTER TABLE clientes ADD COLUMN forma_pago TEXT;
-- ============================================================================
-- Permiso temporal de edición: el admin puede habilitarle al CM la edición
-- de una semana ya cerrada por 2 horas (columna NULL = sin permiso activo).
-- ============================================================================
ALTER TABLE semanas ADD COLUMN edicion_habilitada_hasta TIMESTAMPTZ;
