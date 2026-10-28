ALTER TABLE catalogo_paquetes
    ADD COLUMN costo NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (costo >= 0);

UPDATE catalogo_paquetes SET costo = v.costo
FROM (VALUES ('Básico', 1200), ('Estándar', 2500), ('Élite', 4500), ('Campaña', 1800)) AS v(nombre, costo)
WHERE catalogo_paquetes.nombre = v.nombre;

UPDATE catalogo_paquetes c SET costo = u.costo
FROM (
    SELECT DISTINCT ON (paquete_id) paquete_id, costo
    FROM paquetes_cliente
    ORDER BY paquete_id, fecha_inicio DESC, id DESC
) u
WHERE u.paquete_id = c.id;
