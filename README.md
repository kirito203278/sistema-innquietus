# INNquietus · Plataforma

Una sola plataforma para la agencia que **junta en un mismo sistema** lo que antes eran dos:

- **Clientes, paquetes y pagos** (ciclos de 30 días, prórrogas, renovaciones, ingresos, reportes PDF/Excel).
- **Campañas** (captura semanal, semáforo de rendimiento, resultados mensuales, reportes para el cliente).

Un solo acceso, un solo menú según tu rol, una sola base de datos y **una sola ficha por cliente**: de la ficha
del cliente se llega a sus campañas y de cada campaña se regresa a su cliente. Detalle de cómo se unió todo en
[`docs/INTEGRACION.md`](docs/INTEGRACION.md).

## Probarlo en tu computadora

Solo necesitas **Docker**. Sin crear archivos, sin configurar nada:

```bash
docker compose -f docker-compose.demo.yml up --build
```

La primera vez tarda unos minutos (compila la interfaz). Cuando veas `Uvicorn running`, abre **http://localhost:8000**.
Se crean solas las tablas y datos de ejemplo ficticios: 33 clientes y 22 campañas (las campañas cuelgan de los mismos clientes).

| Usuario | Contraseña | Rol |
|---|---|---|
| `admin.demo` | `10000001` | administrador |
| `lectura.demo` | `10000002` | administrador de solo lectura |
| `ana.ruiz` | `10000003` | CM |
| `beto.luna` | `10000004` | CM |
| `carla.soto` | `10000005` | CM |

## Qué ve cada rol

| Pantalla | CM | Admin | Admin solo lectura |
|---|:-:|:-:|:-:|
| **Inicio** (lo urgente de todos los módulos) | ✔ | ✔ | ✔ |
| **Cartera / ficha del cliente** (datos, paquetes y campañas) | la suya | todas | todas |
| **Campañas** (captura semanal, semáforo, resultados) | las suyas | todas | todas (lectura) |
| **Renovaciones** y **No renovados** | ✔ | ✔ | ✔ |
| **Ingresos**, **Reportes**, pagos y prórrogas | — | ✔ | ✔ (lectura) |
| **Equipo**, **Catálogos** (incl. umbrales del semáforo), **Bitácora** | — | ✔ | ✔ (lectura) |

El dinero de los paquetes (costos, pagos, ingresos) es del administrador: el servidor no se lo envía al CM.
El presupuesto y el gasto **publicitario** de las campañas sí lo ve el CM que las lleva.

## Documentación
- [`docs/INTEGRACION.md`](docs/INTEGRACION.md): cómo se unieron los dos sistemas, reglas nuevas, conflictos resueltos, qué cambió.
- [`COMO_EJECUTAR.md`](COMO_EJECUTAR.md): desarrollo, pruebas y **cómo pasar tus datos actuales a la plataforma**.
- [`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md): producción.
