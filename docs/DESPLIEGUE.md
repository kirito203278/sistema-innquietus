# Guía de despliegue: Render + Neon, con cron-job.org y UptimeRobot

Todo con planes gratuitos y sin tarjeta. Tiempo estimado: 30–40 min. Los nombres de botones de cada servicio pueden cambiar;
verifica límites y condiciones del plan gratuito en el panel de cada uno antes de depender de ellos.

## Cómo encaja todo

```
 navegador ──HTTPS──► Render (1 contenedor: API + interfaz + scheduler) ──► Neon (PostgreSQL)
                          ▲  ▲
   cron-job.org ──POST────┘  └── UptimeRobot (GET /api/health cada 5 min)
   (00:05, 12:00 y 12:10, hora de México)
```

El contenedor corre **un solo proceso**: el scheduler interno (APScheduler) y el bloqueo de intentos de login viven en memoria.
No escales a más de una instancia. El plan gratuito de Render **duerme** el servicio tras unos minutos sin tráfico, por eso hay un
respaldo externo: cron-job.org llama a los jobs por HTTP (la llamada despierta el servicio) y UptimeRobot lo mantiene despierto.
Los jobs son idempotentes: que corran el scheduler **y** cron-job.org el mismo día no duplica avisos.

## 0. Antes de empezar (en tu computadora)

1. Sube el proyecto a **un repositorio privado de GitHub** (cuenta personal o de la agencia). Revisa que `.env` NO esté en el repo
   (ya está en `.gitignore`):
   ```bash
   git ls-files | grep -E "(^|/)\.env$" || echo "OK: .env no está versionado"
   ```
2. Genera la clave de cifrado de producción (**distinta** a la de desarrollo) y guárdala en tu gestor de contraseñas:
   ```bash
   python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"
   ```
   > ⚠️ Si pierdes `AES_KEY_B64` no hay forma de recuperar las contraseñas de Facebook guardadas. Si la cambias, se vuelven ilegibles.

## 1. Base de datos en Neon

1. Crea una cuenta en neon.tech → **New project**. Elige la región más cercana (p. ej. US East / São Paulo).
2. En **Connection details** copia la cadena de conexión **directa** (no la de "pooler"), con `sslmode=require`:
   `postgresql://USUARIO:CLAVE@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`
3. No hay que crear tablas: la app aplica las migraciones sola al arrancar.

## 2. Aplicación en Render

1. render.com → **New → Blueprint** → conecta tu repositorio. Render lee `render.yaml` (Docker, plan Free, health check `/api/health`).
2. Te pedirá las variables marcadas como secretas:
   | Variable | Valor |
   |---|---|
   | `DATABASE_URL` | la cadena de Neon del paso anterior |
   | `AES_KEY_B64` | la clave generada en el paso 0 |
   | `CORS_ORIGINS` | `https://TU-APP.onrender.com` (la URL que te asigne Render; puedes editarla después del primer deploy) |
   `JWT_SECRET` y `JOBS_SECRET` los genera Render. **Copia el valor de `JOBS_SECRET`** (Environment → mostrar): lo necesitas en el paso 4.
3. Espera el primer deploy (el build compila el frontend; tarda varios minutos). Comprueba:
   ```bash
   curl https://TU-APP.onrender.com/api/health      # {"ok":true}
   ```
4. Actualiza `CORS_ORIGINS` con la URL definitiva si hiciste el deploy con un valor provisional y vuelve a desplegar.

> La app valida los secretos al arrancar: si `JWT_SECRET`, `JOBS_SECRET` o `AES_KEY_B64` son débiles o inválidos, no arranca y lo dice en los logs.

## 3. Primer administrador

El plan gratuito de Render no ofrece terminal, y el alta de usuarios de la app exige haber entrado antes como admin. Se resuelve
creando el primer admin **desde tu computadora, contra la base de Neon**:

```bash
cd backend && python3 -m venv ../.venv && . ../.venv/bin/activate && pip install -r requirements.txt

export DATABASE_URL='postgresql://USUARIO:CLAVE@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require'
# El CLI no usa estos tres secretos, pero la configuración los exige válidos para cargar: valores desechables (NO son los de producción)
export JWT_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(40))')"
export JOBS_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')"
export AES_KEY_B64="$(python3 -c 'import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())')"

python -m app.cli crear-admin "Nombre Apellido"
```

Imprime el usuario y una contraseña temporal de 18 caracteres **una sola vez** (solo para este primer admin). Entra a la app con ellos y, desde
**Equipo**, da de alta al resto del equipo (CMs y otros admins): **tú escribes la contraseña de cada persona** (mínimo 8 caracteres, con botón
«Ver» para revisarla antes de crear) y se la entregas. Puedes cambiar tu propia contraseña y la de cualquiera desde **Equipo → Cambiar contraseña**. Si algún día pierdes el acceso del único admin:
`python -m app.cli reset-password usuario` (misma forma).

