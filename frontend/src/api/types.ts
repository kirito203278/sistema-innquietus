export interface Usuario {
  id: number; nombre: string; username: string; rol: 'cm' | 'admin'; solo_lectura: boolean; activo: boolean
}
export interface LoginResponse { access_token: string; usuario: Usuario }

export type Semaforo = 'verde' | 'amarillo' | 'rojo' | 'gris'
export type EstadoPaquete = 'activo' | 'por_vencer' | 'vencido' | 'renovado' | 'archivado' | 'eliminado'

export interface Paquete {
  id: number; cliente_id: number; paquete_id: number; paquete: string; tipo_id: number; tipo: string
  costo: number; pagado: number; restante: number; avance_pct: number
  fecha_inicio: string; fecha_renovacion: string; quincena: 1 | 2; dias_para_renovar: number
  estado: string; estado_efectivo: EstadoPaquete
  renovacion_decision: 'pendiente' | 'si' | 'no'; renovacion_pagada: boolean; semaforo: Semaforo
  prorroga_hasta: string | null; prorroga_registrada_en: string | null; prorroga_dias_restantes: number | null
  prorroga_activa: boolean; prorroga_vencida: boolean
  bloqueado: boolean; opciones_bloqueo: ('renovo' | 'va_a_renovar' | 'no_renovo' | 'prorroga')[]; limite_decision: string | null
  no_renovara: boolean; confirmo_renovacion: boolean; gracia_hasta: string | null; gracia_activa: boolean; confirmado_en: string | null
  renovara_con: { paquete_id: number; tipo_id: number; costo: number } | null
  ciclo_anterior_id: number | null; archivado_en: string | null
}
export interface Pago {
  id: number; monto: number; fecha: string; nota: string | null; registrado_por: number
  registrado_por_nombre: string | null; creado_en: string
}
export interface Bloqueo extends Paquete { cliente_nombre: string; cm_id: number | null }
export interface PaqueteDetalle extends Paquete {
  veces_renovado: number; pagos: Pago[]; ciclos: Paquete[]
  renovaciones: { id: number; fecha: string; costo_anterior: number; costo_nuevo: number
    paquete_anterior_id: number; paquete_nuevo_id: number; ciclo_anterior_id: number; ciclo_nuevo_id: number }[]
}

export interface ClienteListItem {
  id: number; nombre: string; estado: 'activo' | 'no_renovado'; cm_id: number | null; cm_nombre: string | null
  telefono: string | null; paquetes_vigentes: number; pendiente_decision: boolean; semaforo: Semaforo | null; quincenas: number[]
  proxima_renovacion: string | null
}
export interface ClienteFicha {
  id: number; nombre: string; estado: 'activo' | 'no_renovado'; cm_id: number | null
  correo_fb: string | null; tiene_password_fb: boolean; cuenta_compartida_con: { id: number; nombre: string }[]; correo_contacto: string | null
  telefono: string | null; observaciones: string | null
  tipo_cuenta: string | null; metodo_pago: string | null; forma_pago: string | null
  campanas: Campana[]
  paquetes: Paquete[]; historial: Paquete[]; no_renovado_desde: string | null
}

// ---- Campañas (módulo unificado: cuelgan del mismo cliente) ----
export type Rendimiento = 'bueno' | 'regular' | 'bajo'
export type EstadoCampana = 'activa' | 'vencida' | 'cerrada'
export interface Campana {
  id: number; cliente_id: number; cliente_nombre: string; cliente_estado: 'activo' | 'no_renovado'
  cm_id: number | null; cm_nombre: string | null; paquete_cliente_id: number | null; paquete: string | null
  nombre: string; tipo: 'local' | 'nacional' | 'otro'; presupuesto: number; presupuesto_esquema: string
  formato_post: boolean; formato_3d: boolean; formato_boton: boolean; formato_otro: boolean; lugar: string | null
  fecha_inicio: string; fecha_renovacion: string; dias_para_renovar: number
  estado: EstadoCampana; costo_actual: number | null; rendimiento: Rendimiento | null
  cliente_bloqueado?: boolean
}
export interface SemanaCampana {
  id: number; campana_id: number; inicio: string; fin: string; mensajes: number | null
  costo_por_resultado: number | null; importe_gastado: number | null
  editable: boolean; permiso_hasta: string | null; en_curso: boolean; rendimiento: Rendimiento | null
}
export interface MensualCampana {
  id: number; campana_id: number; periodo_inicio: string; periodo_fin: string; mensajes_total: number
  gasto_total: number; costo_por_mensaje: number; presupuesto: number; sobrante: number | null
  rendimiento: Rendimiento | null; origen: 'manual' | 'calculado'
}
export interface ObservacionCampana { id: number; texto: string; autor: string | null; creado_en: string }
export interface MetricaCampana {
  id: number; tipo: string; paquete: string | null; umbral_bueno: number; umbral_regular: number; caida_mensajes_alerta_pct: number
}
export interface CatalogoItem { id: number; nombre: string; orden: number; activo: boolean; costo?: number }

