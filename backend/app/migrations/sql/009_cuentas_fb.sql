-- Cuentas de Facebook COMPARTIDAS: un CM maneja varias campañas de varios clientes
-- con la misma cuenta y contraseña. Una cuenta pertenece a un CM y la usan N clientes.
-- La huella es un hash del correo (no reversible) y sirve para reconocer la misma cuenta.
CREATE TABLE cuentas_fb (
    id           SERIAL PRIMARY KEY,
    cm_id        INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    huella       TEXT NOT NULL,
    correo_enc   TEXT NOT NULL,
    password_enc TEXT,
    creado_en    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_cuentas_fb_cm_huella ON cuentas_fb (COALESCE(cm_id, 0), huella);

-- Los clientes antiguos conservan correo_fb_enc/password_fb_enc hasta que se editen
-- (la app los lee como respaldo); los nuevos apuntan a su cuenta.
ALTER TABLE clientes ADD COLUMN cuenta_id INTEGER REFERENCES cuentas_fb(id) ON DELETE SET NULL;
CREATE INDEX ix_clientes_cuenta ON clientes (cuenta_id);
