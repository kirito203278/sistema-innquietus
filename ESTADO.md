> **Plataforma unificada.** Este documento nació como el estado del sistema de Control de Clientes. Desde la unión con el
> sistema de Campañas, ver [`docs/INTEGRACION.md`](docs/INTEGRACION.md) (módulo de campañas, reglas que lo atan al cliente,
> conflictos resueltos y lo que sigue pendiente). Todo lo que sigue sigue vigente para la parte de clientes y pagos.

# ESTADO — Control de clientes INNquietus

Referencia de solo lectura: `~/Documentos/referencia/sistema-campanas-master` (no modificar, no copiar entero).

## Fases
- [x] Fase 0 — Diseño: `docs/FASE0_esquema.sql`, `docs/FASE0_endpoints.md`. **Cerrada**: todas las preguntas respondidas.
- [x] Fase 1 — BD, migraciones, seed, Docker, `.env` (ver COMO_EJECUTAR.md). Pendiente del usuario: probar con Docker real (aquí no había Docker; se probó con Postgres 18 embebido).
- [x] Fase 2 — Auth, roles, equipo, baja de CM con migración (la reasignación de clientes sueltos va junto al router de clientes, Fase 3)
- [x] Fase 3 — Panel CM (backend + frontend)
- [x] Fase 4 — Renovación, No renovados, notificaciones, jobs (backend + frontend)
- [x] Fase 5 — Ingresos (pantalla CM y admin), recordatorios WhatsApp (SIN importador: la cartera arranca de cero)
- [x] Fase 6 — Reportes PDF/Excel + pruebas (incl. recálculo de fórmulas con LibreOffice) y vista previa en pantalla
- [x] Fase 7 — Producción: Dockerfile de dos etapas, secretos validados, CLI del primer admin, render.yaml, docs/DESPLIEGUE.md

## Decisiones (propuestas, pendientes de confirmar salvo indicación)
- Cada fila de `paquetes_cliente` = un CICLO; renovar crea fila nueva (`ciclo_anterior_id`). Pagos cuelgan del ciclo.
- Estado "por vencer" se calcula, no se guarda. `renovacion_pagada` la mantiene el servidor (pagado >= costo).
- `eliminado` = borrado lógico del paquete (se conservan pagos para reportes históricos).
- `clientes.cm_id NULL` = "Clientes por reasignar".
- `notificaciones.dedupe_key UNIQUE` (el proyecto anterior duplicó avisos al correr el job varias veces).
- `archivo_no_renovados` con ON DELETE CASCADE (bug de la purga en el proyecto anterior).
- Reutilizado de la referencia: AES-GCM, JWT 12 h, rate limit 5/15 min en memoria, `X-Jobs-Secret`, Dockerfile 2 etapas, tokens CSS y `branding.py`. Claves nuevas.

## Decisiones confirmadas por el usuario
- Ciclo = 30 días fijos. Al renovar, nueva fecha = anterior + 30 días.
- El ciclo se cobra en cada renovación. Tolerancia de pago: 3 días; si después sigue debiendo, el CM debe registrar prórroga (15 días naturales desde que se registra; una por ciclo).
- Línea de tiempo (R = día de renovación): aviso "¿renueva?" en R-4 (3 días antes de la fecha límite R-1) · fecha límite R-1 · vencido en R sin decisión · tolerancia de pago R..R+3 (contada desde R, default no contestado) · después, prórroga obligatoria si hay deuda. Ejemplo: R=10 nov → aviso 6 nov, límite 9 nov, tolerancia hasta 13 nov.
- Si renueva: ventana para conservar los mismos paquetes u otros; deudas/paquetes del ciclo anterior se conservan.
- Si no renueva: cliente (sin paquetes activos) pasa a "No renovados" con toda su info; se guarda **3 meses** y luego se elimina permanentemente (antes eran 12 meses en la propuesta).
- Reingreso: regla de 2 meses se mantiene (continuar vs. nuevo con historial borrado).
- Sin importador de Excel. Datos falsos solo para pruebas.
- Tipo y Paquete: no cambian reglas (etiquetas). Confirmado (opción A): dos catálogos, el Tipo es solo etiqueta.
- Pregunta 5 sin respuesta: se usa el default (admin con escritura puede capturar por un CM, con bitácora).

