#!/usr/bin/env python3
"""Prueba rápida de la capa de hardware EN LA PLACA (F2 🔌). Solo lectura por defecto.

    python3 probar_hal.py                 # abre GPIO e I2C y lee los sensores
    python3 probar_hal.py --salidas       # además enciende cada salida 0,4 s
    python3 probar_hal.py --conf ruta     # otra configuración (por defecto ANDON_CONF)

Sin sensores conectados, MPU-6050 y DS18B20 salen como [AVISO], no como fallo.
--salidas mueve los pines de la máquina (MOSFET), las luces y el zumbador: con el
ventilador conectado girará un instante; sin nada conectado es inocuo.
Termina con código 1 solo si hay [FALLO] (no se pudo abrir GPIO/I2C, error de escritura).
"""
import argparse
import sys
import time
from pathlib import Path

# El código vive en /opt/andon en la imagen, o en app/src en el repositorio
for ruta in ("/opt/andon", str(Path(__file__).resolve().parent.parent / "src")):
    if Path(ruta, "andon").is_dir():
        sys.path.insert(0, ruta)
        break

from andon.common.config import ErrorConfig, cargar  # noqa: E402
from andon.hal.base import ErrorHardware  # noqa: E402
from andon.hal.rpi import HalRpi  # noqa: E402

ok = fallo = aviso = 0


def bien(m):
    global ok
    ok += 1
    print(f"  [OK]    {m}")


def mal(m):
    global fallo
    fallo += 1
    print(f"  [FALLO] {m}")


def avisar(m):
    global aviso
    aviso += 1
    print(f"  [AVISO] {m}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--conf")
    ap.add_argument("--salidas", action="store_true")
    a = ap.parse_args()

    try:
        cfg = cargar(a.conf)
    except ErrorConfig as e:
        sys.exit(f"Configuración inválida: {e}")
    g = cfg.gpio
    print(f"Chip {g.chip} · pines máquina={g.maquina} verde={g.verde} amarilla={g.amarilla} "
          f"roja={g.roja} zumbador={g.zumbador} · I2C bus {cfg.i2c.bus}")

    print("\n== Apertura")
    try:
        hal = HalRpi(cfg)
    except ErrorHardware as e:
        mal(str(e))
        print(f"\n== Resumen: {ok} OK · {fallo} fallos · {aviso} avisos")
        sys.exit(1)
    bien("líneas GPIO solicitadas como salidas apagadas (libgpiod v2)")
    bien(f"bus I2C {cfg.i2c.bus} abierto")

    try:
        print("\n== Sensores")
        for nombre, (bueno, detalle) in hal.verificar_sensores().items():
            (bien if bueno else avisar)(f"{nombre}: {detalle}" + ("" if bueno else " (¿sin conectar?)"))

        if a.salidas:
            print("\n== Salidas (0,4 s cada una)")
            pruebas = [("máquina (MOSFET)", hal.set_maquina, True, False),
                       ("luz verde", hal.set_luz, "verde", None),
                       ("luz amarilla", hal.set_luz, "amarilla", None),
                       ("luz roja", hal.set_luz, "roja", None),
                       ("zumbador", hal.set_zumbador, True, False)]
            for nombre, fn, on, off in pruebas:
                try:
                    fn(on)
                    time.sleep(0.4)
                    fn(off)
                    bien(f"{nombre}: encendida y apagada sin error")
                except ErrorHardware as e:
                    mal(f"{nombre}: {e}")
        else:
            print("\n(Salidas no probadas: use --salidas)")
    finally:
        try:
            hal.cerrar()
            bien("cerrar(): salidas en reposo y recursos liberados")
        except ErrorHardware as e:
            mal(f"cerrar(): {e}")

    print(f"\n== Resumen: {ok} OK · {fallo} fallos · {aviso} avisos")
    sys.exit(1 if fallo else 0)


if __name__ == "__main__":
    main()
