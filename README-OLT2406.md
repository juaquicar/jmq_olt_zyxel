# README-OLT2406.md — Uso de `APIOLT2406` (Zyxel OLT2406 vía Telnet)

Cliente Python para interactuar con una **OLT Zyxel OLT2406** mediante **Telnet**, con parsing de salidas típicas de la CLI y métodos de consulta de ONTs.

Incluye correcciones específicas para el comportamiento real de la OLT2406 observado en logs:
- **Manejo de ANSI/VT100**: auto-respuesta a `ESC[6n` con `ESC[1;1R` para evitar bloqueos de CLI.
- **Detección robusta de prompt**: el prompt puede venir sin salto de línea; se detecta al final del buffer.
- **Evita cortar por “prompt viejo”**: `require_progress` ignora buffers que son solo prompt/whitespace.
- **Debug opcional**: dumps en consola con timestamps y/o volcado RAW a fichero.

---

## 1) Estructura esperada del paquete

Ejemplo:

```

jmq_olt_zyxel/
**init**.py
OLT2406.py
tests/
test2406.py

````

---

## 2) Dependencias

- Python 3.10+ recomendado (en tu entorno se ve Python moderno).
- Nota: `telnetlib` está deprecado en Python recientes, pero sigue funcionando y es válido para este caso.

---

## 3) API pública disponible

Clase principal: `jmq_olt_zyxel.OLT2406.APIOLT2406`

Métodos:
- `get_all_onts() -> List[Dict[str, Any]]`  
  Ejecuta `show remote ont` y devuelve tabla parseada (ONTs registradas).
- `get_unregistered_onts() -> List[Dict[str, Any]]`  
  Ejecuta `show remote ont unreg` y parsea formato real `Pon_AID | Type SN Password Status`.
- `get_ont_details(aid: str) -> Dict[str, Any]`  
  Ejecuta `show remote ont {aid}` y devuelve un **dict plano** `clave: valor` (estilo OLT1408A).
- `get_ont_status_history(aid: str) -> List[Dict[str, Any]]`  
  Ejecuta `show remote ont {aid} status-history` y devuelve lista de eventos `{status, tt}`.
- `get_ont_config(aid: str) -> Dict[str, Any]`  
  Ejecuta `show remote ont {aid} config` y devuelve estructura:
  - `{"aid": "...", "ont": {...}, "uni": {"uniport-...": {...}}}`
- `to_json(data) -> str`  
  Pretty-print JSON.
- `close() -> None`  
  Cierra sesión Telnet (intenta `exit`).

---

## 4) Parámetros de conexión

Constructor:

```python
client = APIOLT2406(
    host="IP_O_HOST",
    port=18103,
    username="admin",
    password="***",
    prompt="OLT2406#",
    timeout=30,
    debug=False,
    debug_telnet_dump=False,
    debug_telnet_raw_file="/tmp/olt2406_telnet_raw.log",
    eol=b"\r\n",
)
````

Parámetros relevantes:

* `prompt`: normalmente `"OLT2406#"` (puede llegar con o sin espacio).
* `timeout`: timeout global de lectura/ejecución de comando.
* `debug`: habilita logs `[DEBUG]`.
* `debug_telnet_dump`: si `True`, imprime dumps de salida Telnet en consola (filtrando ANSI).
* `debug_telnet_raw_file`: si no es `None`, guarda volcado RAW en fichero (útil para forense).
* `eol`: por defecto `\r\n` para máxima compatibilidad con equipos.

---

## 5) Ejecución de smoke test (manual)

Archivo: `tests/test2406.py`

### Código de ejemplo (tal cual)

