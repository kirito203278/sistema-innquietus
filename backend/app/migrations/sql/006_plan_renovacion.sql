ALTER TABLE paquetes_cliente
    ADD COLUMN renovara_paquete_id INTEGER REFERENCES catalogo_paquetes(id),
    ADD COLUMN renovara_tipo_id    INTEGER REFERENCES catalogo_tipos(id),
    ADD COLUMN renovara_costo      NUMERIC(10,2) CHECK (renovara_costo IS NULL OR renovara_costo >= 0);