## Constantes (config, no hardcodeadas)
CICLO_DIAS=30, TOLERANCIA_DIAS=3, PRORROGA_MAX_DIAS=15, AVISO_DIAS_ANTES_RENOVACION=4, PURGA_MESES=3, REINGRESO_MESES=2

## Fase 1 — lo construido
- `backend/app/migrations/sql/`: `001_init.sql` (esquema + trigger `actualizado_en`), `002_catalogos_base.sql`. Runner idempotente con `schema_migrations`.
- Modelos ORM (`app/models.py`), config sin secretos por defecto (`app/config.py`), AES-GCM, bcrypt y contraseñas de 18 caracteres.
- `app/seed.py`: 5 usuarios (admin.demo, lectura.demo, ana.ruiz, beto.luna, carla.soto) y 15 clientes ficticios con fechas relativas a hoy que cubren: por vencer, vencido, amarillo/verde, prórroga por vencer, prórroga vencida con deuda, historial de renovación (Estándar→Élite), multi-paquete, por reasignar y No renovados de 20/70/95 días.
- `scripts/generar_env.py` crea `.env` (600) con claves nuevas. `docker-compose.yml`: db (127.0.0.1:5434), backend (:8000), adminer (:8081).
- 21 pruebas (CHECK de prórroga 15 días, estados, pagos, derivación de `pagado`, dedupe de notificaciones, CASCADE de No renovados, cifrado, seed).
- Dockerfile de una etapa; se vuelve de dos etapas en la Fase 7.
- Python local de desarrollo: 3.14; imagen Docker: 3.12 (requirements con `>=`).

## Decisiones de Ingresos y Reportes (Fases 5-6)
- Un solo generador (`services/reporte_datos.py`) alimenta la pantalla Ingresos, el JSON, el PDF y el Excel.
- Proyección = costo de ciclos con fecha de renovación en el periodo, excluyendo archivados y eliminados. Cobrado = pagos de esos ciclos con fecha <= corte (hoy). Un periodo cerrado se reporta completo (los pagos tardíos de un periodo viejo SÍ cuentan: el reporte es "cuánto de lo proyectado se ha cobrado a hoy").
- Periodo en curso (hoy <= último día) = "Periodo parcial, corte al hoy"; la proyección es la del periodo completo. 2da quincena termina el último día real (28/29/30/31).
- Secciones 4 (Prórrogas) y 5 (Pendientes) NO se limitan al periodo: son listas de trabajo con todo lo vigente a la fecha de corte.
- Tasa de renovación = renovados / (ciclos que llegaron a su fecha en el periodo, incluidos archivados/eliminados).
- Reportes: CM obtiene el mismo generador filtrado por su cartera (el `cm_id` de la petición se ignora para un CM). Admin de solo lectura puede descargar.
- Excel: hoja por sección; totales y derivados (restante, %, días, SUMIFS por CM) son fórmulas reales, verificadas recalculando con LibreOffice.

## Regla agregada al final
- Renovar con OTRO paquete reinicia el contador «renovaciones con este paquete» (derivado de la cadena de ciclos, `ciclos.veces_renovado`) y aplica los datos nuevos (paquete, tipo, costo); renovar con el mismo lo incrementa. El historial de ciclos se conserva.

## Pendiente del usuario
- Probar con Docker real (aquí no había Docker; todo se probó con Postgres 18 embebido y uvicorn).
- Desplegar siguiendo docs/DESPLIEGUE.md. docs/FASE0_endpoints.md es el diseño inicial; la API final difiere (prefijos /api/clientes, /api/paquetes...).

## REGLAS ACTUALIZADAS (reemplazan a las anteriores donde choquen)
- **Sin tolerancia de pago.** El contrato termina el día de renovación R a las 23:59 (México). Desde R+1 el paquete queda **bloqueado**
  (se calcula por la fecha, no depende del job): ventana que no se puede cerrar con las salidas válidas:
  *Renovó* (solo si ya pagó completo) · *No renovó* · *Solicitó prórroga* (solo si debe y solo una vez). Mientras haya un paquete
  bloqueado, toda escritura sobre ese cliente se rechaza (409 `bloqueado`) salvo esas tres salidas (aplica también a un admin).
