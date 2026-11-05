#!/bin/sh
# Prueba de salida de la etapa E3. Se corre DENTRO de la Raspberry Pi:
#   sh probar-ollama.sh
# Verifica que Ollama responde en /v1/systemone sin Internet y mide la latencia.
set -e

echo ">> Servicio:"
systemctl is-active ollama

echo ">> Modelos instalados:"
ollama list

echo ">> Consulta JEV de prueba (CU-03):"
INICIO=$(date +%s%N)
curl -s http://127.0.0.1:11434/v1/systemone \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tev1:0.8b",
    "state": "vibracion_rms_g: 0.12, temp_motor_c: 41. Reporte del operario: olor a quemado cerca del motor",
    "questions": {
      "categoria": {
        "type": "choice",
        "instructions": "¿Qué situación describe el estado de la estación?",
        "criteria": {
          "operacion_normal": "La máquina opera sin anomalías",
          "falla_mecanica": "Vibración, golpes, ruidos metálicos o piezas sueltas",
          "falla_electrica": "Olor a quemado, chispas, cortes o calentamiento eléctrico",
          "problema_calidad": "Piezas defectuosas o fuera de especificación",
          "material_faltante": "Falta de materia prima o componentes"
        }
      }
    }
  }'
FIN=$(date +%s%N)
echo
echo ">> Latencia: $(( (FIN - INICIO) / 1000000 )) ms"
echo "   (la primera consulta incluye cargar el modelo en memoria; repetir para medir la normal)"
