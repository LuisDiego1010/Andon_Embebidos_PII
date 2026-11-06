#!/usr/bin/env python3
"""Inyector de fallas para el modo sim (publica en andon/e1/sim/inyectar).

    inyector.py --vib-g 2.0 --duracion-s 5            # vibración desbalanceada 5 s
    inyector.py --temp-c 90 --duracion-s 5            # sobrecalentamiento
    inyector.py --vib-g 2.0 --esperar-paro            # además mide inyección → paro
    inyector.py --reiniciar                           # cmd/maquina reiniciar (origen web)

El tópico sim/inyectar solo existe si andon-sensores corre con ANDON_MODO=sim; en la
placa con hardware real se ignora. `--reiniciar` salta el PIN: es solo para pruebas
(en producción lo publica andon-web tras validar el PIN, CU-06).
Host MQTT: --host o ANDON_MQTT_HOST (por defecto localhost).
"""
import argparse
import os
import sys
import time
from pathlib import Path

for ruta in ("/opt/andon", str(Path(__file__).resolve().parent.parent / "src")):
    if Path(ruta, "andon").is_dir():
        sys.path.insert(0, ruta)
        break

from andon.common import topicos  # noqa: E402
from andon.common.mqtt import ClienteMqtt  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default=os.environ.get("ANDON_MQTT_HOST", "localhost"))
    ap.add_argument("--puerto", type=int, default=int(os.environ.get("ANDON_MQTT_PUERTO", "1883")))
    ap.add_argument("--vib-g", type=float)
    ap.add_argument("--temp-c", type=float)
    ap.add_argument("--duracion-s", type=float, default=5.0)
    ap.add_argument("--esperar-paro", action="store_true", help="mide el tiempo hasta el aviso de paro")
    ap.add_argument("--reiniciar", action="store_true")
    a = ap.parse_args()
    if not a.reiniciar and a.vib_g is None and a.temp_c is None:
        ap.error("indique --vib-g, --temp-c o --reiniciar")

    llegadas = []   # (instante, mensaje) de `seguridad`
    c = ClienteMqtt(a.host, a.puerto, f"inyector-{os.getpid()}")
    c.suscribir(topicos.SEGURIDAD, lambda t, d: llegadas.append((time.monotonic(), d)))
    c.conectar()
    if not c.esperar_conexion(5):
        sys.exit(f"No hay broker MQTT en {a.host}:{a.puerto}")
    time.sleep(0.3)   # deja llegar el estado retenido de `seguridad`
    previo = llegadas[-1][1] if llegadas else None

    t0 = time.monotonic()
    if a.reiniciar:
        c.publicar(topicos.CMD_MAQUINA, {"accion": "reiniciar", "origen": "web"})
        print("reinicio solicitado (origen web)")
    else:
        carga = {"duracion_s": a.duracion_s}
        if a.vib_g is not None:
            carga["vib_g"] = a.vib_g
        if a.temp_c is not None:
            carga["temp_c"] = a.temp_c
        c.publicar(topicos.SIM_INYECTAR, carga)
        print(f"falla inyectada: {carga}")

    if a.esperar_paro and not a.reiniciar:
        fin = time.monotonic() + 5
        while time.monotonic() < fin:
            nuevos = [(t, m) for t, m in llegadas if t >= t0 and m.get("activo")]
            if nuevos:
                t, m = nuevos[0]
                print(f"PARO: {(t - t0) * 1000:.0f} ms desde la inyección → {m['sensor']} "
                      f"valor={m['valor']} umbral={m['umbral']}")
                break
            time.sleep(0.005)
        else:
            estado = "ya estaba en paro" if previo and previo.get("activo") else "sin aviso de paro"
            print(f"No llegó un aviso de paro en 5 s ({estado}). ¿Está andon-sensores en modo sim?")
            c.desconectar()
            sys.exit(1)
    time.sleep(0.2)
    c.desconectar()


if __name__ == "__main__":
    main()
