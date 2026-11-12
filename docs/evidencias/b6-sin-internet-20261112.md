# B6 · Sin Internet (REQ-N01) · RPi 4, imagen final, 12 nov 2026

Resultado: ✅ la estación no tiene salida a Internet ni conexiones salientes.

- Rutas IPv4: solo `192.168.4.0/24 dev wlan0` (punto de acceso). **Sin ruta por defecto.**
- IPv6: solo enlace local (`fe80::/64`) en wlan0 y eth0.
- `ping -c 1 1.1.1.1` → `Network is unreachable`; `wget http://example.com` → `bad address` (no resuelve).
- Conexiones TCP establecidas: solo entre procesos locales (`127.0.0.1`: Mosquitto, Ollama, servicios) y la sesión
  SSH de prueba por el cable (enlace local IPv6).
- Puertos a la escucha:
  - solo local: Mosquitto 1883, Ollama 11434, DNS local 53;
  - hacia la red del punto de acceso: web 5000, DNS 53 y DHCP 67 (dnsmasq), SSH 22, mDNS 5353;
  - **observación:** `rpcbind` (111) escucha en todas las interfaces y la app no lo usa. No afecta a REQ-N01;
    conviene quitarlo de la imagen.
- `/etc/resolv.conf` (systemd-resolved) trae los DNS públicos de respaldo por defecto, pero sin ruta no se alcanzan.
