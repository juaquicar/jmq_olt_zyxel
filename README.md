## Descripción

**`jmq_olt_zyxel`** es un paquete en Python que proporciona una interfaz basada en clases para conectar vía Telnet a un OLT Zyxel (modelo `OLT1408A`) y extraer información de las ONT (Optical Network Terminations) en estructuras de datos listas para serializar a JSON. Todo se realiza sin SNMP, únicamente mediante comandos Telnet y parseo de las salidas ASCII.

## Características principales

* Conexión y autenticación vía Telnet.
* Métodos:

  * `get_all_onts()` → lista ONT activas.
  * `get_unregistered_onts()` → lista ONT no registradas.
  * `get_ont_details(aid)` → detalles generales.
  * `get_ont_status_history(aid)` → historial de estado (status, timestamp).
  * `get_ont_config(aid)` → configuración dividida en bloques `ont` y `uni`.
* Parseo robusto de tablas ASCII y bloques clave\:valor.
* Salida en estructuras nativas de Python.

---

## Uso básico

### Inicialización y login

```python
from jmq_olt_zyxel.OLT1408A import APIOLT1408A

client = APIOLT1408A(
    host="152.170.74.208",
    port=2300,
    username="admin",
    password="1234",
    prompt="OLT1408A#",
    timeout=5
)
```

### Obtener todas las ONT

```python
all_onts = client.get_all_onts()
print(client.to_json(all_onts))
```

**Salida:**

```json
[
  {
    "AID": "ont-1-1",
    "SN": "5A5958458CADA659",
    "Template-ID": "Template-1-121",
    "Status": "IS",
    "FW Version": "V544ACHK1b1_20",
    "Model": "PX3321-T1",
    "Distance": "0 m",
    "ONT Rx": "-24.01",
    "Description": ""
  }
]
```

### Obtener ONT no registradas

```python
unreg = client.get_unregistered_onts()
print(client.to_json(unreg))
```

**Salida:**

```json
[]
```

### Obtener detalles de una ONT específica

```python
details = client.get_ont_details("ont-1-1")
print(client.to_json(details))
```

**Salida:**

```json
{
  "Status": "Down",
  "Estimated distance": "0 m",
  "OMCI GEM port": "0",
  "Model name": "N/A",
  "Model ID": "0",
  "Full bridge": "disable",
  "US FEC": "disable",
  "Alarm profile": "DEFVAL",
  "Anti MAC Spoofing": "disable",
  "Template Description": "Template-1-121",
  "Management IP Address": "N/A",
  "Ethernet 1": "Link Down",
  "Wan 1": "Enable",
  "Vlan": "10",
  "Control Supported": "WAN(full) LAN WiFi ACS ..."
}
```

### Obtener historial de estado

```python
history = client.get_ont_status_history("ont-1-1")
print(client.to_json(history))
```

**Salida:**

```json
[
  {"status": "IS",      "tt": "2037/ 3/14 16:02:16"},
  {"status": "OOS-NP",  "tt": "2037/ 3/14 16:02:16"},
  {"status": "OOS-CD",  "tt": "2037/ 3/14 16:02:07"},
  {"status": "OOS-NR",  "tt": "2037/ 3/14 16:01:25"}
]
```

### Obtener configuración avanzada

```python
config = client.get_ont_config("ont-1-1")
print(client.to_json(config))
```

**Salida:**

```json
{
  "ont": {
    "sn": "5A5958458CADA659",
    "password": "DEFAULT",
    "full_bridge": "disable",
    "template_description": "Template-1-121",
    "alarm_profile": "DEFVAL",
    "anti_mac_spoofing": "inactive",
    "bwgroup": "1",
    "usbwprofname": "DEFVAL",
    "dsbwprofname": "DEFVAL",
    "allocid": "256"
  },
  "uni": {
    "active": true,
    "pmenable": false,
    "queues": [
      {"tc": 0, "priority": 0, "weight": 0, "usbwprofname": "DEFVAL", "dsbwprofname": "DEFVAL", "dsoption": "olt", "bwsharegroupid": "1"},
      {"tc": 1, "priority": 2, "weight": 2, "usbwprofname": "DEFVAL", "dsbwprofname": "DEFVAL", "dsoption": "olt", "bwsharegroupid": "1"}
    ],
    "vlan": "1"
  }
}
```

### Cerrar sesión Telnet

```python
client.close()
```

---

## Referencia de la API

* `get_all_onts() -> List[Dict[str, Any]]`
* `get_unregistered_onts() -> List[Dict[str, Any]]`
* `get_ont_details(aid: str) -> Dict[str, Any]`
* `get_ont_status_history(aid: str) -> List[Dict[str, str]]`
* `get_ont_config(aid: str) -> Dict[str, Any]`
* `to_json(data: object) -> str`
* `close() -> None`

---

## Licencia

MIT License