- **Prórroga fija de 5 días naturales** desde que se activa (botón; el CM no elige fecha). Admite pagos parciales o el resto. Si vence
  sin pago completo: el ciclo se archiva solo, el cliente pasa a No renovados (si era su último paquete) y se deja listo el mensaje
  para el cliente + aviso al CM. Si se paga completo en la prórroga, vuelve la ventana (Renovó / No renovó). BD: constraint `prorroga_max_5_dias` (NOT VALID: no rechaza filas viejas).
- **Mensaje al cliente: se envía una sola vez.** Al marcarlo como enviado no se puede generar ni marcar otro del mismo paquete.
- **Sin decisión:** 2 días con la ventana activa (`dias_para_decidir`); después, a las 00:05, pasa solo a No renovados. Con prórroga, el plazo
  corre desde el fin de la prórroga si ya pagó.
- **«No renovará» marcado antes del fin del contrato:** no archiva de inmediato; el job lo archiva al terminar el contrato (se puede deshacer antes).
  Ya vencido, «No renovó» archiva en el momento.
- **No renovados se conservan 1 año** (`purga_meses=12`), ya no 3 meses. Regla de reingreso de 2 meses sin cambio.
- **Fechas automáticas:** al crear un paquete se captura la fecha de **inicio** (renovación = inicio + 30). Al renovar o reingresar el ciclo nuevo empieza
  **HOY** (el día que se confirma) y renueva en 30 días; no se captura fecha. Cambiar el inicio recalcula la renovación y mueve al cliente de quincena
  (1ra = días 1-15, 2da = 16 al último día del mes).
- **Renovó exige el paquete pagado por completo** (si no, prórroga o no renovó). Consecuencia: la columna «Renovados sin pago» del tablero queda para datos históricos.
- Se retiró la pregunta «¿El cliente pagó?» de las notificaciones: ahora el vencimiento de prórroga actúa solo y deja el mensaje listo.
- Jobs: `renovaciones` y `prorrogas` a las 00:05 y 12:00; `purga_no_renovados` a las 12:10.
- Constantes: CICLO_DIAS=30, PRORROGA_MAX_DIAS=5, DIAS_PARA_DECIDIR=2, AVISO_DIAS_ANTES_RENOVACION=4, AVISO_PRORROGA_DIAS=3, PURGA_MESES=12, REINGRESO_MESES=2.

## Contraseñas (cambio posterior)
- Las contraseñas de usuarios ya NO las genera el sistema: el **admin las escribe** al crear un usuario y al cambiarlas (mínimo 8 y máximo 72 caracteres, sin espacios en los bordes; bcrypt).
  La API nunca devuelve una contraseña y la bitácora no las guarda. Un CM no puede cambiar contraseñas.
- Todos los campos de contraseña de la interfaz (login, alta/cambio de usuario, contraseña de Facebook del cliente) tienen botón «Ver/Ocultar» para revisar lo escrito.
  El alta de usuario ofrece «Sugerir una» (aleatoria, generada en el navegador).
- El seed deja contraseñas de EJEMPLO fijas (ver COMO_EJECUTAR.md). El CLI `python -m app.cli crear-admin` sigue generando una contraseña temporal para el primer admin de producción.

## Prórroga = renovación automática al pagar (ajuste posterior)
- Solicitar prórroga implica que el cliente sigue. En cuanto se **paga completo dentro de los 5 días**, el paquete se **renueva solo** (mismo paquete, tipo y costo;
  el ciclo nuevo empieza el día del pago, +30 días). No se renueva al pedir la prórroga (el ciclo anterior seguiría sin pagarse). Para cambiar de paquete se usa la siguiente renovación.
- Con la prórroga activa ya no se muestran «Renovó / No renovó»: no hay nada que decidir. Si no se completa a los 5 días, pasa a No renovados.

