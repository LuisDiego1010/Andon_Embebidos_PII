"""Configuración de la estación: archivo INI + variables de entorno.

Ruta: variable ANDON_CONF (por defecto /etc/andon/andon.conf). Variables que
sobrescriben el archivo: ANDON_MODO, ANDON_MQTT_HOST, ANDON_MQTT_PUERTO,
ANDON_OLLAMA_URL. Un archivo ausente no es error: se usan los valores por defecto.
"""

import configparser
import os
from dataclasses import dataclass, field, replace

RUTA_POR_DEFECTO = "/etc/andon/andon.conf"
MODOS = ("sim", "rpi")


class ErrorConfig(ValueError):
    """Valor inválido o ilegible en la configuración."""


@dataclass(frozen=True)
class Mqtt:
    host: str = "127.0.0.1"
    puerto: int = 1883


@dataclass(frozen=True)
class OllamaCfg:
    url: str = "http://127.0.0.1:11434"
    modelo: str = "tev1:0.8b"
    timeout_s: float = 45.0
    umbral_confianza: float = 0.92
    calentar: bool = True


@dataclass(frozen=True)
class Umbrales:
    vib_rms_g: float = 1.0
    temp_c: float = 60.0


@dataclass(frozen=True)
class Gpio:
    chip: str = "/dev/gpiochip0"
    maquina: int = 17
    verde: int = 22
    amarilla: int = 27
    roja: int = 23
    zumbador: int = 24


@dataclass(frozen=True)
class I2c:
    bus: int = 1
    mpu: int = 0x68
    oled: int = 0x3C


@dataclass(frozen=True)
class Web:
    host: str = "0.0.0.0"
    puerto: int = 5000
    pin: str = "1234"


@dataclass(frozen=True)
class Config:
    modo: str = "rpi"
    db_ruta: str = "/var/lib/andon/andon.db"
    mqtt: Mqtt = field(default_factory=Mqtt)
    ollama: OllamaCfg = field(default_factory=OllamaCfg)
    umbrales: Umbrales = field(default_factory=Umbrales)
    gpio: Gpio = field(default_factory=Gpio)
    i2c: I2c = field(default_factory=I2c)
    web: Web = field(default_factory=Web)


def _seccion(cp, nombre, defecto, tipos):
    """Construye el dataclass `defecto.__class__` con los valores de [nombre]."""
    if not cp.has_section(nombre):
        return defecto
    valores = {}
    for campo, tipo in tipos.items():
        if not cp.has_option(nombre, campo):
            continue
        try:
            if tipo is bool:
                valores[campo] = cp.getboolean(nombre, campo)
            elif tipo is int:
                valores[campo] = int(cp.get(nombre, campo), 0)  # acepta 0x68
            elif tipo is float:
                valores[campo] = cp.getfloat(nombre, campo)
            else:
                valores[campo] = cp.get(nombre, campo).strip()
        except ValueError as e:
            raise ErrorConfig(f"[{nombre}] {campo}: {e}") from e
    return type(defecto)(**{**defecto.__dict__, **valores})


def _validar(c):
    if c.modo not in MODOS:
        raise ErrorConfig(f"modo inválido: {c.modo!r} (use {' o '.join(MODOS)})")
    if not 0 < c.ollama.umbral_confianza <= 1:
        raise ErrorConfig("[ollama] umbral_confianza debe estar en (0, 1]")
    if c.ollama.timeout_s <= 0:
        raise ErrorConfig("[ollama] timeout_s debe ser positivo")
    if c.umbrales.vib_rms_g <= 0 or c.umbrales.temp_c <= 0:
        raise ErrorConfig("[umbrales] los umbrales deben ser positivos")
    pines = [c.gpio.maquina, c.gpio.verde, c.gpio.amarilla, c.gpio.roja, c.gpio.zumbador]
    if len(set(pines)) != len(pines):
        raise ErrorConfig(f"[gpio] hay pines repetidos: {pines}")
    if not all(0 <= p <= 27 for p in pines):
        raise ErrorConfig(f"[gpio] pin fuera de 0..27: {pines}")
    if not 0 < c.mqtt.puerto < 65536 or not 0 < c.web.puerto < 65536:
        raise ErrorConfig("puerto fuera de rango")
    return c


def cargar(ruta=None, entorno=None):
    """Lee la configuración. `entorno` por defecto es os.environ."""
    env = os.environ if entorno is None else entorno
    ruta = ruta or env.get("ANDON_CONF", RUTA_POR_DEFECTO)
    cp = configparser.ConfigParser(interpolation=None)
    try:
        if os.path.isfile(ruta):
            with open(ruta, encoding="utf-8") as f:
                cp.read_file(f)
    except (OSError, configparser.Error) as e:
        raise ErrorConfig(f"no se pudo leer {ruta}: {e}") from e

    base = Config()
    general = dict(cp["general"]) if cp.has_section("general") else {}
    c = Config(
        modo=general.get("modo", base.modo).strip(),
        db_ruta=general.get("db_ruta", base.db_ruta).strip(),
        mqtt=_seccion(cp, "mqtt", base.mqtt, {"host": str, "puerto": int}),
        ollama=_seccion(cp, "ollama", base.ollama, {
            "url": str, "modelo": str, "timeout_s": float,
            "umbral_confianza": float, "calentar": bool}),
        umbrales=_seccion(cp, "umbrales", base.umbrales,
                          {"vib_rms_g": float, "temp_c": float}),
        gpio=_seccion(cp, "gpio", base.gpio, {
            "chip": str, "maquina": int, "verde": int, "amarilla": int,
            "roja": int, "zumbador": int}),
        i2c=_seccion(cp, "i2c", base.i2c, {"bus": int, "mpu": int, "oled": int}),
        web=_seccion(cp, "web", base.web, {"host": str, "puerto": int, "pin": str}),
    )

    # Variables de entorno: tienen prioridad sobre el archivo
    modo = env.get("ANDON_MODO")
    if modo:
        c = replace(c, modo=modo.strip())
    host = env.get("ANDON_MQTT_HOST")
    puerto = env.get("ANDON_MQTT_PUERTO")
    if host or puerto:
        try:
            c = replace(c, mqtt=Mqtt(host or c.mqtt.host,
                                      int(puerto) if puerto else c.mqtt.puerto))
        except ValueError as e:
            raise ErrorConfig(f"ANDON_MQTT_PUERTO: {e}") from e
    url = env.get("ANDON_OLLAMA_URL")
    if url:
        c = replace(c, ollama=replace(c.ollama, url=url.strip()))
    return _validar(c)

