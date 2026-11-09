#!/usr/bin/env python3
"""Registra vibración y temperatura un tiempo y propone umbrales (bloque hardware).

    calibrar.py --segundos 60                          # con la máquina en operación normal
    calibrar.py --segundos 30 --csv falla.csv          # guarda además cada lectura

Solo escucha `andon/e1/lecturas`: no cambia ninguna configuración. Los umbrales propuestos
son un punto de partida; hay que confirmar que una falla real (aspa desbalanceada) los supera.
"""
import argparse
import csv
import os
import statistics
import sys
import time
import uuid
from pathlib import Path

for ruta in ("/opt/andon", str(Path(__file__).resolve().parent.parent / "src")):
    if Path(ruta, "andon").is_dir():
        sys.path.insert(0, ruta)
        break

from andon.common import topicos  # noqa: E402
from andon.common.mqtt import ClienteMqtt  # noqa: E402

MARGEN_VIB = 1.5        # veces el máximo observado en operación normal
MARGEN_TEMP_C = 15.0    # grados sobre el máximo observado
MAX_VIB_G = 4.0         # rango configurado del MPU-6050
MAX_TEMP_C = 125.0


def proponer(vibraciones, temperaturas):
    """Umbrales (vibración en g, temperatura en °C) a partir de la operación normal."""
    return (round(min(max(vibraciones) * MARGEN_VIB, MAX_VIB_G), 3),
            round(min(max(temperaturas) + MARGEN_TEMP_C, MAX_TEMP_C), 1))


def resumen(nombre, valores, unidad):
    print(f"{nombre}: mín {min(valores):.3f} · media {statistics.fmean(valores):.3f} · "
          f"máx {max(valores):.3f} {unidad} ({len(valores)} lecturas)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--segundos", type=float, default=60.0)
    ap.add_argument("--host", default=os.environ.get("ANDON_MQTT_HOST", "127.0.0.1"))
    ap.add_argument("--csv")
    a = ap.parse_args()

    filas = []
    c = ClienteMqtt(a.host, 1883, f"calibrar-{uuid.uuid4().hex[:6]}")
    c.suscribir(topicos.LECTURAS, lambda t, d: filas.append((d.get("ts"), d.get("vib_rms_g"), d.get("temp_c"))))
    c.conectar()
    if not c.esperar_conexion(5):
        print("no se pudo conectar al broker", file=sys.stderr)
        return 1
    print(f"Registrando {a.segundos:.0f} s…")
    time.sleep(a.segundos)
    c.desconectar()

    vib = [f[1] for f in filas if isinstance(f[1], (int, float))]
    temp = [f[2] for f in filas if isinstance(f[2], (int, float))]
    if not vib or not temp:
        print("sin lecturas válidas (¿corre andon-sensores?)", file=sys.stderr)
        return 1
    resumen("Vibración RMS", vib, "g")
    resumen("Temperatura", temp, "°C")
    v, t = proponer(vib, temp)
    print(f"\nPropuesta si esto fue operación normal:\n  vib_rms_g = {v}\n  temp_c = {t}")
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ts", "vib_rms_g", "temp_c"])
            w.writerows(filas)
        print(f"Guardado en {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
