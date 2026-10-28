CREATE TABLE usuarios (
    id              SERIAL PRIMARY KEY,
    nombre          TEXT        NOT NULL,
    username        TEXT        NOT NULL UNIQUE,
    password_hash   TEXT        NOT NULL,
    rol             TEXT        NOT NULL CHECK (rol IN ('cm','admin')),
    solo_lectura    BOOLEAN     NOT NULL DEFAULT FALSE,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    primer_ingreso  BOOLEAN     NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (rol = 'admin' OR solo_lectura = FALSE)
);

CREATE TABLE catalogo_paquetes (
    id      SERIAL PRIMARY KEY,
    nombre  TEXT    NOT NULL UNIQUE,
    orden   INTEGER NOT NULL DEFAULT 0,
    activo  BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE catalogo_tipos (
    id      SERIAL PRIMARY KEY,
    nombre  TEXT    NOT NULL UNIQUE,
    orden   INTEGER NOT NULL DEFAULT 0,
    activo  BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE clientes (
    id               SERIAL PRIMARY KEY,
    cm_id            INTEGER REFERENCES usuarios(id),
    nombre           TEXT NOT NULL,
    correo_fb_enc    TEXT,
    password_fb_enc  TEXT,
    correo_contacto  TEXT,
    telefono         TEXT,
    observaciones    TEXT,
    estado           TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','no_renovado')),
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_clientes_cm_estado ON clientes (cm_id, estado);

CREATE TABLE paquetes_cliente (
    id                      SERIAL PRIMARY KEY,
    cliente_id              INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    paquete_id              INTEGER NOT NULL REFERENCES catalogo_paquetes(id),
    tipo_id                 INTEGER NOT NULL REFERENCES catalogo_tipos(id),
    costo                   NUMERIC(10,2) NOT NULL CHECK (costo >= 0),
    fecha_inicio            DATE NOT NULL,
    fecha_renovacion        DATE NOT NULL,
    estado                  TEXT NOT NULL DEFAULT 'activo'
                            CHECK (estado IN ('activo','vencido','renovado','archivado','eliminado')),
    renovacion_decision     TEXT NOT NULL DEFAULT 'pendiente' CHECK (renovacion_decision IN ('pendiente','si','no')),
    renovacion_pagada       BOOLEAN NOT NULL DEFAULT FALSE,
    prorroga_hasta          DATE,
    prorroga_registrada_en  DATE,
    ciclo_anterior_id       INTEGER REFERENCES paquetes_cliente(id),
    archivado_en            TIMESTAMPTZ,
    creado_en               TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (fecha_renovacion >= fecha_inicio),
    CHECK ((prorroga_hasta IS NULL) = (prorroga_registrada_en IS NULL)),
    CHECK (prorroga_hasta IS NULL OR
           (prorroga_hasta >= prorroga_registrada_en AND prorroga_hasta <= prorroga_registrada_en + 15))
);
CREATE INDEX ix_paq_cliente        ON paquetes_cliente (cliente_id, estado);
CREATE INDEX ix_paq_renovacion     ON paquetes_cliente (fecha_renovacion) WHERE estado IN ('activo','vencido');
CREATE INDEX ix_paq_prorroga       ON paquetes_cliente (prorroga_hasta)   WHERE prorroga_hasta IS NOT NULL;

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

CREATE VIEW v_paquete_saldo AS
SELECT p.id AS paquete_id,
       COALESCE(SUM(g.monto), 0)             AS pagado,
       p.costo - COALESCE(SUM(g.monto), 0)   AS restante
FROM paquetes_cliente p
LEFT JOIN pagos g ON g.paquete_id = p.id
GROUP BY p.id, p.costo;

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

CREATE TABLE archivo_no_renovados (
    id              SERIAL PRIMARY KEY,
    cliente_id      INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    cm_id           INTEGER REFERENCES usuarios(id),
    motivo          TEXT,
    archivado_en    TIMESTAMPTZ NOT NULL DEFAULT now(),
    reingresado_en  TIMESTAMPTZ
);
CREATE INDEX ix_archivo_abierto ON archivo_no_renovados (archivado_en) WHERE reingresado_en IS NULL;

CREATE TABLE recordatorios_cliente (
    id               SERIAL PRIMARY KEY,
    paquete_id       INTEGER NOT NULL REFERENCES paquetes_cliente(id) ON DELETE CASCADE,
    cliente_id       INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    cm_id            INTEGER REFERENCES usuarios(id),
    telefono_destino TEXT,
    texto            TEXT NOT NULL,
    generado_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
    enviado_en       TIMESTAMPTZ
);

CREATE TABLE notificaciones (
    id                  SERIAL PRIMARY KEY,
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
    tipo                TEXT NOT NULL CHECK (tipo IN
                        ('renovacion_3d','paquete_vencido','prorroga_3d','prorroga_vencida','sistema')),
    mensaje             TEXT NOT NULL,
    cliente_id          INTEGER REFERENCES clientes(id) ON DELETE CASCADE,
    paquete_id          INTEGER REFERENCES paquetes_cliente(id) ON DELETE CASCADE,
    requiere_respuesta  BOOLEAN NOT NULL DEFAULT FALSE,
    respuesta           TEXT CHECK (respuesta IN ('si','no')),
    respondida_en       TIMESTAMPTZ,
    leida               BOOLEAN NOT NULL DEFAULT FALSE,
    dedupe_key          TEXT UNIQUE,
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_notif_usuario ON notificaciones (usuario_id, leida, creado_en DESC);

CREATE TABLE bitacora (
    id          SERIAL PRIMARY KEY,
    usuario_id  INTEGER REFERENCES usuarios(id),
    accion      TEXT NOT NULL,
    detalle     JSONB,
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE jobs_ejecuciones (
    id            SERIAL PRIMARY KEY,
    nombre        TEXT NOT NULL,
    origen        TEXT NOT NULL CHECK (origen IN ('scheduler','endpoint','manual')),
    ejecutado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resultado     JSONB
);

CREATE FUNCTION trg_clientes_actualizado() RETURNS trigger AS $$
BEGIN
    NEW.actualizado_en = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER clientes_actualizado BEFORE UPDATE ON clientes
    FOR EACH ROW EXECUTE FUNCTION trg_clientes_actualizado();
