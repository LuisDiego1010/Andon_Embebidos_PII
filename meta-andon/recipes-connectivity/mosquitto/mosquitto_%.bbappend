# H1: 2895.patch hace que Mosquitto espere network-online.target. Sin DHCP eso lo
# retrasa 2 min. La app solo usa 127.0.0.1, así que volvemos al network.target original.
# No sirve un drop-in: systemd no permite quitar dependencias (After=, Wants=) desde uno.
SRC_URI:remove = "file://2895.patch"
