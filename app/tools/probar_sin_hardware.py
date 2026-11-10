#!/usr/bin/env python3
"""Prueba EN LA PLACA todo lo que no necesita sensores. Correr como root.

    python3 /opt/andon/probar_sin_hardware.py                # todo y deja la placa como estaba
    python3 /opt/andon/probar_sin_hardware.py --dejar-sim    # termina en modo sim, para usar el navegador
    python3 /opt/andon/probar_sin_hardware.py --solo-sim     # salta la parte de modo real

Parte 1, modo real sin sensores: servicios, permisos, libgpiod real y paro por sensor ausente (D13).
Parte 2, modo sim con el Ollama real: CU-01 a CU-07 por la API de la web y escenarios de falla.

Reinicia servicios y borra paro.json. Mientras corre, activa temporalmente el modo sim con un
drop-in y cambia umbrales: al terminar, incluso si falla, restaura la configuración.
Termina con código 1 si hay algún [FALLO].
"""
import argparse
import configparser
import json
import os
import pwd
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

CONF = os.environ.get("ANDON_CONF", "/etc/andon/andon.conf")
_SYSTEMD = os.environ.get("ANDON_PRUEBA_DROPIN", "/etc/systemd/system")
DROPINS = tuple(os.path.join(_SYSTEMD, f"{s}.service.d", "sim.conf") for s in ("andon-sensores", "andon-web"))
WEB = "http://127.0.0.1:5000"
SERVICIOS = ("mosquitto", "ollama", "andon-sensores", "andon-core", "andon-web")
ESPERA_REPORTE_S = 120
LIMITE_PARO_S = 1.0

# Frases verificadas con el modelo real (docs/pruebas.md). Las pruebas con Ollama falso las ajustan.
FRASE_CU03 = "Huele a quemado y salió una chispa del cable de alimentación"
FRASE_CU04 = "Las piezas salen rayadas y fuera de especificación"
FRASE_CU05 = "Algo raro pasa, no sé qué es" + os.environ.get("ANDON_PRUEBA_AMBIGUO", "")
FRASE_NORMAL = "Todo funciona bien, la máquina corre sin problemas" + os.environ.get("ANDON_PRUEBA_NORMAL", "")
SUFIJO_LENTO = os.environ.get("ANDON_PRUEBA_LENTO", "")

ok_n = mal_n = 0


def bien(m):
    global ok_n
    ok_n += 1
    print(f"  [OK]    {m}", flush=True)


def mal(m):
    global mal_n
    mal_n += 1
    print(f"  [FALLO] {m}", flush=True)


def comprobar(condicion, m, detalle=""):
    (bien(m) if condicion else mal(f"{m} {detalle}".rstrip()))
    return condicion


def seccion(m):
    print(f"\n== {m}", flush=True)


def sistema(*args):
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def systemctl(*args):
    return subprocess.run(("systemctl", *args), capture_output=True, text=True).returncode == 0


def http(ruta, datos=None):
    """(código, json). Código 0 si la web no responde."""
    cuerpo = None if datos is None else json.dumps(datos).encode()
    pedido = urllib.request.Request(WEB + ruta, data=cuerpo, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=5) as r:
            texto = r.read()
            return r.status, json.loads(texto) if ruta.startswith("/api") else texto
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:      # páginas de error en HTML
            return e.code, {}
    except (urllib.error.URLError, OSError, ValueError):
        return 0, {}


def estado():
    codigo, d = http("/api/estado")
    return d if codigo == 200 else {}


