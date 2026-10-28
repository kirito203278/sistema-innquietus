# Cómo se unieron los dos sistemas

La plataforma toma **Control de Clientes como base** (es el más maduro: valida secretos al arrancar, estado derivado
de fechas, reloj inyectable, capa de servicios) y le **absorbe Campañas como un módulo** que cuelga del mismo cliente.
No hay dos aplicaciones pegadas: hay una sola base de datos, un solo login, un solo cliente y un solo menú.

```
usuarios ─┬─ clientes ─┬─ paquetes_cliente ─┬─ pagos / renovaciones      (Clientes y pagos)
          │            │                    └──────────────┐ (vínculo opcional)
          │            └─ campanas ─┬─ semanas              │
          │                         ├─ observaciones   ◄─────┘            (Campañas)
          │                         └─ mensuales (inmutables)
          └─ notificaciones · bitacora · jobs_ejecuciones                  (compartidas)
```

Migración `008_modulo_campanas.sql` agrega `campanas`, `semanas`, `observaciones`, `mensuales` y `metricas_config`,
tres columnas de pago en `clientes` (la 009 agrega `cuentas_fb` y `clientes.cuenta_id`) y los nuevos tipos de notificación. **No duplica** usuarios, clientes,
notificaciones ni bitácora: los comparte.

## Reglas que atan los dos módulos

| Regla | Qué pasa |
|---|---|
| Una campaña cuelga **del cliente** | Se crea desde la ficha del cliente y se liga sola a su paquete vigente (venta → campaña). |
| Cliente **en pausa** (contrato terminado sin decidir) | No admite crear campañas, capturar semanas ni agregar observaciones (409 `bloqueado`), igual que el resto de escrituras sobre ese cliente. Leer sí se puede. |
| Cliente pasa a **No renovados** | Sus campañas abiertas se **cierran solas** (archivando el mensual de lo capturado) y el histórico se conserva. |
| **Reingreso con «borrón y cuenta nueva»** (≥ 2 meses) | Además de los paquetes, se borran sus campañas. Con reingreso reciente se conservan. |
| Borrar un cliente | Solo el admin, desde No renovados (regla de Clientes). Borra en cascada campañas, semanas y mensuales. |
| Aislamiento por CM | Un CM solo ve las campañas de **sus** clientes; otro CM recibe 404, también en listados, reportes y PDF. |
| Avisos | Campañas usa el mismo buzón y campana de notificaciones (tipos `campana_vencida`, `recordatorio_captura`). |
| Reloj | Todo usa `app.dates` (no `date.today()`), así que se puede probar cualquier día. |

## Conflictos entre los dos sistemas y cómo se resolvieron

| Conflicto | Resolución |
|---|---|
| **«Cliente» duplicado** (distinto esquema en cada sistema) | Una sola tabla `clientes`. El importador empareja por (CM, nombre) sin acentos ni mayúsculas y avisa cuando cada sistema lo atendía un CM distinto. |
| **Credenciales cifradas** (cuenta publicitaria con huella vs. Facebook del cliente, cada una con su clave AES) | Una sola: las credenciales de Facebook del cliente. Se re-cifran con la clave de la plataforma al importar. |
| **Quién borra clientes** (CM en Campañas, solo admin en Clientes) | Gana la regla de Clientes: solo el admin, desde No renovados. |
| **Estado almacenado vs. derivado** | La edición de una semana se **deriva de la fecha** (no depende de que el job del sábado haya corrido). |
| **Cierre de ciclo solo si la fecha era exactamente hoy** | Ahora corre con `fecha_renovacion <= hoy`: si el servidor estuvo caído ese día, la campaña igual vence. |
| **Constantes sueltas** (365 días, 60 días) | Desaparecen: «No renovados» y sus plazos los gobierna solo Clientes (`purga_meses`, `reingreso_meses`). |
| **Secretos débiles al arrancar** (Campañas) | La plataforma se niega a arrancar con JWT/AES/jobs débiles (validación de Clientes). |
| **Rate limit por usuario** | Por (IP, usuario): un tercero no puede bloquear la cuenta de otro. |
| **Dos juegos de jobs** | Uno solo, en el mismo scheduler, con registro de cada corrida en `jobs_ejecuciones` y disparables por `POST /api/jobs/run/{nombre}`. |

