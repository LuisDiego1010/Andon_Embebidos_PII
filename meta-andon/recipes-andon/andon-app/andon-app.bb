SUMMARY = "Aplicación de la Estación Andon (andon-sensores, andon-core, andon-web)"
DESCRIPTION = "Instala la app de Python que vive en app/ de este mismo repositorio. \
Rutas acordadas en docs/yocto-requisitos.md: /opt/andon (código), \
/etc/andon (configuración) y /var/lib/andon (datos)."
LICENSE = "CLOSED"

# El código se toma directo de app/ del repo (no hay que publicar nada antes).
# Para la entrega final se puede cambiar a una etiqueta de git (v1.0-rcN).
inherit externalsrc
EXTERNALSRC = "${@os.path.abspath(d.getVar('THISDIR') + '/../../../app')}"
EXTERNALSRC_BUILD = "${WORKDIR}/build"

SRC_URI = " \
    file://andon-sensores.service \
    file://andon-core.service \
    file://andon-web.service \
"

inherit useradd systemd allarch

# Usuario de servicio "andon" y los grupos que usan las reglas udev de la placa
# (meta-raspberrypi instala 99-com.rules: /dev/i2c-* -> grupo i2c, /dev/gpiochip* -> grupo gpio)
USERADD_PACKAGES = "${PN}"
GROUPADD_PARAM:${PN} = "--system i2c; --system gpio; --system andon"
USERADD_PARAM:${PN} = "--system --gid andon --groups i2c,gpio \
                       --home-dir /var/lib/andon --no-create-home \
                       --shell /sbin/nologin andon"

SYSTEMD_SERVICE:${PN} = "andon-sensores.service andon-core.service andon-web.service"
SYSTEMD_AUTO_ENABLE = "enable"

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    if [ -f ${S}/Makefile ] && grep -q '^install:' ${S}/Makefile; then
        # Instalador propio de la app (F6): el mismo para Raspberry Pi OS, QEMU y Yocto
        oe_runmake -C ${S} install DESTDIR=${D}
    else
        # Mientras no exista el Makefile: copia directa a las rutas acordadas
        install -d ${D}/opt/andon
        cp -R --no-preserve=ownership ${S}/src/andon ${D}/opt/andon/
        install -d ${D}/opt/andon/pruebas
        install -m 0644 ${S}/tests/contract/reportes.json ${D}/opt/andon/pruebas/
        install -d ${D}${sysconfdir}/andon
        for f in ${S}/config/*.conf; do
            [ -f "$f" ] && install -m 0644 "$f" ${D}${sysconfdir}/andon/
        done
    fi

    # Herramientas de prueba y calibración en la placa
    for t in probar_sin_hardware probar_hal inyector enviar_reporte calibrar; do
        install -m 0755 ${S}/tools/$t.py ${D}/opt/andon/
    done
    install -m 0755 ${S}/tools/modo.sh ${D}/opt/andon/

    # Nunca empaquetar bytecode generado en la PC de desarrollo
    find ${D} -name __pycache__ -type d -prune -exec rm -rf {} +
    find ${D} -name '*.pyc' -delete

    install -d ${D}${systemd_system_unitdir}
    for u in andon-sensores andon-core andon-web; do
        install -m 0644 ${WORKDIR}/$u.service ${D}${systemd_system_unitdir}/
    done

    install -d -m 0750 ${D}/var/lib/andon
    chown -R andon:andon ${D}/var/lib/andon

    # andon-web guarda los umbrales aquí (CU-07) con reemplazo atómico: necesita el directorio.
    # El archivo trae el PIN (D8): solo lo lee el usuario andon.
    chown -R andon:andon ${D}${sysconfdir}/andon
    chmod 0750 ${D}${sysconfdir}/andon
    chmod 0640 ${D}${sysconfdir}/andon/andon.conf
}

FILES:${PN} += " \
    /opt/andon \
    ${sysconfdir}/andon \
    /var/lib/andon \
    ${systemd_system_unitdir} \
"

RDEPENDS:${PN} += " \
    python3 \
    python3-flask \
    python3-paho-mqtt \
    python3-smbus2 \
    python3-gpiod \
    mosquitto \
    ollama-bin \
"
