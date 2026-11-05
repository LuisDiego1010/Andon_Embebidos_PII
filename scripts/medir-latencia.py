#!/usr/bin/env python3
"""Mide latencia y exactitud de tev1:0.8b EN LA RASPBERRY PI (REQ-N05, D4).

Usa el mismo cliente (andon.core.ollama) y los mismos 19 reportes que la prueba
de contrato de la PC, para comparar resultados directamente. Solo biblioteca
estándar: corre en la imagen Yocto sin pytest.

    python3 medir-latencia.py                 # 19 reportes, 1 ronda
    python3 medir-latencia.py --rondas 3      # repite para ver la variación
    python3 medir-latencia.py --umbral 0.92   # umbral de confianza a evaluar

Guarda los resultados en latencia-<fecha>.csv (para docs/evidencias/ y la bitácora).
"""
import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

# El código de la app vive en /opt/andon en la imagen, o en app/src en el repo
for ruta in ("/opt/andon", str(Path(__file__).resolve().parent.parent / "app" / "src")):
    if Path(ruta, "andon").is_dir():
        sys.path.insert(0, ruta)
        break

from andon.core import ollama  # noqa: E402

REPORTES_RUTAS = [
    Path("/opt/andon/pruebas/reportes.json"),
    Path(__file__).resolve().parent.parent / "app" / "tests" / "contract" / "reportes.json",
]


def cargar_reportes():
    for p in REPORTES_RUTAS:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8")), p
    sys.exit("No encontré reportes.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:11434")
    ap.add_argument("--modelo", default=ollama.MODELO)
    ap.add_argument("--rondas", type=int, default=1)
    ap.add_argument("--umbral", type=float, default=0.92)
    ap.add_argument("--timeout", type=float, default=120.0)
    a = ap.parse_args()

    reportes, origen = cargar_reportes()
    print(f"Modelo {a.modelo} @ {a.url} · {len(reportes)} reportes ({origen})")

    # Calentamiento: la primera consulta incluye cargar el modelo en memoria
    print("Calentando el modelo (la primera consulta carga los pesos)...")
    t0 = time.monotonic()
    try:
        ollama.clasificar("prueba", url=a.url, modelo=a.modelo, timeout_s=a.timeout)
    except ollama.ErrorOllama as e:
        sys.exit(f"Ollama no respondió: {e}")
    print(f"  carga + primera consulta: {time.monotonic() - t0:.1f} s\n")

    filas = []
    for ronda in range(1, a.rondas + 1):
        for r in reportes:
            try:
                res = ollama.clasificar(r["texto"], r["vib_rms_g"], r["temp_c"],
                                        url=a.url, modelo=a.modelo, timeout_s=a.timeout)
                filas.append(dict(ronda=ronda, id=r["id"], esperada=r["esperada"] or "(ambiguo)",
                                  obtenida=res.categoria, prob=round(res.prob, 3),
                                  conf=round(res.confianza, 3), ms=res.latencia_ms,
                                  ambiguo=r["ambiguo"], error=""))
            except ollama.ErrorOllama as e:
                filas.append(dict(ronda=ronda, id=r["id"], esperada=r["esperada"] or "(ambiguo)",
                                  obtenida="ERROR", prob=0, conf=0, ms=0,
                                  ambiguo=r["ambiguo"], error=str(e)))
            f = filas[-1]
            print(f"r{ronda} {f['id']:>2} {f['esperada']:<18} {f['obtenida']:<18} "
                  f"{f['prob']:5.2f} {f['ms']:6d} ms {f['error']}", flush=True)

    ok = [f for f in filas if f["obtenida"] != "ERROR"]
    claros = [f for f in ok if not f["ambiguo"]]
    amb = [f for f in ok if f["ambiguo"]]
    lat = sorted(f["ms"] for f in ok)
    aciertos = sum(f["esperada"] == f["obtenida"] for f in claros)

    print("\n== Resultados en la placa")
    if lat:
        p90 = lat[min(len(lat) - 1, int(0.9 * len(lat)))]
        print(f"Latencia: mín {lat[0]} ms · mediana {statistics.median(lat):.0f} ms · "
              f"p90 {p90} ms · máx {lat[-1]} ms")
        print(f"REQ-N05 (meta ≤ 3000 ms): {'CUMPLE' if statistics.median(lat) <= 3000 else 'NO CUMPLE'} "
              f"por mediana")
    if claros:
        print(f"Exactitud en reportes claros: {aciertos}/{len(claros)} = {aciertos / len(claros):.0%}")
        claros_amarillo = sum(f["prob"] < a.umbral for f in claros)
        print(f"Umbral {a.umbral}: {claros_amarillo}/{len(claros)} claros irían a amarillo (falsa revisión)")
    if amb:
        amb_amarillo = sum(f["prob"] < a.umbral for f in amb)
        print(f"Umbral {a.umbral}: {amb_amarillo}/{len(amb)} ambiguos irían a amarillo (CU-05 correcto)")
    errores = len(filas) - len(ok)
    if errores:
        print(f"Errores: {errores} (timeout {a.timeout} s)")

    salida = Path(f"latencia-{time.strftime('%Y%m%d-%H%M%S')}.csv")
    with salida.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    print(f"\nCSV guardado en {salida.resolve()}")


if __name__ == "__main__":
    main()
