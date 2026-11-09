# Guía para cuando llegue el hardware

Todo lo que no depende de sensores se prueba antes con `probar_sin_hardware.py`. Esta guía cubre
solo lo que queda. **Antes de conectar nada: placa apagada y `docs/hardware.md` a mano.**

## 1. Antes de energizar
- [ ] Sensores y OLED alimentados desde **3,3 V**, nunca 5 V (REQ-N07).
- [ ] Multímetro: ningún pin de señal por encima de 3,3 V.
- [ ] Compuerta del MOSFET con 10 kΩ a GND. Ventilador con fuente propia, GND común y diodo.
- [ ] LED con resistencia en serie. DS18B20 con 4,7 kΩ entre datos y 3,3 V.

## 2. Comprobar cada periférico, en este orden (en la placa)
```bash
systemctl stop andon-sensores               # libera GPIO e I2C
i2cdetect -y 1                              # esperado: 68 (MPU-6050) y 3c (OLED)
ls /sys/bus/w1/devices/                     # esperado: una carpeta 28-*
python3 /opt/andon/probar_hal.py            # sensores
python3 /opt/andon/probar_hal.py --salidas  # el ventilador gira un instante
```
Si el MPU-6050 sale con `WHO_AM_I` distinto de 0x68, es un clon: la app lo rechaza a propósito,
porque otros chips configuran el filtro con registros distintos. Hay que cambiar el módulo o
adaptar `hal/rpi.py`.

## 3. Estado seguro
Con el ventilador conectado: `systemctl start andon-sensores`, y después `systemctl kill -s KILL
andon-sensores`. El ventilador debe detenerse solo.

## 4. Calibrar
Los umbrales actuales (1,0 g y 60 °C) son provisionales.
```bash
python3 /opt/andon/calibrar.py --segundos 60 --csv normal.csv   # operación normal
python3 /opt/andon/calibrar.py --segundos 30 --csv falla.csv    # con el aspa desbalanceada
```
La vibración con falla tiene que superar claramente el umbral propuesto. Cargarlo en
`http://<placa>:5000/supervisor`.

## 5. Casos con hardware real
| Caso | Qué hacer | Esperado |
|---|---|---|
| CU-01 | Encender | Luz verde, ventilador girando, lecturas reales en `/tablero` |
| CU-02 vibración | Desbalancear el aspa | Paro < 1 s, luz roja, zumbador; medir en video (REQ-N04) |
| CU-02 temperatura | Calentar el DS18B20 | Paro al superar el umbral |
| D13 | Desconectar un sensor en marcha | Paro en ≈ 2 s con `*_fallo` |
| CU-03, 04, 05 | Reportes desde el celular | Igual que en sim, con torre y OLED reales |
| CU-06, CU-07 | `/supervisor` | Reinicio con PIN; umbral aplicado sin reiniciar |
| REQ-N06 | Quitar y dar corriente | Todo arranca solo |

La OLED nunca se probó en una pantalla real: si no se ve, revisar con `i2cdetect` y mirar el
registro `OLED ... no responde`. Una OLED dañada no afecta al paro.
