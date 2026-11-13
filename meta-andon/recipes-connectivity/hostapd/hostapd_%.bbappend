# Punto de acceso Andon-E1 (docs/yocto-requisitos.md, notas v2). La configuración vive en la app,
# app/deploy/red/hostapd.conf, y reemplaza la de ejemplo que instala la receta.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:${THISDIR}/../../../app/deploy/red:"
SRC_URI += "file://hostapd.conf file://andon-wlan0.conf"

SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install:append() {
    # 0600: trae la clave de la red Wi-Fi
    install -m 0600 ${WORKDIR}/hostapd.conf ${D}${sysconfdir}/hostapd.conf
    install -d ${D}${systemd_system_unitdir}/hostapd.service.d
    install -m 0644 ${WORKDIR}/andon-wlan0.conf ${D}${systemd_system_unitdir}/hostapd.service.d/
}

FILES:${PN} += "${systemd_system_unitdir}/hostapd.service.d"
