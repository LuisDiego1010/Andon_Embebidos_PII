import json, time, urllib.request as u
B = "http://127.0.0.1:5000"
def post(r, d):
    q = u.Request(B + r, json.dumps(d).encode(), {"Content-Type": "application/json"})
    try: return json.load(u.urlopen(q, timeout=10))
    except Exception as e: return str(e)
def est(): return json.load(u.urlopen(B + "/api/estado", timeout=10))
def ver(t):
    s = est(); sal = s["salidas"]; seg = s["seguridad"] or {}
    print(f"{time.strftime('%T')} {t:32} luz={sal['luz']:9} zumbador={sal['zumbador']!s:5} maquina={sal['maquina']!s:5} "
          f"paro={seg.get('activo')} pantalla={sal['oled']}", flush=True)
def reporte(texto):
    rid = post("/api/reporte", {"texto": texto, "ts_navegador": time.time()})["id"]
    for _ in range(90):
        time.sleep(1)
        try: e = json.load(u.urlopen(f"{B}/api/evento/{rid}", timeout=10)); break
        except Exception: pass
    print(f"   modelo: {e['categoria']} {e['prob']:.3f} -> {e['accion']} ({e['latencia_ms']/1000:.1f} s)", flush=True)
ver("inicio")
post("/api/sim/ajustar", {"vib_g": 2.0}); time.sleep(2); ver("1. aspa desbalanceada")
time.sleep(4)
post("/api/sim/ajustar", {"vib_g": 0.1}); time.sleep(1); post("/api/reiniciar", {"pin": "1234"}); time.sleep(3); ver("2. normal + reinicio")
reporte("Las piezas salen rayadas y fuera de especificación"); time.sleep(1); ver("3. reporte de calidad")
time.sleep(4)
reporte("Huele a quemado y salió una chispa del cable de alimentación"); time.sleep(1); ver("4. falla eléctrica")
time.sleep(5)
post("/api/reiniciar", {"pin": "1234"}); time.sleep(3); ver("5. reinicio")
