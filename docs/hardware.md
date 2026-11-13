# Hardware de la estación · mapa de pines y notas de conexión

Propuesta de la app (F2). **Diego la confirma al cablear**; todo vive en
`[gpio]` e `[i2c]` de `andon.conf`, así que un cambio de pin no toca el código.
Numeración BCM. Acceso solo con libgpiod v2 (`/dev/gpiochip0`).

## Pines

| Señal | GPIO | Pin físico | Dirección | Nota |
|---|---|---|---|---|
| I2C SDA | 2 | 3 | bus 1 | MPU-6050 (0x68) y pantalla en el mismo bus, a 400 kHz. Pantalla: OLED SSD1306 (0x3C) o LCD 16x2 con PCF8574 (0x27), según `[i2c] pantalla` |
| I2C SCL | 3 | 5 | bus 1 | |
| 1-Wire (DS18B20) | 4 | 7 | w1-gpio | Resistencia de 4,7 kΩ entre datos y 3,3 V |
| MOSFET del ventilador | 17 | 11 | salida | Activo en alto. Resistencia de 10 kΩ de la compuerta a GND |
| LED verde | 22 | 15 | salida | Con resistencia serie |
| LED amarillo | 27 | 13 | salida | Con resistencia serie |
| LED rojo | 23 | 16 | salida | Con resistencia serie |
| Zumbador | 24 | 18 | salida | Activo, activo en alto. Montaje de la demo: GPIO → 1 kΩ → base de un 2N2222; emisor a GND; colector al (−) del zumbador; (+) del zumbador a 5 V |

## Montaje de la demo (12 nov, modo híbrido, D18)

Solo salidas: 3 LEDs, zumbador y LCD. Sin MPU-6050, DS18B20, MOSFET ni ventilador (GPIO 17 y 4 sin conectar).

| Riel de la protoboard | Desde | Alimenta |
|---|---|---|
| + de arriba | 3,3 V (pin 1) | Solo la LCD (así SDA y SCL quedan a 3,3 V, REQ-N07) |
| + de abajo | 5 V (pin 2) | Solo el (+) del zumbador; el GPIO 24 solo ve la base del 2N2222 por 1 kΩ |
| − (los dos, unidos) | GND (pin 6) | Todos los GND |

Pantalla: LCD de caracteres 16x2 (HD44780) con adaptador I2C PCF8574 (placa «MH»), en 0x27. A 3,3 V se lee
bien; el contraste se ajusta con el potenciómetro azul del adaptador. Verificado en la placa el 12 nov
(`docs/evidencias/b8-hibrido-placa-20261112.txt`).

## Reglas de seguridad eléctrica

- **REQ-N07: ningún GPIO recibe más de 3,3 V.** Alimentar el MPU-6050, la OLED y el
  DS18B20 desde el pin de 3,3 V (no de 5 V) para que las líneas I2C y 1-Wire no
  queden a 5 V por los resistores de pull-up de las placas.
- **El ventilador va con su propia fuente.** El MOSFET aísla su corriente del GPIO. Unir
  las tierras (GND) de la fuente del ventilador y de la Raspberry Pi.
- **Diodo de rueda libre** (1N4007 o similar) en antiparalelo con el ventilador, si el
  módulo MOSFET no lo trae.
- **Estado seguro al fallar el software:** la resistencia de 10 kΩ a GND en la compuerta
  mantiene el ventilador detenido cuando el proceso muere o las líneas se liberan
  (libgpiod devuelve los pines a entrada). Al arrancar, `HalRpi` solicita todas las
  líneas como salida **apagada**, y `cerrar()` las deja apagadas.
- Cada LED con su resistencia serie (330 Ω a 1 kΩ con 3,3 V).

## Sensores

| Sensor | Configuración de la app | Observaciones |
|---|---|---|
| MPU-6050 | ±4 g (8192 LSB/g), filtro pasa-bajos de 44 Hz, 1 kHz internos, lectura a 100 Hz; reloj PLL del giroscopio | `WHO_AM_I` debe ser 0x68. Clones que respondan otro valor se rechazan con un mensaje explícito |
| DS18B20 | `/sys/bus/w1/devices/28-*/w1_slave`, con verificación de CRC | Lectura de ~750 ms: se hace en un hilo aparte (F3). Un valor de 85,0 °C se descarta (es el valor de arranque, no una medición) |

## Verificación en la placa

`app/tools/probar_hal.py` (ver `docs/pruebas.md`, «Verificación de periféricos»).