export interface Recordatorio {
  id: number; paquete_id: number; texto: string; wa_url: string | null; telefono: string | null
  generado_en: string; enviado_en: string | null
}
export interface Notificacion {
  id: number; tipo: string; mensaje: string; cliente_id: number | null; paquete_id: number | null
  requiere_respuesta: boolean; respuesta: 'si' | 'no' | null; respondida_en: string | null; leida: boolean; creado_en: string
}
export interface NotificacionesResp { no_leidas: number; preguntas_pendientes: number; items: Notificacion[] }

export interface TarjetaTablero extends Paquete {
  cliente_nombre: string; cm_id: number | null; cm_nombre: string | null; arrastrado: boolean
}
export interface Tablero {
  periodo: { anio: number; mes: number; quincena: string; desde: string; hasta: string; etiqueta: string }
  columnas: { por_vencer: TarjetaTablero[]; en_prorroga: TarjetaTablero[]; vencidos: TarjetaTablero[]
    renovados_sin_pago: TarjetaTablero[]; completos: TarjetaTablero[] }
  en_plazo: number
}

export interface PeriodoInfo {
  anio: number; mes: number; quincena: string; desde: string; hasta: string; corte: string; cerrado: boolean
  etiqueta: string; estado_texto: string
}
export interface Totales { proyeccion: number; cobrado: number; pendiente: number; pct_cobrado: number; clientes: number; paquetes: number }
export interface FilaCM {
  cm_id: number | null; cm: string; clientes: number; paquetes: number; proyeccion: number; cobrado: number
  pendiente: number; pct_cobrado: number
}
export interface FilaTasa { cm_id: number | null; cm: string; vencidos: number; renovados: number; tasa: number }
export interface IngresosResp {
  periodo: PeriodoInfo; totales: Totales
  clientes: { cliente_id: number; cliente: string; cm: string; paquetes: number; proyeccion: number; actual: number; pendiente: number; pct_cobrado: number }[]
  por_cm?: FilaCM[]; total_general?: FilaCM; tasa_renovacion?: FilaTasa[]
  tasa_total: { vencidos: number; renovados: number; tasa: number }
}
export interface FilaDetalle {
  paquete_id: number; cliente_id: number; cm_id: number | null; cm: string; cliente: string; paquete: string; tipo: string
  costo: number; pagado: number; restante: number; fecha_renovacion: string; estado: string; estado_efectivo: EstadoPaquete
  semaforo: Semaforo; decision: string
}
export interface ReporteDatos {
  periodo: PeriodoInfo; resumen: Totales; por_cm: FilaCM[]; total_cm: FilaCM; detalle: FilaDetalle[]
  prorrogas: { cm: string; cliente: string; paquete: string; tipo: string; costo: number; pagado: number; restante: number
    fecha_limite: string; dias: number; vencida: boolean }[]
  pendientes: Record<'por_vencer' | 'vencidos' | 'renovados_sin_pago', { cm: string; items: FilaDetalle[] }[]>
  tasa_renovacion: FilaTasa[]; tasa_total: { vencidos: number; renovados: number; tasa: number }; alcance: string
}

export interface UsuarioEquipo extends Usuario { creado_en: string; clientes_activos: number; clientes_no_renovados: number }
export interface BitacoraItem { id: number; usuario: string; accion: string; detalle: Record<string, unknown> | null; creado_en: string }
