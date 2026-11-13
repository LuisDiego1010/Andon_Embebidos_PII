# D17 · Se recorta el nivel 3 (QEMU con Debian arm64)

- **Estado:** cerrada (aprobada por el usuario)
- **Fecha:** 2026-11-10
- **Modifica:** D11, punto 4

## Contexto
D11 dejó QEMU con Debian arm64 (nivel 3) como respaldo sin placa: validar systemd, el instalador
y el flujo completo con `tools/fake_ollama.py`. Nunca se llegó a montar. Desde el 9 nov la imagen
Yocto real arranca los tres servicios en la RPi 4 (8,6 s, H1 resuelto), el nivel 3b corrió con el
modelo real y `/defensa` dio 10 de 10. Diego descartó una imagen `qemuarm64` (`yocto-respuestas.md`, pregunta 6).
El plazo vence el viernes 13.

## Decisión
1. **No se usa `qemu-system` (nivel 3).** Lo que iba a validar ya está probado en la placa, con la imagen real.
2. **El nivel 2 se mantiene:** Docker `--platform linux/arm64` sigue usando la emulación de usuario
   (`qemu-user-binfmt`) para la compatibilidad aarch64.
3. **`config/andon-qemu.conf` no se crea.**
4. **`make install` pasa a opcional:** sin Raspberry Pi OS ni QEMU, su único consumidor sería la receta, y la
   receta `andon-app` ya instala sin él.
5. **`oeqa` queda opcional** y, si se hace, se ejecuta contra la placa (`TEST_TARGET = "simpleremote"`), no en QEMU.
   Es terreno de Diego.

## Respaldo sin placa
- `scripts/simulador-pc.sh`: la estación completa en un contenedor de la PC, con Ollama falso.
- Docker, niveles 1 y 2, y las pruebas unitarias.
- Evidencias de la placa ya registradas en `docs/evidencias/`.

## Consecuencias
- Sin placa no hay prueba de sistema completo con systemd. Se acepta: la placa ya lo demostró, y
  cualquier cambio de `app/` se valida en el siguiente día con placa.
- El tiempo liberado va a lo pendiente en la placa: corte de corriente (REQ-N06), red para la demo,
  evidencia completa de `probar_sin_hardware.py` e imagen final.