## Lo que cambió o se simplificó respecto al sistema de Campañas

Para que el cliente sea **uno solo**, estas cosas ya no funcionan como antes:

- **Alta de clientes por lote** (varios clientes + su campaña de una vez) → el cliente se da de alta como en Clientes y la campaña se agrega desde su ficha.
- **Cuentas de Facebook compartidas entre clientes** → se conservan: un CM captura una cuenta (correo + contraseña) una sola vez y la usan varios de sus clientes. Se reconoce por el correo (mismo CM); al dar de alta otro cliente basta elegirla de la lista o escribir el mismo correo. Cambiar la contraseña la cambia para todos; cambiar el correo de un cliente lo pasa a otra cuenta. Tabla `cuentas_fb` (migración 009).
- **«No renovar» a nivel cliente desde la campaña, «continuar» y «reactivar»** → una campaña se **da por terminada** (queda `cerrada`, con su histórico) y se puede **reabrir** renovándola. El estado del cliente lo deciden sus paquetes.
- **Reportes PDF por cliente** se conservan (semanal y mensual consolidados). El «PDF de credenciales de entrega» no se portó.
- La columna de texto `paquete` de la campaña se reemplazó por el **vínculo** al paquete vigente del cliente.
- Notificaciones y bitácora del sistema anterior **no se importan** (son efímeras).

## Endpoints del módulo (todos bajo `/api`, con JWT)

| Método y ruta | Quién |
|---|---|
| `GET /campanas?cliente_id&cm_id&estado&q` | CM (las suyas) · admin (todas) |
| `POST /clientes/{id}/campanas` · `GET /campanas/{id}` | escribe CM/admin · lee todos |
| `POST /campanas/{id}/renovar` · `POST /campanas/{id}/cerrar` | CM/admin |
| `GET /campanas/{id}/semanas` · `PUT /semanas/{id}` | captura CM/admin |
| `POST /semanas/{id}/habilitar-edicion` | admin con escritura (2 h, sáb 8:00 → vie 15:00) |
| `GET·POST /campanas/{id}/observaciones` | CM/admin |
| `GET /campanas/{id}/mensuales` (2 meses al CM, 3 al admin) · `POST …/mensuales/manual` (una sola vez) | CM/admin |
| `GET /clientes/{id}/campanas/consolidado` · `…/reporte-mensual` · `…/reporte-semanal` (PDF) | CM (sus clientes) · admin |
| `GET /metricas` · `PATCH /metricas/{id}` | lee todos · edita admin con escritura |

## Trabajos programados (zona America/Mexico_City)

| Job | Cuándo | Qué hace |
|---|---|---|
| `renovaciones`, `prorrogas` | 00:05 y 12:00 | (Clientes) avisos, vencimientos, archivo |
| `purga_no_renovados` | 12:10 | (Clientes) elimina clientes con ≥ 12 meses |
| `cierre_semana` | sábado 00:00 | bloquea la semana que terminó (las no capturadas quedan en 0) y abre la nueva |
| `recordatorio_captura` | viernes 14:00 | un aviso por responsable con las campañas sin capturar |
| `cierre_ciclo_campanas` | diario 12:00 | archiva el mensual de las campañas cuya renovación llegó y las deja `vencida` |

## Pasar tus datos actuales

Ver la sección **«Adoptar los datos de los sistemas actuales»** de [`COMO_EJECUTAR.md`](../COMO_EJECUTAR.md).

## Qué sigue sin existir

Esta unión cubre **Clientes + Pagos + Campañas**. Del Plan Maestro siguen pendientes: Ventas, Contenido/Parrilla (hoy solo
existe como prototipo estático), Diseño, IA y un modelo de permisos por rol más fino que `cm` / `admin`.
