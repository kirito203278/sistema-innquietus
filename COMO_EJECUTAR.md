# Cómo ejecutar

La forma más rápida de probarlo es el modo demo del [README](README.md) (un solo comando). Esto es para desarrollo.

## Todo en uno con Docker (recomendado para probar)
Requisitos: Docker + Docker Compose.

```bash
python3 scripts/generar_env.py            # una vez: crea .env con claves NUEVAS (nunca reutilices las de otro proyecto)
docker compose up -d --build              # Postgres + app (API e interfaz) + Adminer
docker compose exec backend python -m app.seed   # datos de ejemplo FICTICIOS (solo desarrollo)
```

- Aplicación: http://localhost:8000 · Adminer (visor de BD): http://localhost:8081
- Usuarios de ejemplo (contraseñas de prueba fijas): `admin.demo` / `10000001`, `lectura.demo` / `10000002`,
  `ana.ruiz` / `10000003`, `beto.luna` / `10000004`, `carla.soto` / `10000005`. Solo para desarrollo: en producción
  NO se siembra y el admin crea a cada usuario con la contraseña que elija.
- Volver a sembrar desde cero (solo dev): `docker compose exec -e FORCE_SEED=true backend python -m app.seed`
- Crear un admin sin datos de ejemplo: `docker compose exec backend python -m app.cli crear-admin "Nombre Apellido"`
- Disparar un job a mano: `docker compose exec backend python -c "from app.jobs import tareas; print(tareas.ejecutar('renovaciones'))"`
  (nombres: `renovaciones`, `prorrogas`, `purga_no_renovados`, `cierre_semana`, `recordatorio_captura`, `cierre_ciclo_campanas`).

## Desarrollo con recarga en vivo
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build   # backend con --reload en :8000
cd frontend && npm install && npm run dev                                       # interfaz en http://localhost:5173 (proxy a :8000)
```

## Sin Docker
Necesitas un PostgreSQL propio y Python 3.14. Ajusta `DATABASE_URL` en `.env` y:
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements-dev.txt
cd backend && python -m app.migrations.run_migrations && python -m app.seed && uvicorn app.main:app --port 8000
cd ../frontend && npm install && npm run build      # compila a backend/app/static; el backend lo sirve en el mismo puerto
```

## Pruebas automatizadas
Necesitan un Postgres con permiso para crear bases (cada corrida crea y borra la suya):
```bash
docker compose up -d db
cd backend && . ../.venv/bin/activate && python -m pytest -q       # toma credenciales de ../.env; o define TEST_DATABASE_URL
```
Reglas críticas cubiertas: bloqueo por contrato vencido, semáforo y calendario de campañas, cierre de ciclo y mensuales inmutables, campañas ligadas al cliente (pausa, No renovados, reingreso), importador de datos, prórroga de 5 días, mensaje de una sola vez, aislamiento por `cm_id`, reglas de reingreso y purga a 1 año, periodos y cortes de
quincena, jobs idempotentes, reportes (incluido recálculo de fórmulas del Excel con LibreOffice si está instalado).

## Adoptar los datos de los sistemas actuales
Si ya usas **Control de Clientes** y **Campañas** con datos reales, así se pasan a la plataforma sin perder nada.
**Haz un respaldo de las dos bases antes de empezar** (`pg_dump`).

1. **Control de Clientes se adopta tal cual.** La plataforma es un superconjunto exacto de su esquema: apunta `DATABASE_URL`
   de la plataforma a la base de Control de Clientes, conserva sus mismas `JWT_SECRET`, `JOBS_SECRET` y `AES_KEY_B64`
   (así las contraseñas de Facebook ya cifradas siguen funcionando) y aplica la migración nueva:
   ```bash
   cd backend && python -m app.migrations.run_migrations      # agrega el módulo de campañas (008); no toca tus datos
   ```
2. **Importa lo de Campañas** (usuarios, clientes, campañas, semanas, observaciones y mensuales). Primero **simula**: no guarda nada y
   te muestra el resumen y los avisos:
   ```bash
   cd backend
   python -m app.migracion.importar_campanas \
     --origen "postgresql+psycopg2://usuario:clave@host:5432/base_de_campanas" \
     --clave-aes-antigua "<AES_KEY_B64 que usaba Campañas>"
   ```
3. Revisa los **avisos** (p. ej. un cliente que en cada sistema lo atendía un CM distinto: se conserva el CM de la plataforma;
   si no es el correcto, reasígnalo en la ficha). Cuando todo esté bien, repite el comando agregando `--aplicar`.
4. Es **idempotente**: si lo vuelves a correr, las campañas ya importadas se omiten.

Qué hace: empareja usuarios por `username` (los nuevos conservan su contraseña), empareja clientes por CM + nombre sin importar acentos
o mayúsculas (**un cliente que existía en los dos sistemas queda en una sola ficha**), pasa las credenciales de la cuenta publicitaria
a las de Facebook del cliente (re-cifradas con la clave de la plataforma), y deja `cerrada` la campaña de un cliente que está en No renovados.
No importa notificaciones ni bitácora del sistema anterior.

## Producción
Ver **docs/DESPLIEGUE.md** (Render + Neon, cron-job.org, UptimeRobot, respaldos).

## Los dos entornos no se pisan
`docker-compose.yml` (proyecto `control-clientes`) y `docker-compose.demo.yml` (proyecto
`control-clientes-demo`) tienen cada uno su nombre de proyecto, sus contenedores y su volumen.
Usan los mismos puertos (8000 la aplicación, 5434 la base), así que **se levanta uno u otro, no los dos
a la vez**: si intentas levantar el segundo, Docker avisa de que el puerto está ocupado. Para cambiar de
uno a otro, baja el que esté corriendo primero (`docker compose down` o
`docker compose -f docker-compose.demo.yml down`).

Las pruebas se conectan a `localhost:5434` y funcionan con cualquiera de los dos: prueban primero las
credenciales de `.env` y después las del demo. Solo necesitan que la base esté levantada.
