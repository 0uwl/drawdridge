# Kea Configuration

Drawbridge does not include an installation of Kea DHCP server. It assumes
you have an Ubuntu Server with Kea installed locally. This repository
includes example configurations for the DHCP server so that you can get the
Drawbridge service up and running as quickly as possible.

**Control Agent** (`kea/kea-ctrl-agent.conf`):
- Listens on `127.0.0.1:8081` — loopback only, not exposed externally
- The Drawbridge container reaches it via `http://keahost:8081` where `keahost`
  resolves to `host-gateway` via the Quadlet's `AddHost` directive

**DHCPv4** (`kea/kea-dhcp4.conf`):
- Provisioning subnet: `192.168.100.0/24`, pool `192.168.100.10–200`
- `deny-unknown-clients` equivalent via client class — unknown devices get
  no offer at all, not even a NAK
- Option 67 (`boot-file-name`) set to `https://<host-ip>:8080/scripts/ztp-base.py`
  only for devices in the `known` client class
- `leases4_committed` hook configured with the custom callout library
- `host_cmds` hook loaded to enable `reservation-add`/`reservation-del` via API

**`leases4_committed` hook behaviour:**
- POSTs to `http://127.0.0.1:8080/api/lease-event` synchronously (see
  [api.md](api.md) for the contract)
- On HTTP 200: sets next step to CONTINUE (unpark, send DHCPACK)
- On any other response or connection error: sets next step to DROP
- Timeout: 2 seconds — fail closed on timeout