## Los tres casos de «no me han contestado» (reglas vigentes; reemplazan a las anteriores donde choquen)
- **La ventana vive DENTRO del cliente/paquete** (no bloquea el sistema): con los demás clientes se trabaja normal. En el panel del CM sale un aviso con los pendientes, el cliente lleva la marca «decidir» en la lista y el tablero lo marca. El servidor traba solo las escrituras de ESE cliente (409 `bloqueado`).
- **Caso 1 – no contesta:** al terminar el contrato (R 23:59) la ventana pregunta **«¿va a renovar o no?»**. Tolerancia de **2 días** (solo en este caso); sin respuesta pasa a No renovados.
  Si contesta **«sí va a renovar»**: se habilitan las funciones; **ese día es el inicio del nuevo contrato** y **no hay tolerancia de pago**: a las 23:59 de ese mismo día, si no pagó, la ventana pregunta
  **prórroga o no renovó** (sin plazo automático: queda pendiente hasta que el CM decida). Si ya pagó, se renueva en el momento.
- **Caso 2 – dijo que no renovará** (casilla «No renovará»): se archiva solo al terminar el contrato; no hay ventana. Se puede deshacer antes.
- **Caso 3 – confirmó que renovará pero no ha pagado** (botón «Confirmó que renovará», antes de R): semáforo amarillo; en cuanto paga completo se renueva solo; al terminar el contrato se bloquea y pregunta por la prórroga.
- **Inicio del nuevo contrato = el día que se confirma** (`confirmado_en`), aunque el pago se complete después en la prórroga (renovación = inicio + 30). Auto-renovación al pagar completo si ya confirmó o pidió prórroga (mismo paquete y costo; el cambio de paquete es en la siguiente renovación).
- **«No renovó» tiene dos alcances:** solo este paquete, o **todo el cliente** (se archivan todos sus paquetes vigentes y pasa a No renovados). Antes de que termine el contrato solo existe «no renovará» por paquete (programado).
- La prórroga solo se ofrece a quien ya confirmó que renovará y no ha pagado (una vez, 5 días).
- BD: `gracia_hasta` (004) y `confirmado_en` (005).

## Ajustes finales (reemplazan a lo anterior donde choquen)
- **Un cliente tiene UN solo paquete** (no existen clientes con 2). La API rechaza un segundo paquete (409) y un alta con 2 (422). Se agrega paquete solo a un cliente sin paquete vigente. Desaparece «no renovó por paquete / por cliente»: no renovar el paquete = el cliente a No renovados.
  (Se aplica en la aplicación, no con índice único en BD, para que la migración no falle en bases con datos viejos.)
- **Prórroga conserva la fecha de renovación original:** si el ciclo usó prórroga, el nuevo contrato empieza en la fecha de renovación original (R) y renueva R+30; no se recorre al día en que termine de pagar. Sin prórroga, el inicio es el día de la confirmación (o el día de «Renovó»).
- **Cambiar de paquete solo al renovar:** se elige al confirmar «va a renovar» (mismo paquete u otro con su tipo y costo; se guarda como plan y se aplica al concretarse la renovación) o en «Renovó». Fuera de la renovación NO se editan paquete/tipo/costo: un CM solo corrige la fecha de inicio; un admin con escritura puede corregir capturas erróneas (bitácora).
- Quien no paga (venció la prórroga) o no pidió prórroga pasa a No renovados: sin cambios.
- BD: migración 006 (`renovara_paquete_id`, `renovara_tipo_id`, `renovara_costo`).

## Separación CM / administrador (2026-10-06, reemplaza a lo anterior donde choque)
- **El dinero es del administrador.** El CM ya no ve ni escribe ningún monto: costo, pagado, restante, avance y la lista de pagos se omiten en la API para un usuario con rol `cm` (`app/services/visibilidad.py`), no solo en la interfaz.
- **Solo admin (403 para el CM):** registrar y borrar pagos, activar la prórroga, generar y marcar el mensaje de cobro, Ingresos y Reportes (`/api/ingresos`, `/api/reportes/*`).
  Desaparece la regla anterior de que un CM borraba sus propios pagos el mismo día: ahora ningún CM borra pagos y el administrador borra cualquiera.
