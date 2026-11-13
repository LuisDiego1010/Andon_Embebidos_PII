# DHCP y nombre andon.lan del punto de acceso (docs/yocto-requisitos.md, notas v2). La configuración
# vive en la app, app/deploy/red/dnsmasq.conf; al estar primero en la ruta reemplaza a la de la receta.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:${THISDIR}/../../../app/deploy/red:"
SRC_URI += "file://andon-reintentar.conf"

SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install:append() {
    install -d ${D}${systemd_system_unitdir}/dnsmasq.service.d
    install -m 0644 ${WORKDIR}/andon-reintentar.conf ${D}${systemd_system_unitdir}/dnsmasq.service.d/
}

FILES:${PN} += "${systemd_system_unitdir}/dnsmasq.service.d"