```python
# -*- coding: utf-8 -*-
"""
tests/test2406.py

Test manual (smoke test) para la API de OLT2406.
Ejecuta:
  - show remote ont
  - show remote ont unreg
  - show remote ont {aid}
  - show remote ont {aid} status-history
  - show remote ont {aid} config
"""

from jmq_olt_zyxel.OLT2406 import APIOLT2406

HOST = "XX.XX.XX.XX"
PORT = 18103
USER = "admin"
PASS = "***"
PROMPT_BASE = "OLT2406#"

AID_TEST = "ont-3-1-1"

if __name__ == "__main__":
    client = APIOLT2406(
        host=HOST,
        port=PORT,
        username=USER,
        password=PASS,
        prompt=PROMPT_BASE,
        timeout=30,
        debug=False,
    )

    try:
        # 1) Todas las ONTs registradas
        all_onts = client.get_all_onts()
        print("--- Todas las ONTs registradas ---")
        print(client.to_json(all_onts))

        # 2) ONTs no registradas (UnReg)
        unreg = client.get_unregistered_onts()
        print("--- ONTs no registradas ---")
        print(client.to_json(unreg))

        aid = AID_TEST
        if aid:
            # 3) Detalles de la ONT
            details = client.get_ont_details(aid)
            print(f"--- get_ont_details - Detalles de la ONT {aid} ---")
            print(client.to_json(details))

            # 4) Historial de estado de la ONT
            history = client.get_ont_status_history(aid)
            print(f"--- get_ont_status_history - Historial de estado de la ONT {aid} ---")
            print(client.to_json(history))

            # 5) Configuración de la ONT
            config = client.get_ont_config(aid)
            print(f"--- get_ont_config -Configuración de la ONT {aid} ---")
            print(client.to_json(config))
        else:
            print("No hay ONTs registradas (o no se pudo inferir AID) para probar detalles/historial/config.")

    finally:
        client.close()
```

### Ejecución

Desde la raíz del proyecto:

```bash
python tests/test2406.py
```

---

## 6) Salida esperada (ejemplo real)

A continuación se documenta un ejemplo de salida **real** (tal y como has proporcionado), para validar que las llamadas y el parsing son correctos.

### 6.1 `get_all_onts()` — Todas las ONTs registradas

**Llamada:**

```python
all_onts = client.get_all_onts()
print(client.to_json(all_onts))
```

**Respuesta:**

```json
[
  {
    "AID": "ont-6-4-52",
    "SN": "5A5958458CAEF993",
    "Template-ID": "",
    "Status": "IS",
    "FW Version": "V541ACBB1E0a03",
    "Model": "PMG5617T20B2",
    "Distance": "7650 m",
    "ONT Rx": "-25.81",
    "Description": "470766"
  },
  {
    "AID": "ont-6-4-53",
    "SN": "5A5955501648E760",
    "Template-ID": "",
    "Status": "IS",
    "FW Version": "V540ABNA1C01",
    "Model": "PMG5617GA",
    "Distance": "7854 m",
    "ONT Rx": "-25.49",
    "Description": "470326"
  },
  {
    "AID": "ont-6-4-54",
    "SN": "5A5958458CAEEF92",
    "Template-ID": "",
    "Status": "IS",
    "FW Version": "V541ACBB1E0a06",
    "Model": "PMG5617T20B2",
    "Distance": "7854 m",
    "ONT Rx": "-26.29",
    "Description": "470B45"
  }
]
```

---

### 6.2 `get_unregistered_onts()` — ONTs no registradas (UnReg)

**Llamada:**

```python
unreg = client.get_unregistered_onts()
print(client.to_json(unreg))
```

**Respuesta:**

```json
[
  {
    "Pon_AID": "pon-3-3",
    "Type": "UnReg",
    "SN": "5A59495397426460",
    "Password": "DEFAULT",
    "Status": "Active"
  },
  {
    "Pon_AID": "pon-5-2",
    "Type": "UnReg",
    "SN": "5A5958458CACCBFB",
    "Password": "DEFAULT",
    "Status": "Active"
  }
]
```

---

### 6.3 `get_ont_details(aid)` — Detalles de ONT (dict plano)

**Llamada:**

```python
details = client.get_ont_details("ont-3-1-1")
print(client.to_json(details))
```

