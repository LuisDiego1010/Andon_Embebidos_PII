# B5 · Corte de corriente · RPi 4, imagen final, modo híbrido, 12 nov 2026

Resultado: ✅ el paro retenido sobrevive al corte, todo arranca solo y `andon.db` queda íntegra.

## Preparación (antes del corte)
- Paro de seguridad por vibración (panel a 2 g y vuelta a 0,1 g): retenido, `paro.json` =
  `{"sensor": "vibracion", "valor": 1.0648…, "umbral": 1.0}`. LED rojo y zumbador reales.
- `andon.db`: 37 eventos, `integrity_check = ok`.
- Carga: un reporte nuevo cada 15 s (09:57:09, 09:57:24, 09:57:39), para cortar con uno en análisis.
- Corte: Diego desconectó la alimentación de la Pi sin apagado ordenado (~10 s) y la reconectó.

## Después del arranque
- `uptime` 1 min: mosquitto, ollama, andon-sensores, andon-core, andon-web, hostapd y dnsmasq `active`;
  ninguna unidad fallida.
- Estado: `paro_seguridad`, vibración 1,06 > 1,00 g; luz roja, zumbador y LCD «PARO vibracion 1.06>1.00».
  Diego lo confirmó en físico: «retomó el estado anterior ROJO y sigue sonando».
- `andon.db`: `integrity_check = ok`, 39 eventos. Los reportes 1 y 2 quedaron registrados (`paro_activo`).
- El reporte 3, enviado ~1 s antes del corte, se perdió: estaba en memoria, en el modelo, y no llegó a la base.
  Comportamiento aceptado: el operario ve «No llegó respuesta a tiempo. Su texto sigue arriba» y lo reenvía.
- El modo híbrido (drop-in de prueba) se mantuvo. El paro se liberó con el PIN: luz verde, «OPERANDO».
