"""Tópicos MQTT del contrato (CLAUDE.md › Contrato MQTT). Payload siempre JSON.

Cualquier cambio aquí se consulta primero y se refleja en CLAUDE.md.
"""

PREFIJO = "andon/e1/"

LECTURAS = PREFIJO + "lecturas"        # sensores -> *        ts, vib_rms_g, temp_c
SEGURIDAD = PREFIJO + "seguridad"      # sensores -> core,web (retenido)
CMD_MAQUINA = PREFIJO + "cmd/maquina"  # core,web -> sensores  accion: parar|reiniciar
CMD_SENAL = PREFIJO + "cmd/senal"      # core -> sensores      luz, zumbador, oled
REPORTE = PREFIJO + "reporte"          # web -> core           id, texto, ts_navegador
EVENTO = PREFIJO + "evento"            # core -> público
ESTADO = PREFIJO + "estado"            # core -> web (retenido)
CMD_RECARGAR = PREFIJO + "cmd/recargar"  # web -> *
SIM_INYECTAR = PREFIJO + "sim/inyectar"  # pruebas -> sensores (solo modo sim)

RETENIDOS = frozenset({SEGURIDAD, ESTADO})

LUCES = ("verde", "amarilla", "roja")
ACCIONES_MAQUINA = ("parar", "reiniciar")
