# D18 · Modo híbrido: sensores simulados, LEDs, zumbador y OLED reales

- **Estado:** cerrada (decisión de Diego, 11 nov). **Eduardo: revisar.**
- **Fecha:** 2026-11-11
- **Modifica:** D11 (se agrega un tercer modo) y `docs/guia-hardware.md` §6 (pasa de diseño a implementado)

## Contexto
El equipo no va a comprar el MPU-6050. Sin él, el modo `rpi` hace un paro retenido a los 2 s
(`mpu6050_fallo`, D13). Simular solo la vibración y leer el DS18B20 real se descartó por complejo.
Lo que sí se quiere mostrar físicamente son las **salidas**: torre de luces, zumbador y OLED.

## Decisión
1. **Nuevo modo `hibrido`** (`ANDON_MODO=hibrido`). `hal/hibrido.py` define `HalHibrido`:
   - entradas de `HalSim` (vibración y temperatura, sensores «desconectados», `sim/inyectar`);
   - salidas de `HalRpi` (GPIO de LEDs, zumbador y MOSFET, y OLED por I2C) con los pines de `docs/hardware.md`.
2. El simulador sigue el estado de la máquina: con la máquina detenida no hay vibración, igual que en sim.
3. `Config.entradas_simuladas` vale para `sim` e `hibrido`. Con él, `andon-sensores` se suscribe a
   `sim/inyectar` y `sim/ajustar`, y la web publica `/simulador` y `/defensa`. En `rpi` siguen sin existir.
4. Se activa igual que el modo sim: `sh /opt/andon/modo.sh hibrido` (drop-in de prueba, nunca en la receta, D11).
5. **No cambia el contrato MQTT** ni los invariantes: el paro sigue decidiéndose en `andon-sensores`,
   queda retenido hasta el PIN y el modelo no arranca la máquina.

## Cableado
Ver `docs/guia-hardware.md` §6. Con la placa apagada; los LEDs con 330 Ω; la OLED a 3,3 V (REQ-N07).
El MOSFET y el ventilador (GPIO 17) son opcionales: si se conectan, el ventilador arranca y se detiene
con la máquina, pero no influye en la vibración simulada.

## Addendum (12 nov): pantalla LCD 16x2
La pantalla disponible resultó ser una LCD de caracteres 16x2 (HD44780) con adaptador I2C PCF8574 en 0x27, no
una OLED SSD1306. Se agregó `hal/lcd1602.py` y la opción `[i2c] pantalla = ssd1306 | lcd1602` (la dirección sigue
en `oled`). Las líneas que la estación manda para la OLED se acomodan en 2 filas de 16; sin tildes. El hilo de la
pantalla es el mismo de la OLED: si no responde, se registra y el lazo de seguridad no se entera. El contrato
MQTT no cambia. `andon.conf` de la imagen queda con `pantalla = lcd1602` y `oled = 0x27`.

## Consecuencias
- En la defensa hay que decirlo claro: **los sensores son simulados; las salidas son reales.**
- El paro < 1 s (REQ-N04) se mide desde la lectura simulada que cruza el umbral hasta el LED rojo real.
- Pruebas: `test_hal_hibrido.py` y `test_hal_interfaz.py` (ahora con los tres HAL), más la suscripción
  al panel en `test_sensores.py` y `/simulador` en `test_web.py`.