**Respuesta:**

```json
{
  "Status": "Up",
  "Estimated distance": "7752 m",
  "OMCI GEM port": "1",
  "Model name": "PMG5317-T20B",
  "Model ID": "5",
  "Full bridge": "disable",
  "US FEC": "disable",
  "Alarm profile": "DEFVAL",
  "Anti MAC Spoofing": "disable",
  "Planned Version": "actualizar",
  "Description": "",
  "Template Description": "",
  "Management IP Address": "N/A",
  "POTS/VoIP 1": "On-hook      INITIAL",
  "POTS/VoIP 2": "On-hook      INITIAL",
  "Wan 1": "Enable",
  "Connection Type": "IPoE",
  "Nat": "Enable",
  "Service": "Data",
  "Vlan": "41",
  "Priority": "0",
  "MVLAN": "",
  "Auto get IP": "Enable",
  "IP address": "10.233.83.19",
  "IP Mask": "255.255.240.0",
  "Gateway": "10.233.80.1",
  "Primary DNS": "10.233.80.1",
  "Secondary DNS": "0.0.0.0",
  "Wan 2": "Enable",
  "Wan 3": "Disable",
  "Wan 4": "Disable",
  "Wan 5": "Disable",
  "Wan 6": "Disable",
  "Wan 7": "Disable",
  "Control Supported": "WAN(partial)"
}
```

---

### 6.4 `get_ont_status_history(aid)` — Historial de estado

**Llamada:**

```python
history = client.get_ont_status_history("ont-3-1-1")
print(client.to_json(history))
```

**Respuesta:**

```json
[
  { "status": "IS", "tt": "2026/ 1/14 18:01:53" },
  { "status": "OOS-NP", "tt": "2026/ 1/14 18:01:50" },
  { "status": "OOS-CD", "tt": "2026/ 1/14 18:01:32" },
  { "status": "OOS-DG", "tt": "2026/ 1/14 17:43:38" },
  { "status": "IS", "tt": "2026/ 1/14 17:40:38" },
  { "status": "OOS-NP", "tt": "2026/ 1/14 17:40:37" },
  { "status": "OOS-CD", "tt": "2026/ 1/14 17:40:22" },
  { "status": "OOS-DG", "tt": "2026/ 1/14 16:44:42" },
  { "status": "IS", "tt": "2026/ 1/14 2:23:02" },
  { "status": "OOS-NP", "tt": "2026/ 1/14 2:23:02" },
  { "status": "OOS-CD", "tt": "2026/ 1/14 2:22:20" },
  { "status": "OOS-NR", "tt": "2026/ 1/14 2:21:05" },
  { "status": "IS", "tt": "2026/ 1/13 10:52:51" },
  { "status": "OOS-NP", "tt": "2026/ 1/13 10:52:44" },
  { "status": "OOS-CD", "tt": "2026/ 1/13 10:51:34" },
  { "status": "OOS-NR", "tt": "2026/ 1/13 10:50:16" }
]
```

---

### 6.5 `get_ont_config(aid)` — Configuración de ONT + UNI ports

**Llamada:**

```python
config = client.get_ont_config("ont-3-1-1")
print(client.to_json(config))
```

**Respuesta:**

