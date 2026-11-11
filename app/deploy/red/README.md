# Red Wi-Fi de la estación (punto de acceso propio)

La propuesta (Tablas 4, 7 y 8) promete que el operario abre el formulario desde su celular,
conectado a una red Wi-Fi propia de la estación, sin Internet. Esta carpeta la define. Hasta la demo
no tiene recetas propias: la receta de la imagen copia los archivos (ver `docs/yocto-requisitos.md`, v2).

| Archivo | Destino en la placa | Qué hace |
|---|---|---|
| `hostapd.conf` | `/etc/hostapd.conf` | Red `Andon-E1`, WPA2, canal 6, país CR |
| `dnsmasq.conf` | `/etc/dnsmasq.conf` | DHCP `192.168.4.10–50`; `andon.lan` → `192.168.4.1`; sin reenvío a Internet |
| `10-wlan0.network` | `/etc/systemd/network/10-wlan0.network` | IP fija `192.168.4.1/24` en `wlan0` |

Servicios habilitados: `hostapd.service` y `dnsmasq.service`. La web ya escucha en `0.0.0.0:5000`.

**Antes de la demo:** cambiar `wpa_passphrase` en `hostapd.conf`. El repositorio es público.

## Comprobación en la placa (paso B2 del plan)

```sh
rfkill list                        # wlan: Soft blocked: no
networkctl status wlan0            # 192.168.4.1/24, «routable» o «carrier»
systemctl status hostapd dnsmasq   # active (running)
journalctl -u hostapd -b | tail    # «AP-ENABLED»
```
Desde el celular:
1. Conectarse a `Andon-E1`. El celular avisará «sin Internet»; elegir **mantener la conexión**.
2. Abrir `http://192.168.4.1:5000`. Probar también `http://andon.lan:5000`: algunos celulares con
   «DNS privado» activado no lo resuelven, y la IP funciona siempre.
3. En la placa, `cat /var/lib/misc/dnsmasq.leases` (o la ruta que use la receta) muestra el celular.

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| hostapd: `Could not set channel` / `nl80211: Could not configure driver mode` | Falta el firmware `bcm43455` (`linux-firmware-rpidistro-bcm43455`) o wpa_supplicant tiene tomada `wlan0` |
| hostapd no arranca y `rfkill` dice `Soft blocked: yes` | `rfkill unblock wlan` (y que la imagen lo deje desbloqueado) |
| El celular se conecta pero no recibe IP | dnsmasq no está activo o `wlan0` no tiene `192.168.4.1` (revisar `networkctl`) |
| La red no aparece en el celular | Canal o país: probar `channel=1` |
