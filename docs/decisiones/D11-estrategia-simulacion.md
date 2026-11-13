# D11 · Desarrollo y pruebas con sensores simulados

- **Estado:** cerrada (aprobada por el usuario)
- **Fecha:** 2026-11-06

## Contexto
El hardware (sensores, torre de luces, zumbador, ventilador) no tiene fecha de llegada, y
la placa es un préstamo disponible solo entre semana. F3 a F6 son la mayor parte de la
app y no pueden esperar. La capa de hardware ya aísla todo: `hal/sim.py` y `hal/rpi.py`
pasan las mismas pruebas (D6, F2).

## Decisión
1. **Se desarrolla la app completa en simulación** (`ANDON_MODO=sim`). El paso a hardware
   es cambiar a `rpi`, calibrar umbrales y confirmar pines, sin tocar código.
2. **Rebanada completa antes que profundidad.** Primero un esqueleto de extremo a
   extremo (sensores simulados → MQTT → core con Ollama → evento → formulario mínimo) y
   después se profundiza cada servicio, para probar un CU entero lo antes posible.
3. **Nuevo nivel de prueba 3b: la Raspberry Pi en modo sim.** Corre la app completa con el
   Ollama real y las unidades systemd de la imagen de Diego; el simulador reemplaza solo
   al hardware. Valida systemd, el arranque automático (REQ-N06), la latencia real y la
   **contención de CPU**: mientras Ollama calcula (~17 s con los 4 núcleos), el lazo de
   100 Hz debe seguir deteniendo la máquina en menos de 1 s (REQ-N04). Si se retrasa, las
   soluciones son prioridad `Nice` y afinidad de núcleo para `andon-sensores`, o limitar los
   hilos de Ollama.
4. *(Recortado el 10 nov, ver D17: el 3b con la imagen Yocto real ya cubre lo que validaba.)*
   **QEMU con Debian arm64 (nivel 3) queda como respaldo** para cuando no haya placa
   (fines de semana). Valida systemd e instalador; no latencia ni hardware.
5. **`tools/fake_ollama.py` se adelanta de F6 a F4**: lo necesitan las pruebas
   deterministas del core.
6. **Las tareas 🔌 de F2, F3 y F4 pasan a un «bloque hardware» sin fecha** y no bloquean el
   cierre de F3 a F6 en simulación.
7. **`docs/pruebas.md` lleva dos columnas por requisito: «simulación» y «hardware»**, para
   no dar por probado lo que solo se simuló. REQ-N04 y REQ-N05 se cierran solo con medición
   en la placa.

## Modo sim seguro
`sim/inyectar` permite inyectar una vibración falsa; no puede llegar a producción:
- El modo por defecto es `rpi`.
- `sim/inyectar` se ignora fuera del modo sim (con prueba unitaria que lo verifica).
- En la placa, el modo sim se activa con un *drop-in* de systemd de prueba
  (`/etc/systemd/system/andon-sensores.service.d/`), **nunca en la receta**.

## Lo que la simulación no valida
| Pendiente | Motivo |
|---|---|
| Umbrales de vibración y temperatura (hoy 1,0 g y 60 °C, provisionales) | Solo se calibran con el ventilador real |
| Paro < 1 s sobre sensores reales (REQ-N04) | La lectura I2C real tiene su propio jitter |
| Pines, cableado y estado seguro del MOSFET | Es eléctrico |
| Comportamiento del modelo con las lecturas reales | Ya se validó el texto, no las lecturas |

## Consecuencias
- Desviación de `docs/plan.md` (orden de tareas, no de alcance): reflejada en el plan.
- Riesgo: falsa confianza. Se mitiga con la tabla simulación/hardware.
- Calendario ajustado: F3–F6 en tres días. Orden de recortes sin cambios.