def esperar(condicion, timeout, paso=0.05):
    """Devuelve los segundos que tardó, o None si venció el plazo."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            if condicion():
                return time.monotonic() - t0
        except (KeyError, TypeError):
            pass
        time.sleep(paso)
    return None


def nombre_estado(s=None):
    s = estado() if s is None else s
    return (s.get("estado") or {}).get("estado")


def paro_activo():
    return bool((estado().get("seguridad") or {}).get("activo"))


class Pruebas:
    def __init__(self):
        self.cp = configparser.ConfigParser(interpolation=None)
        self.cp.read(CONF, encoding="utf-8")
        self.pin = self.cp.get("web", "pin")
        self.paro_ruta = self.cp.get("general", "paro_ruta")
        self.db = self.cp.get("general", "db_ruta")
        with open(CONF, "rb") as f:
            self.conf_original = f.read()

    # ------------------------------------------------------------------ utilidades
    def reiniciar(self, pin=None):
        return http("/api/reiniciar", {"pin": self.pin if pin is None else pin})[0]

    def liberar(self):
        """Deja la estación en reposo y luz verde."""
        self.reiniciar()
        return esperar(lambda: nombre_estado() == "reposo"
                       and estado()["salidas"]["luz"] == "verde", 15) is not None

    def inyectar(self, **campos):
        subprocess.run(["mosquitto_pub", "-h", "127.0.0.1", "-t", "andon/e1/sim/inyectar",
                        "-m", json.dumps(campos)], check=True)

    def reporte(self, texto):
        codigo, d = http("/api/reporte", {"texto": texto, "ts_navegador": 1762700000})
        if codigo != 202:
            return None
        resultado = {}

        def llego():
            c, e = http("/api/evento/" + d["id"])
            if c == 200:
                resultado.update(e)
            return c == 200
        esperar(llego, ESPERA_REPORTE_S, paso=0.5)
        return resultado or None

    def filas_db(self):
        con = sqlite3.connect(self.db)
        try:
            return con.execute("select count(*) from eventos").fetchone()[0]
        finally:
            con.close()

    def umbrales(self, **valores):
        return http("/api/umbrales", {"pin": self.pin, "valores": valores})[0]

    # ------------------------------------------------------------------ parte 1
    def base(self):
        seccion("Servicios y permisos")
        for s in SERVICIOS:
            comprobar(systemctl("is-active", "-q", s), f"{s} activo")
        for s in SERVICIOS[2:]:
            comprobar(systemctl("is-enabled", "-q", s), f"{s} habilitado al arrancar (REQ-N06)")
        for ruta in ("/", "/tablero", "/supervisor"):
            comprobar(http(ruta)[0] == 200, f"web {ruta}")
        info = os.stat(CONF)
        dueno = pwd.getpwuid(info.st_uid).pw_name
        comprobar(dueno == "andon", "la configuración es del usuario andon", f"(es de {dueno})")
        comprobar(stat.S_IMODE(info.st_mode) == 0o640, "el PIN no es legible por otros usuarios",
                  f"(modo {stat.S_IMODE(info.st_mode):o})")

    def modo_real(self):
        seccion("Modo real sin sensores: libgpiod, permisos y D13")
        if any(os.path.exists(d) for d in DROPINS):
            mal("hay un drop-in de modo sim instalado: no es el modo real (use modo.sh real)")
            return
        comprobar(http("/simulador")[0] == 404, "el simulador no existe en modo real")
        comprobar(http("/api/sim/ajustar", {"vib_g": 0.1})[0] == 404, "los ajustes no existen en modo real")
        systemctl("stop", "andon-sensores")
        self._borrar_paro()
        inicio = time.time()
        systemctl("start", "andon-sensores")
        # `seguridad` es retenido: hay que esperar un paro publicado por ESTE arranque
        tardo = esperar(lambda: estado()["seguridad"]["activo"] and estado()["seguridad"]["ts"] > inicio
                        and estado()["salidas"]["ts"] > inicio, 15, paso=0.2)
        if not comprobar(tardo is not None, "sin sensores detiene la máquina (D13)"):
            print(sistema("journalctl", "-u", "andon-sensores", "-n", "15", "--no-pager"))
            return
        s = estado()
        comprobar(s["seguridad"]["sensor"].endswith("_fallo"), "el motivo es un sensor ausente",
                  f"({s['seguridad']['sensor']})")
        comprobar(s["salidas"]["maquina"] is False and s["salidas"]["luz"] == "roja", "máquina detenida y luz roja")
        comprobar(systemctl("is-active", "-q", "andon-sensores"), "el servicio sigue vivo con el hardware real abierto")
        self._gpio_real()
        comprobar(self.reiniciar("0000") == 403, "PIN incorrecto rechazado")
        self.reiniciar()
        time.sleep(4)
        comprobar(paro_activo(), "reiniciar sin sensores vuelve a detener: la falla sigue presente")

    @staticmethod
    def _gpio_real():
        try:
            with open("/sys/kernel/debug/gpio", encoding="ascii") as f:
                lineas = [l.strip() for l in f if "andon-sensores" in l]
        except OSError:
            print("  [AVISO] sin /sys/kernel/debug/gpio: no se pudo leer el estado eléctrico")
            return
        comprobar(len(lineas) == 5, "las 5 salidas están tomadas por andon-sensores", f"({len(lineas)})")
        maquina = [l for l in lineas if "GPIO17" in l]
        comprobar(bool(maquina) and "out lo" in maquina[0], "GPIO17 (MOSFET) está en bajo durante el paro",
                  str(maquina))

    @staticmethod
    def _limpiar_ajustes():
        """Borra los controles retenidos del panel: la prueba arranca desde valores normales."""
        subprocess.run(["mosquitto_pub", "-h", "127.0.0.1", "-r", "-n", "-t", "andon/e1/sim/ajustar"], check=False)

    def _borrar_paro(self):
        try:
            os.unlink(self.paro_ruta)
        except FileNotFoundError:
            pass

    # ------------------------------------------------------------------ parte 2
    def activar_sim(self):
        seccion("Activando modo sim (drop-in temporal)")
        for dropin in DROPINS:
            os.makedirs(os.path.dirname(dropin), exist_ok=True)
            with open(dropin, "w", encoding="utf-8") as f:
                f.write("[Service]\nEnvironment=ANDON_MODO=sim\n")
        systemctl("stop", "andon-sensores")
        systemctl("daemon-reload")
        self._borrar_paro()
        self._limpiar_ajustes()
        systemctl("start", "andon-sensores")
        systemctl("restart", "andon-core", "andon-web")
        esperar(lambda: http("/api/estado")[0] == 200, 15, 0.2)
        comprobar(esperar(lambda: not paro_activo() and estado()["lecturas_edad_s"] < 3, 15, 0.2) is not None,
                  "sensores simulados publicando")
        print("  Esperando a que cargue el modelo (hasta 90 s)…", flush=True)
        comprobar(esperar(lambda: nombre_estado() == "reposo", 90, 0.5) is not None,
                  "andon-core en reposo con el modelo cargado", f"(estado {nombre_estado()})")

    def casos(self):
        seccion("CU-01 a CU-07 con el modelo real")
        s = estado()
        comprobar(s["salidas"]["luz"] == "verde" and s["salidas"]["maquina"] is True, "CU-01 luz verde y máquina en marcha")
        filas = self.filas_db()
        e = self.reporte(FRASE_NORMAL)
        comprobar(e and e["categoria"] == "operacion_normal" and e["accion"] == "ninguna", "reporte normal → sin acción", str(e))
        self.liberar()

        e = self.reporte(FRASE_CU04)
        comprobar(e and e["categoria"] == "problema_calidad" and e["accion"] == "avisar", "CU-04 calidad → aviso", str(e))
        s = estado()
        comprobar(s["salidas"]["luz"] == "amarilla" and s["salidas"]["maquina"] is True, "CU-04 amarilla y la máquina sigue")
        self.liberar()

        e = self.reporte(FRASE_CU05)
        comprobar(e and e["accion"] == "revision_manual", "CU-05 ambiguo → revisión manual", str(e))
        comprobar(estado()["salidas"]["maquina"] is True, "CU-05 la máquina sigue")
        self.liberar()

        e = self.reporte(FRASE_CU03)
        comprobar(e and e["categoria"] == "falla_electrica" and e["accion"] == "parar_maquina", "CU-03 falla eléctrica → paro", str(e))
        s = estado()
        comprobar(s["salidas"]["maquina"] is False and s["salidas"]["luz"] == "roja", "CU-03 máquina detenida y luz roja")
        if e:
            print(f"        latencia: {e['latencia_ms'] / 1000:.1f} s · confianza {e['prob']:.3f}")
            comprobar(abs(e["ts"] - 1762700000) < ESPERA_REPORTE_S, "el evento usa la hora del navegador (D9)", f"(ts {e['ts']})")

        comprobar(self.reiniciar("0000") == 403, "CU-06 PIN incorrecto rechazado")
        time.sleep(1)
        comprobar(estado()["salidas"]["maquina"] is False, "CU-06 sigue detenida con PIN incorrecto")
        comprobar(self.liberar(), "CU-06 con PIN correcto vuelve a verde")
        comprobar(self.filas_db() - filas >= 4, "REQ-F10 eventos guardados en SQLite", f"({self.filas_db() - filas})")

    def paro(self):
        seccion("CU-02 paro de seguridad")
        t0 = time.monotonic()
        self.inyectar(vib_g=2.0, duracion_s=2)
        comprobar(esperar(paro_activo, 5, 0.01) is not None, "paro por vibración")
        tardo = time.monotonic() - t0
        comprobar(tardo < LIMITE_PARO_S, f"REQ-N04 paro en {tardo * 1000:.0f} ms visto desde la web")
        comprobar(estado()["salidas"]["maquina"] is False, "máquina detenida")
        time.sleep(3)
        comprobar(paro_activo(), "el paro sigue retenido al desaparecer la falla")
        systemctl("restart", "andon-sensores")
        time.sleep(4)
        comprobar(paro_activo(), "el paro sobrevive al reinicio del servicio")
        comprobar(self.liberar(), "se libera con PIN")

        print("  Paro con el modelo calculando…", flush=True)
        hilo = threading.Thread(target=self.reporte, args=(FRASE_NORMAL + SUFIJO_LENTO,))
        hilo.start()
        analiza = esperar(lambda: nombre_estado() == "analizando", 10, 0.05)
        comprobar(analiza is not None, "luz amarilla mientras analiza", f"(estado {nombre_estado()})")
        time.sleep(1)
        t0 = time.monotonic()
        self.inyectar(vib_g=2.0, duracion_s=2)
        esperar(paro_activo, 5, 0.01)
        tardo = time.monotonic() - t0
        comprobar(tardo < LIMITE_PARO_S, f"REQ-N04 paro en {tardo * 1000:.0f} ms con Ollama calculando")
        hilo.join()
        comprobar(paro_activo() and estado()["salidas"]["maquina"] is False, "el modelo no levantó el paro")
        time.sleep(3)
        comprobar(self.liberar(), "se libera con PIN")

    def panel(self):
        seccion("Panel del simulador")
        comprobar(http("/simulador")[0] == 200, "página /simulador disponible")
        comprobar(http("/api/sim/ajustar", {"vib_g": 99})[0] == 400, "valor fuera de rango rechazado")
        comprobar(http("/api/sim/ajustar", {"mpu_ok": False})[0] == 200, "MPU-6050 desconectado desde el panel")
        comprobar(esperar(lambda: estado()["seguridad"]["sensor"] == "mpu6050_fallo", 6, 0.1) is not None,
                  "sensor desconectado → paro D13")
        http("/api/sim/ajustar", {"mpu_ok": True})
        time.sleep(0.5)
        comprobar(self.liberar(), "se libera al reconectar")
        comprobar(http("/api/sim/ajustar", {"vib_g": 2.0})[0] == 200, "perilla de vibración a 2 g")
        comprobar(esperar(lambda: estado()["seguridad"]["sensor"] == "vibracion", 6, 0.1) is not None,
                  "la perilla dispara el paro por vibración")
        http("/api/sim/ajustar", {"vib_g": 0.1})
        comprobar(self.liberar(), "se libera al normalizar")
        http("/api/sim/ajustar", {"temp_c": 90})
        comprobar(esperar(lambda: estado()["seguridad"]["sensor"] == "temperatura", 6, 0.1) is not None,
                  "la perilla dispara el paro por temperatura")
        http("/api/sim/ajustar", {"temp_c": None})
        comprobar(self.liberar(), "se libera al volver a automático")

    def recarga(self):
        seccion("CU-07 umbrales sin reiniciar")
        comprobar(self.umbrales(temp_c="999") == 400, "valor fuera de rango rechazado")
        comprobar(self.umbrales(vib_rms_g="0.05") == 200, "umbral bajo guardado")
        comprobar(esperar(paro_activo, 5, 0.05) is not None, "sensores aplican el umbral nuevo sin reiniciar")
        comprobar(self.umbrales(vib_rms_g="1.0") == 200, "umbral restaurado")
        time.sleep(1)
        comprobar(self.liberar(), "se libera con PIN")

    def ollama_caido(self):
        seccion("Ollama caído")
        systemctl("stop", "ollama")
        try:
            e = self.reporte(FRASE_CU03)
            comprobar(e and e["accion"] == "revision_manual" and e["error"], "falla del modelo → revisión manual", str(e))
            comprobar(estado()["salidas"]["maquina"] is True, "la máquina sigue en marcha")
            self.liberar()
            t0 = time.monotonic()
            self.inyectar(vib_g=2.0, duracion_s=2)
            esperar(paro_activo, 5, 0.01)
            comprobar(time.monotonic() - t0 < LIMITE_PARO_S, "el paro funciona sin Ollama")
            time.sleep(3)
            self.liberar()
        finally:
            systemctl("start", "ollama")

    def journal(self):
        seccion("Registros del sistema")
        for s in SERVICIOS[2:]:
            texto = sistema("journalctl", "-u", s, "--no-pager", "-n", "2000")
            comprobar("Traceback" not in texto, f"{s} sin excepciones")
        retrasos = sistema("journalctl", "-u", "andon-sensores", "--no-pager", "-n", "2000").count("se retras")
        comprobar(retrasos == 0, "lazo de seguridad sin retrasos", f"({retrasos})")

    def restaurar(self, dejar_sim):
        seccion("Restaurando la placa")
        with open(CONF, "wb") as f:
            f.write(self.conf_original)
        if not dejar_sim:
            for dropin in DROPINS:
                if os.path.exists(dropin):
                    os.unlink(dropin)
        systemctl("stop", "andon-sensores")
        systemctl("daemon-reload")
        self._borrar_paro()
        self._limpiar_ajustes()
        systemctl("start", "andon-sensores")
        systemctl("restart", "andon-core", "andon-web")
        print("  Modo sim activo: abra http://<placa>:5000/simulador" if dejar_sim
              else "  Modo real restaurado. Sin sensores, la máquina volverá a detenerse: es lo esperado.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dejar-sim", action="store_true")
    ap.add_argument("--solo-sim", action="store_true")
    a = ap.parse_args()
    if os.geteuid() != 0:
        sys.exit("Correr como root.")
    p = Pruebas()
    try:
        if not a.solo_sim:
            p.base()
            p.modo_real()
        p.activar_sim()
        p.casos()
        p.paro()
        p.panel()
        p.recarga()
        p.ollama_caido()
        p.journal()
    finally:
        p.restaurar(a.dejar_sim)
    print(f"\n== Resumen: {ok_n} OK · {mal_n} fallos")
    return 1 if mal_n else 0


if __name__ == "__main__":
    sys.exit(main())
