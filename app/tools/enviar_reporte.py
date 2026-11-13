#!/usr/bin/env python3
"""Envía un reporte del operario por MQTT y muestra el evento que publica andon-core.

    enviar_reporte.py "Salen chispas del cable" [--host H] [--espera-s 60]

Hace de «web» mínima para probar CU-03/04/05 sin navegador. Con --reiniciar publica además
`cmd/maquina reiniciar` (origen web, sin PIN: solo para pruebas) y espera el estado `reposo`.
"""
import argparse
import json
import os
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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("texto")
    ap.add_argument("--host", default=os.environ.get("ANDON_MQTT_HOST", "localhost"))
    ap.add_argument("--espera-s", type=float, default=60.0)
    ap.add_argument("--reiniciar", action="store_true")
    a = ap.parse_args()

    eventos, estados = [], []
    c = ClienteMqtt(a.host, 1883, f"enviar-{uuid.uuid4().hex[:6]}")
    c.suscribir(topicos.EVENTO, lambda t, d: eventos.append(d))
    c.suscribir(topicos.ESTADO, lambda t, d: estados.append(d["estado"]))
    c.conectar()
    if not c.esperar_conexion(5):
        print("no se pudo conectar al broker", file=sys.stderr)
        return 1
    time.sleep(0.3)
    t0 = time.monotonic()
    c.publicar(topicos.REPORTE, {"id": uuid.uuid4().hex[:8], "texto": a.texto,
                                 "ts_navegador": time.time()})
    while not eventos and time.monotonic() - t0 < a.espera_s:
        time.sleep(0.05)
    if not eventos:
        print(f"sin evento en {a.espera_s} s (¿corre andon-core?)", file=sys.stderr)
        return 1
    print(json.dumps(eventos[-1], ensure_ascii=False, indent=2))
    print(f"→ evento en {time.monotonic() - t0:.1f} s · estado: {estados[-1] if estados else '?'}")
    if a.reiniciar:
        c.publicar(topicos.CMD_MAQUINA, {"accion": "reiniciar", "origen": "web"})
        t1 = time.monotonic()
        while time.monotonic() - t1 < 5 and (not estados or estados[-1] != "reposo"):
            time.sleep(0.05)
        print(f"→ tras reiniciar: estado {estados[-1]}")
    c.desconectar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