- **El CM decide renovación, no dinero.** En la ventana de bloqueo el CM ve «Sí, va a renovar» / «Renovó» / «No renovó»; el botón de prórroga solo lo ve el administrador. Si el único camino era la prórroga, al CM se le dice que la autoriza el administrador y le queda «No renovó».
- **Cambio de paquete al renovar:** lo elige el administrador. Si confirma un CM, se ignoran `paquete_id`, `tipo_id` y `costo`: renueva con el mismo paquete.
- **Costo en el catálogo de paquetes** (migración 007, columna `catalogo_paquetes.costo`). Cuando un CM da de alta un cliente o un paquete, el costo sale del catálogo y lo pagado empieza en cero; el administrador ajusta el costo en Catálogos o en la ficha del cliente. Un administrador sí puede fijar el costo al dar de alta.
- **Panel del CM:** Mi cartera (tabla con el mismo formato que la cartera del admin, con filtro Todos / 1ra quincena / 2da quincena y buscador), Renovaciones y No renovados. Se quitaron Ingresos y Reportes, y la lista de clientes salió de la barra lateral.
- Sin cambios: aislamiento por CM, bloqueo por fecha, 5 días de prórroga, 2 días para decidir, el resto de [S03].

## Reglas confirmadas y ajustes (2026-10-06, segunda tanda)
- **Eliminar clientes: solo el administrador y solo desde No renovados.** Un cliente activo ya no se borra: primero se marca «no renovó» (así conserva su información 1 año) y después, si se quiere, se elimina. El CM ya no puede borrar paquetes ni clientes: en «No renovó» solo le queda «Conservar en historial».
- **Baja de un CM:** si todavía tiene clientes, hay que pasarlos a otro CM. Ya no se pueden dejar «por reasignar» al darlo de baja; para repartirlos entre varios, se reasignan antes desde Cartera.
- **La ventana de decisión también le aparece al administrador:** su panel lleva el mismo aviso de pendientes que el del CM, con acceso directo a cada cliente.
- **Ingresos y Reportes abren en «mes completo»**; las quincenas quedan como filtro. La proyección y lo cobrado de cada CM son del periodo elegido.
- **Al mover un cliente de CM, su proyección y lo pagado se van con él** (los reportes agrupan por el CM actual del cliente). Ya funcionaba así; ahora hay una prueba que lo fija.
- Sin cambios (confirmadas): 30 días por ciclo desde el inicio del contrato; «no renovará» archiva al terminar el contrato; 2 días para decidir cuando el cliente no contesta; prórroga de 5 días que conserva la fecha de renovación original; 1 año en No renovados; reingreso por CM o admin; el ciclo de cobro va por la fecha de contrato de cada cliente, no por el calendario del mes.

### Cuándo aparece «Renovados sin pago»
Con las reglas vigentes un paquete no renueva debiendo, así que esa columna solo se llena cuando, **después** de renovar, el ciclo cerrado se queda con saldo: porque el administrador corrigió el costo hacia arriba o porque se borró un pago mal capturado. Los datos de ejemplo traen un caso de cada uno (Mueblería Don Rafa y Barbería El Corte). El cliente que confirmó que renovará y aún no paga no sale ahí: está en amarillo, y pasa a «Vencidos sin decisión» cuando se le termina el contrato.

## Prórroga activa: se trabaja normal (2026-10-06, aclaración del usuario)
- Al activar la prórroga, **la fecha de renovación del paquete no se mueve**: queda la que tenía antes de pedirla, y el contrato nuevo arrancará en esa misma fecha (ya era así).
- **Con la prórroga corriendo el cliente NO está bloqueado**: se le registran pagos, se edita su ficha y se trabaja con él como con cualquier otro. No hay nada que decidir mientras dure.
- Lo único que pasa solo es que, **si al terminar su último día no pagó completo, el cliente pasa a No renovados**. El día del vencimiento todavía cuenta: el trabajo programado lo archiva en la siguiente corrida (00:05 del día siguiente), igual que el contrato que termina a las 23:59.
- Ajustes para que la pantalla diga lo mismo que la regla:
  · el semáforo de un paquete con prórroga activa es **amarillo** (ya decidió, falta el pago), no rojo;
  · el tablero tiene una columna **«En prórroga»**; antes esos paquetes salían en «Vencidos sin decisión», que es justo lo contrario de lo que son.