## 4. Jobs programados en cron-job.org (respaldo del scheduler)

Crea cuenta en cron-job.org y estas tareas. En todas: **Zona horaria = America/Mexico_City**, método **POST**, y en *Advanced →
Headers* agrega `X-Jobs-Secret` con el valor de `JOBS_SECRET`. Sube el *timeout* al máximo permitido: si el servicio está dormido,
el primer request tarda hasta ~1 min en despertar. Activa el aviso por correo si una ejecución falla.

Los contratos terminan a las **23:59** del día de renovación, así que `renovaciones` y `prorrogas` corren **dos veces al día**:
a las 00:05 (para que los bloqueos, archivados y avisos ocurran justo después de esa hora) y a las 12:00 (respaldo y avisos del día).

| Tarea | URL | Horario |
|---|---|---|
| Renovaciones: aviso a R-4, bloqueo por fecha vencida, archivado de «no renovará» y de quien no decide en 2 días | `https://TU-APP.onrender.com/api/jobs/run/renovaciones` | diario 00:05 **y** 12:00 (2 tareas) |
| Prórrogas: aviso a 3 días y paso a No renovados si vence sin pago | `https://TU-APP.onrender.com/api/jobs/run/prorrogas` | diario 00:05 **y** 12:00 (2 tareas) |
| Purga de No renovados (1 año) | `https://TU-APP.onrender.com/api/jobs/run/purga_no_renovados` | diario 12:10 |

> Aunque cron-job.org falle, el bloqueo de un paquete vencido **no depende de los jobs**: el servidor lo calcula por la fecha en cada
> petición. Los jobs solo hacen los cambios automáticos (archivar, avisos).

Prueba cada una con "Test run": debe responder `200` y `{"ok":true,...}`. Un secreto incorrecto responde `401`.
Opcional: una tarea GET a `/api/health` a las 00:00 y a las 11:55 para que el servicio ya esté despierto cuando lleguen las anteriores.

## 5. Monitoreo con UptimeRobot

Crea cuenta en uptimerobot.com → **Add New Monitor** → tipo **HTTP(s)**, URL `https://TU-APP.onrender.com/api/health`, intervalo
5 minutos, con aviso por correo. Además de avisarte si se cae, reduce los "arranques en frío" del plan gratuito.

## 6. Respaldos

Neon gratuito conserva poco historial; haz respaldos propios de forma periódica (p. ej. cada semana y antes de cambios grandes):

```bash
docker run --rm -v "$PWD":/backup postgres:17-alpine \
  pg_dump "postgresql://USUARIO:CLAVE@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require" -Fc -f /backup/respaldo-$(date +%F).dump
```
(La versión mayor de `pg_dump` debe ser igual o mayor que la del servidor Neon; ajusta `postgres:17-alpine` si Neon usa otra.)
Guarda también tu copia de `AES_KEY_B64`: el respaldo sin esa clave no sirve para las credenciales de Facebook.
Restaurar: `pg_restore --clean --if-exists -d "<cadena de conexión>" respaldo.dump`.

## 7. Lista de verificación después del deploy

- [ ] `https://TU-APP.onrender.com/api/health` responde `{"ok":true}`.
- [ ] Entras con el admin creado y ves el panel; `/docs` responde 404 (no se expone la documentación de la API).
- [ ] Creaste un CM de prueba, un cliente con un paquete y registraste un pago.
- [ ] Descargaste el reporte PDF y el Excel del mes en curso.
- [ ] Las 5 tareas de cron-job.org responden 200 con "Test run".
- [ ] UptimeRobot muestra el servicio "Up".
- [ ] `CORS_ORIGINS` contiene solo tu dominio (nunca `*`).
- [ ] Guardaste `AES_KEY_B64`, `JOBS_SECRET` y la cadena de Neon en un gestor de contraseñas.
- [ ] Borraste el usuario de prueba y sus datos antes de capturar la cartera real.

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| El deploy falla al arrancar con un error de validación | Falta/está mal un secreto (mensaje en los logs de Render). |
| `could not connect to server` | `DATABASE_URL` mal copiada o sin `?sslmode=require`. |
| El navegador muestra error de CORS | `CORS_ORIGINS` no coincide exactamente con la URL (con `https://`, sin `/` final). |
| Los avisos de las 12:00 no llegan | Revisa el historial de cron-job.org (¿401? secreto distinto; ¿timeout? sube el límite) y la tabla `jobs_ejecuciones`. |
| Primera carga lenta tras horas de inactividad | Normal en el plan gratuito (arranque en frío). |
