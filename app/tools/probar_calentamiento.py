#!/usr/bin/env python3
"""Mide en la placa el calentamiento del modelo y la latencia ya caliente (D4, REQ-N05).

    python3 probar_calentamiento.py              # calienta y hace 3 consultas
    python3 probar_calentamiento.py --descargar  # antes descarga el modelo de la memoria

--descargar fuerza la carga en frío (keep_alive=0) para ver el costo real del
calentamiento. Solo biblioteca estándar.
"""
import argparse
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

for ruta in ("/opt/andon", str(Path(__file__).resolve().parent.parent / "src")):
    if Path(ruta, "andon").is_dir():
        sys.path.insert(0, ruta)
        break

from andon.core import ollama  # noqa: E402


def descargar(url, modelo):
    """Pide a Ollama sacar el modelo de la memoria (la siguiente consulta carga en frío)."""
    req = urllib.request.Request(
        url.rstrip("/") + "/api/generate",
        data=json.dumps({"model": modelo, "keep_alive": 0}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=30).read()
    time.sleep(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:11434")
    ap.add_argument("--modelo", default=ollama.MODELO)
    ap.add_argument("--consultas", type=int, default=3)
    ap.add_argument("--descargar", action="store_true")
    a = ap.parse_args()

    if a.descargar:
        print("Descargando el modelo de la memoria...")
        descargar(a.url, a.modelo)

    print("Calentando...")
    seg = ollama.calentar(a.url, a.modelo)
    if seg is None:
        sys.exit("El calentamiento falló (ver mensaje de log)")
    print(f"  calentamiento: {seg:.1f} s")

    lat = []
    for i in range(a.consultas):
        r = ollama.clasificar("Se escucha un ruido metálico fuerte en el ventilador",
                              0.9, 42.0, url=a.url, modelo=a.modelo)
        lat.append(r.latencia_ms)
        print(f"  consulta {i + 1}: {r.latencia_ms} ms -> {r.categoria} ({r.prob:.2f})")
    print(f"Mediana ya caliente: {statistics.median(lat):.0f} ms")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
