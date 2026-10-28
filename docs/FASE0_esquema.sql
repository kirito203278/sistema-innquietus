-- ============================================================================
-- INNquietus · Control de clientes y paquetes — ESQUEMA PROPUESTO (Fase 0)
-- PostgreSQL. En Fase 1 se parte en migraciones numeradas (001_init.sql, ...).
-- Zona horaria de negocio: America/Mexico_City. Las FECHAS de negocio son DATE
-- (fecha local); los instantes son TIMESTAMPTZ.
--
-- DESVIACIÓN CLAVE respecto al modelo sugerido: cada fila de paquetes_cliente
-- es UN CICLO (no el paquete "para siempre"). Al renovar se crea una fila nueva
-- encadenada con ciclo_anterior_id. Así pagos, costo y fechas de cada ciclo
-- quedan intactos y los reportes de periodos cerrados siguen siendo exactos.
-- ============================================================================

-- ------------------------------------------------------------------ usuarios
CREATE TABLE usuarios (
    id              SERIAL PRIMARY KEY,
    nombre          TEXT        NOT NULL,
    username        TEXT        NOT NULL UNIQUE,            -- "nombre.apellido"
    password_hash   TEXT        NOT NULL,                   -- bcrypt
    rol             TEXT        NOT NULL CHECK (rol IN ('cm','admin')),
    solo_lectura    BOOLEAN     NOT NULL DEFAULT FALSE,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,      -- baja lógica
    primer_ingreso  BOOLEAN     NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (rol = 'admin' OR solo_lectura = FALSE)
);

-- ------------------------------------------------------------------ catálogos
CREATE TABLE catalogo_paquetes (          -- siembra: Básico, Estándar, Élite, Campaña
    id      SERIAL PRIMARY KEY,
    nombre  TEXT    NOT NULL UNIQUE,
    orden   INTEGER NOT NULL DEFAULT 0,   -- también define "subir/bajar de nivel"
    activo  BOOLEAN NOT NULL DEFAULT TRUE -- nunca se borra: se desactiva
);
CREATE TABLE catalogo_tipos (             -- siembra: Normal, Dinamita, Fantasma, Campaña
    id      SERIAL PRIMARY KEY,
    nombre  TEXT    NOT NULL UNIQUE,
    orden   INTEGER NOT NULL DEFAULT 0,
    activo  BOOLEAN NOT NULL DEFAULT TRUE
);