```json
{
  "aid": "ont-3-1-1",
  "ont": {
    "inactive": false,
    "sn": "5A594B4C735BA550",
    "password": "b1|b1$C6(d4#",
    "full_bridge": "disable",
    "plan_version": "actualizar",
    "alarm_profile": "DEFVAL",
    "anti_mac_spoofing": "inactive",
    "bwgroup": "1",
    "usbwprofname": "30_Megas",
    "dsbwprofname": "30_Megas",
    "allocid": "256",
    "ontwan": "3",
    "vlans": [
      { "vlan": "4000" }
    ],
    "connection_type": "bridge",
    "lines": [
      "binding wifi 2.4g 2",
      "enable",
      "exit",
      "ontWifi 2.4g 2",
      "exit"
    ],
    "enable": "2",
    "ssid": "lec_med"
  },
  "uni": {
    "uniport-3-1-1-2-1": {
      "inactive": false,
      "pmenable": false,
      "queues": [
        {
          "tc": 0,
          "priority": 0,
          "weight": 0,
          "usbwprofname": "30_Megas",
          "dsbwprofname": "30_Megas",
          "dsoption": "olt"
        },
        {
          "tc": 1,
          "priority": 0,
          "weight": 0,
          "usbwprofname": "256k",
          "dsbwprofname": "256k",
          "dsoption": "olt",
          "bwsharegroupid": 1
        }
      ],
      "id": "1",
      "vlans": [
        {
          "vlan": "41",
          "network": "41",
          "gemport": "257",
          "ingprof": "alltc0",
          "aesencrypt": "disable"
        },
        {
          "vlan": "103",
          "gemport": "258",
          "ingprof": "alltc0",
          "aesencrypt": "disable"
        },
        {
          "vlan": "4000",
          "gemport": "369",
          "ingprof": "alltc1",
          "aesencrypt": "disable"
        }
      ]
    }
  }
}
```

---

## 7) Debug y troubleshooting

### 7.1 Ver trazas de debug (alto nivel)

Activa `debug=True`:

```python
client = APIOLT2406(..., debug=True)
```

Obtendrás mensajes tipo:

* `[DEBUG] Abriendo sesión Telnet...`
* `[DEBUG] _send_command: preparando comando=...`
* `[DEBUG] _read_until_prompt: prompt detectado al final del buffer.`

### 7.2 Dumps de Telnet en consola (START/END)

Activa ambos:

```python
client = APIOLT2406(..., debug=True, debug_telnet_dump=True)
```

La salida se imprime filtrando ANSI para evitar que tu terminal “interprete” secuencias como `^[[25;1R`.

### 7.3 Volcado RAW exacto a fichero

```python
client = APIOLT2406(..., debug=True, debug_telnet_raw_file="/tmp/olt2406_telnet_raw.log")
```

Esto es útil cuando:

* el prompt llega “pegado” al output,
* hay caracteres invisibles,
* hay negociación ANSI/VT100 extra.

---

## 8) Consideraciones operativas y de seguridad

* **Telnet no cifra**: usa esta API únicamente en entornos controlados (VPN/Red de gestión), y evita exponer el puerto a Internet.
* No hardcodees credenciales en repos públicos; usa variables de entorno o un `.env`.
* Si necesitas rotación de credenciales o multi-OLT, encapsula configuración en un loader externo.

---

## 9) Ejemplo mínimo de uso (sin test completo)

```python
from jmq_olt_zyxel.OLT2406 import APIOLT2406

client = APIOLT2406(
    host="20.20.20.20",
    port=18103,
    username="admin",
    password="***",
    prompt="OLT2406#",
    timeout=30,
    debug=False,
)

try:
    onts = client.get_all_onts()
    print(client.to_json(onts))

    aid = "ont-3-1-1"
    details = client.get_ont_details(aid)
    print(client.to_json(details))
finally:
    client.close()
```

---

## 10) Notas sobre parsing (para mantenimiento)

* `get_all_onts()` usa `_parse_table_any(...)` y detecta headers de tabla dinámicamente.
* `get_unregistered_onts()` usa `_parse_unreg_onts(...)` (determinista por el formato real `Pon_AID | ...`).
* `get_ont_details()` devuelve **salida plana** `Dict[str, Any]` (estilo OLT1408A).
* `get_ont_config()` construye estructura `ont/uni` parseando líneas tipo:

  * `queue tc ...`
  * `vlan ...`
  * `bwgroup ...`
  * y líneas no clasificadas en `lines`.

---

### Licencia / responsabilidad

Este módulo ejecuta comandos en equipos de red. Úsalo bajo tus procedimientos de operación y cambios.

