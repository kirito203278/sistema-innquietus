DO $$
DECLARE c record;
BEGIN
    FOR c IN SELECT conname FROM pg_constraint
             WHERE conrelid = 'paquetes_cliente'::regclass AND contype = 'c'
               AND pg_get_constraintdef(oid) LIKE '%prorroga_registrada_en + 15%'
    LOOP
        EXECUTE format('ALTER TABLE paquetes_cliente DROP CONSTRAINT %I', c.conname);
    END LOOP;
END $$;

ALTER TABLE paquetes_cliente ADD CONSTRAINT prorroga_max_5_dias CHECK (
    prorroga_hasta IS NULL OR
    (prorroga_hasta >= prorroga_registrada_en AND prorroga_hasta <= prorroga_registrada_en + 5)) NOT VALID;