-- ------------------------------------------------------------------ clientes
CREATE TABLE clientes (
    id               SERIAL PRIMARY KEY,
    cm_id            INTEGER REFERENCES usuarios(id),       -- NULL = "Clientes por reasignar"
    nombre           TEXT NOT NULL,
    correo_fb_enc    TEXT,                                  -- AES-GCM (base64 nonce+ct)
    password_fb_enc  TEXT,                                  -- AES-GCM
    correo_contacto  TEXT,
    telefono         TEXT,                                  -- se normaliza a dígitos con lada para wa.me
    observaciones    TEXT,
    estado           TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','no_renovado')),
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_clientes_cm_estado ON clientes (cm_id, estado);

-- ------------------------------------------------------- paquetes (= ciclos)
CREATE TABLE paquetes_cliente (
    id                      SERIAL PRIMARY KEY,
    cliente_id              INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    paquete_id              INTEGER NOT NULL REFERENCES catalogo_paquetes(id),
    tipo_id                 INTEGER NOT NULL REFERENCES catalogo_tipos(id),
    costo                   NUMERIC(10,2) NOT NULL CHECK (costo >= 0),
    fecha_inicio            DATE NOT NULL,
    fecha_renovacion        DATE NOT NULL,                  -- fecha COMPLETA (el Excel solo tenía el día)
    estado                  TEXT NOT NULL DEFAULT 'activo'
                            CHECK (estado IN ('activo','vencido','renovado','archivado','eliminado')),
                            -- 'por vencer' NO se guarda: se calcula (activo y faltan <= 3 días)
                            -- 'renovado' = ciclo cerrado porque se abrió el siguiente
                            -- 'eliminado' = borrado lógico (conserva pagos para reportes históricos)
    renovacion_decision     TEXT NOT NULL DEFAULT 'pendiente' CHECK (renovacion_decision IN ('pendiente','si','no')),
    renovacion_pagada       BOOLEAN NOT NULL DEFAULT FALSE, -- se mantiene en servidor = (pagado >= costo); no la edita el cliente HTTP
    prorroga_hasta          DATE,
    prorroga_registrada_en  DATE,
    ciclo_anterior_id       INTEGER REFERENCES paquetes_cliente(id),
    archivado_en            TIMESTAMPTZ,
    creado_en               TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (fecha_renovacion >= fecha_inicio),
    CHECK ((prorroga_hasta IS NULL) = (prorroga_registrada_en IS NULL)),
    -- Defensa en profundidad de la regla "máx. 15 días naturales" (la validación principal es en la API)
    CHECK (prorroga_hasta IS NULL OR
           (prorroga_hasta >= prorroga_registrada_en AND prorroga_hasta <= prorroga_registrada_en + 15))
);
CREATE INDEX ix_paq_cliente        ON paquetes_cliente (cliente_id, estado);
CREATE INDEX ix_paq_renovacion     ON paquetes_cliente (fecha_renovacion) WHERE estado IN ('activo','vencido');
CREATE INDEX ix_paq_prorroga       ON paquetes_cliente (prorroga_hasta)   WHERE prorroga_hasta IS NOT NULL;

-- --------------------------------------------------------------------- pagos
CREATE TABLE pagos (
    id              SERIAL PRIMARY KEY,
    paquete_id      INTEGER NOT NULL REFERENCES paquetes_cliente(id) ON DELETE CASCADE,
    monto           NUMERIC(10,2) NOT NULL CHECK (monto > 0),
    fecha           DATE NOT NULL,
    nota            TEXT,
    registrado_por  INTEGER NOT NULL REFERENCES usuarios(id),
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_pagos_paquete ON pagos (paquete_id);
CREATE INDEX ix_pagos_fecha   ON pagos (fecha);

-- "pagado" nunca es un campo suelto: se deriva de pagos
CREATE VIEW v_paquete_saldo AS
SELECT p.id AS paquete_id,
       COALESCE(SUM(g.monto), 0)             AS pagado,
       p.costo - COALESCE(SUM(g.monto), 0)   AS restante
FROM paquetes_cliente p
LEFT JOIN pagos g ON g.paquete_id = p.id
GROUP BY p.id, p.costo;

-- -------------------------------------------------- historial de renovaciones
CREATE TABLE renovaciones (
    id                    SERIAL PRIMARY KEY,
    ciclo_anterior_id     INTEGER NOT NULL REFERENCES paquetes_cliente(id) ON DELETE CASCADE,
    ciclo_nuevo_id        INTEGER NOT NULL REFERENCES paquetes_cliente(id) ON DELETE CASCADE,
    paquete_anterior_id   INTEGER NOT NULL REFERENCES catalogo_paquetes(id),
    paquete_nuevo_id      INTEGER NOT NULL REFERENCES catalogo_paquetes(id),
    costo_anterior        NUMERIC(10,2) NOT NULL,
    costo_nuevo           NUMERIC(10,2) NOT NULL,
    fecha                 DATE NOT NULL,
    registrado_por        INTEGER REFERENCES usuarios(id),
    creado_en             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------ No renovados
-- Una fila por entrada del cliente a "No renovados" (cuando se queda sin paquetes activos).
CREATE TABLE archivo_no_renovados (
    id              SERIAL PRIMARY KEY,
    cliente_id      INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,  -- (el proyecto anterior no tenía CASCADE y causó un IntegrityError en la purga)
    cm_id           INTEGER REFERENCES usuarios(id),
    motivo          TEXT,
    archivado_en    TIMESTAMPTZ NOT NULL DEFAULT now(),   -- reloj de las reglas de 2 meses (reingreso) y 3 meses (purga)
    reingresado_en  TIMESTAMPTZ                           -- NULL = sigue en "No renovados"
);
CREATE INDEX ix_archivo_abierto ON archivo_no_renovados (archivado_en) WHERE reingresado_en IS NULL;

-- ------------------------------------------------- recordatorios al cliente
CREATE TABLE recordatorios_cliente (
    id               SERIAL PRIMARY KEY,
    paquete_id       INTEGER NOT NULL REFERENCES paquetes_cliente(id) ON DELETE CASCADE,
    cliente_id       INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    cm_id            INTEGER REFERENCES usuarios(id),
    telefono_destino TEXT,
    texto            TEXT NOT NULL,                       -- mensaje ya redactado
    generado_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
    enviado_en       TIMESTAMPTZ                          -- lo marca el CM
);

-- ----------------------------------------------------------- notificaciones
CREATE TABLE notificaciones (
    id                  SERIAL PRIMARY KEY,
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
    tipo                TEXT NOT NULL CHECK (tipo IN
                        ('renovacion_3d','paquete_vencido','prorroga_3d','prorroga_vencida','sistema')),
    mensaje             TEXT NOT NULL,
    cliente_id          INTEGER REFERENCES clientes(id) ON DELETE CASCADE,
    paquete_id          INTEGER REFERENCES paquetes_cliente(id) ON DELETE CASCADE,
    requiere_respuesta  BOOLEAN NOT NULL DEFAULT FALSE,   -- "¿El cliente pagó?"
    respuesta           TEXT CHECK (respuesta IN ('si','no')),
    respondida_en       TIMESTAMPTZ,
    leida               BOOLEAN NOT NULL DEFAULT FALSE,
    dedupe_key          TEXT UNIQUE,                      -- p.ej. 'renov3d:123:2026-10-10'; evita duplicados si corren scheduler Y cron externo
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_notif_usuario ON notificaciones (usuario_id, leida, creado_en DESC);

-- -------------------------------------------------------------- auditoría
CREATE TABLE bitacora (
    id          SERIAL PRIMARY KEY,
    usuario_id  INTEGER REFERENCES usuarios(id),
    accion      TEXT NOT NULL,     -- 'alta_usuario','reset_password','baja_cm','reasignar_cliente','borrar_paquete','editar_catalogo',...
    detalle     JSONB,
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------- ejecuciones de jobs (nuevo)
-- Útil para depurar cron-job.org y para que los jobs sean idempotentes y auditables.
CREATE TABLE jobs_ejecuciones (
    id            SERIAL PRIMARY KEY,
    nombre        TEXT NOT NULL,
    origen        TEXT NOT NULL CHECK (origen IN ('scheduler','endpoint','manual')),
    ejecutado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resultado     JSONB
);

-- ------------------------------------------------------------ semillas
-- catalogo_paquetes: Básico(1), Estándar(2), Élite(3), Campaña(4)
-- catalogo_tipos:    Normal(1), Dinamita(2), Fantasma(3), Campaña(4)
-- Usuarios y clientes de ejemplo (nombres ficticios): Fase 1, script de seed aparte.
-- No hay importador de Excel: todo arranca desde cero; el seed de Fase 1 usa datos falsos.
