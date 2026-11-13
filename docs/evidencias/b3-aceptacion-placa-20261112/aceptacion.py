"""Guion de aceptación (docs/aceptacion.md) en la placa, con un navegador real (Playwright).

Uso: python aceptacion.py BASE_URL SALIDA_DIR
Antes de correrlo: estación en modo sim y recién reiniciados ollama + andon-core (para O1/O2).
"""
import json
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE, SALIDA = sys.argv[1].rstrip("/"), sys.argv[2]
PIN = "1234"
NORMAL = {"vib_g": 0.1, "ruido_g": 0.01, "temp_c": None, "mpu_ok": True, "ds18b20_ok": True}
MOVIL = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True, "locale": "es-CR"}
resultados = []


def anotar(n, marca, nota):
    resultados.append((n, marca, nota))
    print(f"{n:4} {marca} {nota}", flush=True)


def http(ruta, datos=None):
    req = urllib.request.Request(BASE + ruta, method="POST" if datos is not None else "GET",
                                 data=json.dumps(datos).encode() if datos is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def estado():
    return http("/api/estado")[1]


def esperar(cond, max_s, paso=0.1):
    t0 = time.monotonic()
    while time.monotonic() - t0 < max_s:
        s = estado()
        if cond(s):
            return time.monotonic() - t0, s
        time.sleep(paso)
    return None, estado()


def paro(s):
    return bool(s.get("seguridad") and s["seguridad"].get("activo"))


def a_normal():
    """Sensores normales, máquina en marcha y sin paro (por API, como el botón del simulador)."""
    http("/api/sim/ajustar", NORMAL)
    time.sleep(1.5)
    for _ in range(3):
        http("/api/reiniciar", {"pin": PIN})
        t, s = esperar(lambda s: not paro(s) and s["salidas"].get("maquina")
                       and s["estado"]["estado"] not in ("detenida",), 6)
        if t is not None:
            return True
    return False


def reportar(page, texto, max_s=170):
    """Envía desde el formulario y devuelve (texto del resultado, segundos)."""
    page.fill("#texto", texto)
    page.evaluate("() => { const r = document.getElementById('resultado'); r.hidden = true; r.textContent = ''; }")
    t0 = time.monotonic()
    page.click("#enviar")
    page.wait_for_function(
        "() => { const r = document.getElementById('resultado');"
        " return !r.hidden && !r.textContent.startsWith('Analizando'); }", timeout=max_s * 1000)
    return page.inner_text("#resultado").replace("\n", " · "), time.monotonic() - t0


def foto(page, nombre):
    page.screenshot(path=f"{SALIDA}/{nombre}.png", full_page=True)


with sync_playwright() as pw:
    nav = pw.chromium.launch()
    movil = nav.new_context(**MOVIL)
    op = movil.new_page()
    pc = nav.new_context(viewport={"width": 1366, "height": 900}, locale="es-CR")
    sup = pc.new_page()
    sup.on("dialog", lambda d: d.accept())

    # ---------------------------------------------------------------- O1 / O2 calentamiento
    op.goto(BASE + "/")
    try:
        op.wait_for_function("() => document.getElementById('estacion').textContent.includes('cargando el modelo')",
                             timeout=15000)
        aviso = True
        foto(op, "o1-calentando")
    except Exception:
        aviso = False
    anotar("O1", "✅" if aviso else "⚠️", "aviso «cargando el modelo» visible" if aviso
           else f"no se vio el aviso (estado {estado()['estado']['estado']})")
    try:
        txt, seg = reportar(op, "Huele a quemado cerca del motor")
        ok = "tardó demasiado" not in txt and "No llegó respuesta" not in txt
        anotar("O2", "✅" if ok else "❌", f"{txt} ({seg:.0f} s desde el envío)")
    except Exception as e:
        anotar("O2", "❌", f"sin resultado: {e}")
    a_normal()

    # ---------------------------------------------------------------- O3–O8
    casos = [("O3", "La máquina funciona bien, sin novedades", lambda t: "Operación normal" in t or "Revisión manual" in t),
             ("O4", "Huele a quemado y salió una chispa del cable de alimentación", lambda t: "Máquina detenida" in t and "Mantenimiento" in t),
             ("O5", "Salen chispas del cable", None),
             ("O6", "Las piezas salen con rebaba y fuera de medida", lambda t: "Calidad" in t and "Aviso" in t),
             ("O6b", "Las piezas salen rayadas y fuera de especificación", lambda t: "Calidad" in t),
             ("O7", "Se acabaron los tornillos en la línea", lambda t: "Supervisión" in t),
             ("O8", "Algo raro pasa, no sé qué es", lambda t: "un supervisor revisará" in t)]
    for n, frase, cond in casos:
        txt, seg = reportar(op, frase)
        marca = "📝" if cond is None else ("✅" if cond(txt) else "❌")
        anotar(n, marca, f"«{frase}» → {txt}")
        if n == "O4":
            foto(op, "o4-falla-electrica")
            # U6: detenida por el modelo → supervisor
            sup.goto(BASE + "/supervisor")
            sup.wait_for_timeout(2500)
            causa = sup.inner_text("#causa")
            sup.fill("#pin", PIN)
            sup.click("#reiniciar")
            sup.wait_for_function("() => { const m = document.getElementById('msg-reinicio');"
                                  " return !m.hidden && !m.textContent.startsWith('Orden enviada. Verificando'); }",
                                  timeout=15000)
            msg = sup.inner_text("#msg-reinicio")
            ok = "falla reportada por el operario" in causa and "volvió a operar" in msg
            anotar("U6", "✅" if ok else ("⚠️" if "Máquina detenida" not in txt else "❌"),
                   f"causa «{causa}» → «{msg}»")
        a_normal()

    # ---------------------------------------------------------------- O9 recargar
    op.fill("#texto", "La banda transportadora hace un ruido metálico fuerte en el rodillo")
    op.click("#enviar")
    op.wait_for_timeout(3000)
    op.reload()
    op.wait_for_timeout(1500)
    sigue = "Analizando" in op.inner_text("#resultado") and op.input_value("#texto").startswith("La banda")
    op.wait_for_function("() => { const r = document.getElementById('resultado');"
                         " return !r.hidden && !r.textContent.startsWith('Analizando'); }", timeout=170000)
    anotar("O9", "✅" if sigue else "❌", f"tras recargar sigue «Analizando» con el texto: {sigue}; "
           f"final: {op.inner_text('#resultado').replace(chr(10), ' · ')}")
    a_normal()

    # ---------------------------------------------------------------- O10 sin red mientras espera
    op.fill("#texto", "Se escucha un golpeteo en el motor cada pocos segundos")
    op.click("#enviar")
    op.wait_for_timeout(2000)
    movil.set_offline(True)
    op.wait_for_timeout(10000)
    durante = op.inner_text("#resultado")
    movil.set_offline(False)
    op.wait_for_function("() => { const r = document.getElementById('resultado');"
                         " return !r.hidden && !r.textContent.startsWith('Analizando'); }", timeout=170000)
    final = op.inner_text("#resultado").replace("\n", " · ")
    ok = durante.startswith("Analizando") and "No llegó" not in final
    anotar("O10", "✅" if ok else "❌", f"sin red: «{durante.splitlines()[0]}»; al volver: {final}")
    a_normal()

    # ---------------------------------------------------------------- O11 enviar sin red
    movil.set_offline(True)
    op.fill("#texto", "Prueba sin conexión")
    op.click("#enviar")
    op.wait_for_timeout(1500)
    msg = op.inner_text("#resultado")
    queda = op.input_value("#texto")
    movil.set_offline(False)
    anotar("O11", "✅" if "No hay conexión con la estación" in msg and queda == "Prueba sin conexión" else "❌",
           f"«{msg}», texto conservado: {queda == 'Prueba sin conexión'}")

    # ---------------------------------------------------------------- O12 280 caracteres
    largo = ("La máquina número ñandú vibra un poco más de lo normal y el operario anotó la lectura. " * 5)
    op.fill("#texto", "")
    op.type("#texto", largo[:300], delay=0)
    valor, cuenta = op.input_value("#texto"), op.inner_text("#cuenta")
    txt, _ = reportar(op, valor)
    anotar("O12", "✅" if len(valor) == 280 and cuenta == "280" and "Analizando" not in txt else "❌",
           f"longitud {len(valor)}, contador {cuenta}; resultado: {txt}")
    a_normal()

    # ---------------------------------------------------------------- O13 emoji
    txt, _ = reportar(op, "la banda hace ruido 🔧")
    anotar("O13", "✅" if "Escriba" not in txt and "Error" not in txt else "❌", f"aceptado → {txt}")
    a_normal()

    # ---------------------------------------------------------------- O14 espacios
    op.fill("#texto", "     ")
    op.click("#enviar")
    op.wait_for_timeout(500)
    msg = op.inner_text("#resultado")
    anotar("O14", "✅" if msg == "Escriba qué está pasando." else "❌", f"«{msg}»")

    # ---------------------------------------------------------------- O17 legibilidad en el celular
    anchos = {}
    for ruta in ("/", "/tablero", "/supervisor", "/simulador"):
        p = movil.new_page()
        p.goto(BASE + ruta)
        p.wait_for_timeout(1500)
        anchos[ruta] = p.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
        foto(p, "o17-movil" + ruta.replace("/", "-").rstrip("-"))
        p.close()
    ok = all(a <= b for a, b in anchos.values())
    anotar("O17", "✅" if ok else "❌", "sin desplazamiento horizontal: " + ", ".join(
        f"{r} {a}/{b}px" for r, (a, b) in anchos.items()))

    # ---------------------------------------------------------------- S1 aspa desbalanceada + tablero
    a_normal()
    sim = pc.new_page()
    sim.goto(BASE + "/simulador")
    sim.wait_for_timeout(2000)
    t0 = time.monotonic()
    sim.click("text=Aspa desbalanceada")
    t, s = esperar(paro, 5, paso=0.05)
    tab = pc.new_page()
    tab.goto(BASE + "/tablero")
    tab.wait_for_timeout(2000)
    alerta = tab.inner_text("#alerta")
    zumb = s["salidas"].get("zumbador")
    ok = t is not None and s["salidas"]["luz"] == "roja" and zumb and "vibración excesiva" in alerta
    anotar("S1", "✅" if ok else "❌", f"paro visto por la web en {t:.2f} s (incluye MQTT y sondeo), luz {s['salidas']['luz']}, "
           f"zumbador {zumb}; tablero: «{alerta}»" if t else f"sin paro: {s}")
    foto(tab, "s1-tablero-paro")
    foto(sim, "s1-simulador-paro")

    # ---------------------------------------------------------------- O15 operario con paro
    op.goto(BASE + "/")
    op.wait_for_timeout(3500)
    aviso = op.inner_text("#estacion")
    txt, _ = reportar(op, "Se escucha un ruido fuerte en la máquina")
    anotar("O15", "✅" if "PARO DE SEGURIDAD" in aviso and "Paro de seguridad activo" in txt else "❌",
           f"aviso «{aviso}» → {txt}")

    # ---------------------------------------------------------------- U1 supervisor con paro
    sup.goto(BASE + "/supervisor")
    sup.wait_for_timeout(2500)
    actual, causa = sup.inner_text("#actual"), sup.inner_text("#causa")
    anotar("U1", "✅" if "paro_seguridad" not in actual and "vibración" in causa and "límite" in causa else "❌",
           f"estado «{actual}», causa «{causa}», lecturas «{sup.inner_text('#lecturas')}»")
    foto(sup, "u1-supervisor-paro")

    # ---------------------------------------------------------------- S2 la causa desaparece, el paro sigue
    http("/api/sim/ajustar", {"vib_g": 0.1})
    time.sleep(3)
    s = estado()
    anotar("S2", "✅" if paro(s) and s["salidas"]["luz"] == "roja" else "❌",
           f"vibración {s['lecturas']['vib_rms_g']} g, paro retenido: {paro(s)}")

    # ---------------------------------------------------------------- U2 / U3 PIN incorrecto
    def reiniciar_ui(pin):
        sup.fill("#pin", pin)
        sup.evaluate("() => { const m = document.getElementById('msg-reinicio'); m.hidden = true; m.textContent = ''; }")
        sup.click("#reiniciar")
        sup.wait_for_function("() => { const m = document.getElementById('msg-reinicio');"
                              " return !m.hidden && !m.textContent.startsWith('Orden enviada. Verificando'); }",
                              timeout=15000)
        sup.wait_for_timeout(300)
        return sup.inner_text("#msg-reinicio")

    msg = reiniciar_ui("0000")
    anotar("U2", "✅" if msg == "PIN incorrecto." and paro(estado()) else "❌", f"«{msg}», sigue detenida: {paro(estado())}")
    msgs = [reiniciar_ui("0000") for _ in range(5)]
    anotar("U3", "✅" if "Demasiados intentos" in msgs[-1] else "❌", f"6.º intento: «{msgs[-1]}»")
    print("  (esperando 31 s por el bloqueo de PIN)", flush=True)
    time.sleep(31)

    # ---------------------------------------------------------------- U4 causa presente
    http("/api/sim/ajustar", {"vib_g": 2.0})
    time.sleep(1.5)
    msg = reiniciar_ui(PIN)
    anotar("U4", "✅" if "se detuvo de nuevo" in msg and "volvió a operar" not in msg else "❌", f"«{msg}»")

    # ---------------------------------------------------------------- U5 causa corregida
    http("/api/sim/ajustar", {"vib_g": 0.1})
    time.sleep(1.5)
    msg = reiniciar_ui(PIN)
    time.sleep(1)
    anotar("U5", "✅" if "volvió a operar" in msg and estado()["salidas"]["luz"] == "verde" else "❌",
           f"«{msg}», luz {estado()['salidas']['luz']}")

    # ---------------------------------------------------------------- S3 sobrecalentamiento
    sim.click("text=Sobrecalentamiento")
    t, s = esperar(paro, 6, paso=0.05)
    seg = s.get("seguridad") or {}
    anotar("S3", "✅" if t is not None and seg.get("sensor") == "temperatura" else "❌",
           f"paro en {t:.2f} s: sensor {seg.get('sensor')}, valor {seg.get('valor')} °C, límite {seg.get('umbral')}" if t
           else f"sin paro: {seg}")
    a_normal()

    # ---------------------------------------------------------------- S4 MPU-6050 desconectado
    sim.click("text=Desconectar MPU-6050")
    t, s = esperar(paro, 6, paso=0.05)
    seg = s.get("seguridad") or {}
    tab.wait_for_timeout(1500)
    anotar("S4", "✅" if t is not None and seg.get("sensor") == "mpu6050_fallo" and 1.5 <= t <= 3.5 else "❌",
           f"paro en {t:.2f} s, sensor {seg.get('sensor')}; tablero «{tab.inner_text('#alerta')}»" if t else f"sin paro: {seg}")
    a_normal()

    # ---------------------------------------------------------------- U7 eventos en el tablero
    tab.goto(BASE + "/tablero")
    tab.wait_for_timeout(2000)
    eventos = tab.locator(".evento")
    n = eventos.count()
    bajos = [eventos.nth(i).inner_text() for i in range(n) if "Revisión manual" in eventos.nth(i).inner_text()]
    ok = n > 0 and bajos and all("%" in e and "respuesta en" in e for e in bajos)
    anotar("U7", "✅" if ok else "❌", f"{n} eventos; uno de baja confianza: «{bajos[0].replace(chr(10), ' · ') if bajos else '—'}»")
    foto(tab, "u7-tablero-eventos")

    # ---------------------------------------------------------------- A1–A4 umbrales
    def umbrales_ui(vib=None, conf=None):
        sup.goto(BASE + "/supervisor")
        sup.wait_for_timeout(2000)
        sup.fill("#pin", PIN)
        if vib is not None:
            sup.fill("#vib_rms_g", vib)
        if conf is not None:
            sup.fill("#umbral_confianza", conf)
        sup.click("text=Guardar umbrales")
        sup.wait_for_function("() => !document.getElementById('msg-umbrales').hidden", timeout=10000)
        return sup.inner_text("#msg-umbrales")

    antes = estado()["umbrales"]
    msg = umbrales_ui(vib="9")
    anotar("A1", "✅" if "como máximo 4" in msg and estado()["umbrales"] == antes else "❌", f"«{msg}»")
    msg = umbrales_ui(vib="0,05")
    t, s = esperar(paro, 5, paso=0.1)
    seg = s.get("seguridad") or {}
    anotar("A2", "✅" if "Umbrales guardados" in msg and t is not None and seg.get("sensor") == "vibracion" else "❌",
           f"«{msg}»; paro en {t:.1f} s por {seg.get('sensor')} (límite {seg.get('umbral')})" if t else f"«{msg}»; sin paro")
    msg = umbrales_ui(vib="1")
    ok = a_normal()
    anotar("A3", "✅" if "Umbrales guardados" in msg and ok and estado()["umbrales"]["vib_rms_g"] == 1.0 else "❌",
           f"«{msg}», verde: {ok}")
    umbrales_ui(conf="0,5")
    txt, _ = reportar(op, "Algo raro pasa, no sé qué es")
    anotar("A4", "✅" if "Revisión manual" not in txt else "⚠️", f"con confianza 0,5: {txt}")
    msg = umbrales_ui(conf="0,92")
    a_normal()
    anotar("A4r", "✅" if estado()["umbrales"]["umbral_confianza"] == 0.92 else "❌", "confianza restaurada a 0,92")

    # ---------------------------------------------------------------- O16 3 reportes desde 2 dispositivos
    op2 = nav.new_context(**MOVIL).new_page()
    op3 = nav.new_context(**MOVIL).new_page()
    frases = ["La máquina funciona bien, sin novedades", "Se acabaron los tornillos en la línea",
              "Las piezas salen rayadas y fuera de especificación"]
    for p, f in zip((op, op2, op3), frases):
        p.goto(BASE + "/")
        p.wait_for_timeout(1000)
        p.fill("#texto", f)
        p.click("#enviar")
    finales = []
    for p in (op, op2, op3):
        p.wait_for_function("() => { const r = document.getElementById('resultado');"
                            " return !r.hidden && !r.textContent.startsWith('Analizando'); }", timeout=240000)
        finales.append(p.inner_text("#resultado").replace("\n", " · "))
    ok = all("Descartado" not in f and "No llegó" not in f for f in finales)
    anotar("O16", "✅" if ok else "❌", " | ".join(finales))
    a_normal()

    # ---------------------------------------------------------------- B4 /defensa
    d = pc.new_page()
    d.goto(BASE + "/defensa")
    d.wait_for_timeout(2000)
    d.fill("#pin", PIN)
    d.click("#todos")
    d.wait_for_function("() => /\\d+ de \\d+ casos/.test(document.getElementById('resumen').textContent)"
                        " && !document.querySelector('#casos button').disabled", timeout=900000)
    resumen = d.inner_text("#resumen")
    with d.expect_download() as dl:
        d.click("#exportar")
    dl.value.save_as(f"{SALIDA}/defensa.csv")
    foto(d, "b4-defensa")
    a, b = [int(x) for x in resumen.split(" casos")[0].split(" de ")]
    anotar("B4", "✅" if a == b else "❌", resumen)
    a_normal()
    nav.close()

total = {m: sum(1 for _, x, _ in resultados if x == m) for m in ("✅", "❌", "⚠️", "📝")}
print(f"\n== Resumen: {total['✅']} ✅ · {total['❌']} ❌ · {total['⚠️']} ⚠️ · {total['📝']} 📝 (solo se anota)")
with open(f"{SALIDA}/resultados.json", "w", encoding="utf-8") as f:
    json.dump(resultados, f, ensure_ascii=False, indent=1)
