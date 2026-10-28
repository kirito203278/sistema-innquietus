# Endpoints propuestos (Fase 0)

Prefijo `/api`. Auth: `Authorization: Bearer <JWT 12 h>`. Roles: **CM** (filtra siempre por `cm_id = current_user.id` en la capa de datos), **Admin** (`W` = escritura; el admin solo lectura recibe 403 en W).
Errores en español, formato `{detail}`. Dinero como string decimal; fechas ISO (`YYYY-MM-DD`).

## Auth
| Método | Ruta | Quién | Notas |
|---|---|---|---|
| POST | `/auth/login` | público | bcrypt; 5 fallos/15 min → 429 |
| GET | `/auth/me` | todos | |
| POST | `/auth/primer-ingreso` | todos | marca `primer_ingreso=false` (pantalla "Comenzar") |

## Admin · equipo y catálogos
| Método | Ruta | Quién |
|---|---|---|
| GET | `/admin/usuarios` | Admin |
| POST | `/admin/usuarios` (crea CM o admin, `solo_lectura`; devuelve contraseña de 18 car. UNA vez) | Admin W |
| POST | `/admin/usuarios/{id}/reset-password` (idem, una sola vez) | Admin W |
| POST | `/admin/usuarios/{id}/baja` (CM: `migrar_a_cm_id` o `null`=por reasignar; si 0 clientes no pide destino) | Admin W |
| POST | `/admin/clientes/{id}/reasignar` (`cm_id` o `null`) | Admin W |
| GET | `/admin/clientes/por-reasignar` | Admin |
| GET / POST / PATCH | `/admin/catalogo/paquetes`, `/admin/catalogo/tipos` (alta, renombrar, orden, activar/desactivar) | Admin / Admin W |
| GET | `/catalogo/paquetes`, `/catalogo/tipos` (solo activos, para los dropdowns) | todos |
| GET | `/admin/bitacora` | Admin |
| GET | `/admin/cms` · `/admin/cms/{id}/clientes` · `/admin/clientes/{id}` (vista de cartera, solo lectura de ficha) | Admin |

## Clientes y ficha (CM; el admin W puede las mismas bajo `/admin/...` si se confirma — ver pregunta 5)
| Método | Ruta | Notas |
|---|---|---|
| GET | `/cm/clientes?quincena=1\|2` | barra lateral; filtro por quincena de `fecha_renovacion` de algún paquete vigente |
| POST | `/cm/clientes` | alta (nombre, contactos, credenciales FB cifradas, paquetes iniciales opcionales) |
| GET | `/cm/clientes/{id}` | ficha **sin** contraseña FB |
| PATCH | `/cm/clientes/{id}` | edita ficha |
| POST | `/cm/clientes/{id}/password-fb/ver` | descifra y registra en bitácora (botón "Ver") |
| DELETE | `/cm/clientes/{id}` | doble confirmación (`confirmar_nombre`) |
| GET | `/cm/no-renovados` | |
| POST | `/cm/clientes/{id}/reingresar` | `modo`: `continuar` \| `nuevo` (≥2 meses fuerza `nuevo` y borra historial anterior; a los 3 meses el cliente ya fue purgado) |

## Paquetes, pagos y prórroga (CM)
| Método | Ruta | Notas |
|---|---|---|
| GET | `/cm/clientes/{id}/paquetes` | vigentes + historial; cada uno con pagado, restante, % avance, estado derivado (por vencer), semáforo |
| POST | `/cm/clientes/{id}/paquetes` | alta de paquete (paquete, tipo, costo, inicio, renovación) |
| PATCH | `/cm/paquetes/{id}` | tipo, costo, fecha (con bitácora) |
| GET | `/cm/paquetes/{id}/pagos` | |
| POST | `/cm/paquetes/{id}/pagos` | monto > 0 y ≤ restante; recalcula `renovacion_pagada` |
| DELETE | `/cm/pagos/{id}` | solo el mismo día y quien lo registró; bitácora |
| PUT | `/cm/paquetes/{id}/prorroga` | `hasta` ≤ hoy + 15 días naturales (servidor, `America/Mexico_City`); solo si pagado < costo; una por ciclo |
| POST | `/cm/paquetes/{id}/recordatorio` | genera texto + enlace `wa.me`; fila en `recordatorios_cliente` |
| POST | `/cm/recordatorios/{id}/marcar-enviado` | |

## Renovación (CM)
| Método | Ruta | Notas |
|---|---|---|
| GET | `/cm/renovaciones/tablero?mes=&quincena=` | 4 columnas: por vencer, vencidos sin decisión, renovados sin pago, completos |
| POST | `/cm/paquetes/{id}/confirmar-renovacion` | `renovacion_decision` = si/no/pendiente (sin cerrar ciclo) |
| POST | `/cm/paquetes/{id}/renovar` | `paquete_id`, `tipo_id`, `costo`, `fecha_renovacion` (por defecto = fecha actual del ciclo + 30 días) → cierra ciclo, abre el nuevo, fila en `renovaciones` |
| POST | `/cm/paquetes/{id}/no-renovar` | `accion`: `conservar` \| `borrar` (+ `confirmar_nombre`; si era el último: `eliminar_cliente` bool) |
| GET | `/cm/paquetes/{id}/historial` | cadena de ciclos + renovaciones |

## Notificaciones
| Método | Ruta |
|---|---|
| GET | `/notificaciones?solo_no_leidas=` |
| POST | `/notificaciones/{id}/leer` · `/notificaciones/leer-todas` |
| POST | `/notificaciones/{id}/responder` (`pago`: si/no; "sí" → pide pago; "no" → genera recordatorio) |

## Ingresos
| Método | Ruta | Notas |
|---|---|---|
| GET | `/cm/ingresos?mes=&anio=&quincena=1\|2\|ambas` | por cliente + totales + % cobrado |
| GET | `/admin/ingresos?mes=&anio=&quincena=&cm_id=` | por CM + total general + tasa de renovación |

## Reportes (generador único, parametrizado por `cm_id` opcional)
| Método | Ruta | Quién |
|---|---|---|
| GET | `/admin/reportes/datos?mes=&anio=&quincena=` | Admin (incl. solo lectura): las 6 secciones en JSON, cabecera cerrado/parcial |
| GET | `/admin/reportes/pdf?...` · `/admin/reportes/excel?...` | Admin (incl. solo lectura); en memoria (`BytesIO`) |
| GET | `/cm/reportes/pdf?...` · `/cm/reportes/excel?...` | CM (misma función filtrada por `cm_id`) |

## Jobs (respaldo para cron-job.org)
| Método | Ruta | Notas |
|---|---|---|
| POST | `/api/jobs/run/{nombre}` | header `X-Jobs-Secret` (comparación constante). `aviso_renovacion_y_vencidos` (12:00), `avisos_prorroga` (12:00; 3 días antes y vencidas), `purga_no_renovados` (12:10, elimina clientes con 3 meses en No renovados). Idempotentes vía `dedupe_key`. |
| GET | `/api/health` | UptimeRobot |

APScheduler interno: 12:00 y 12:10 `America/Mexico_City`, además de los endpoints.
