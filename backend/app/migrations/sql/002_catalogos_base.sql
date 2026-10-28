INSERT INTO catalogo_paquetes (nombre, orden) VALUES
    ('Básico', 1), ('Estándar', 2), ('Élite', 3), ('Campaña', 4)
ON CONFLICT (nombre) DO NOTHING;

INSERT INTO catalogo_tipos (nombre, orden) VALUES
    ('Normal', 1), ('Dinamita', 2), ('Fantasma', 3), ('Campaña', 4)
ON CONFLICT (nombre) DO NOTHING;
