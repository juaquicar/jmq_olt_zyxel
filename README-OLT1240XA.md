# README-OLT1240XA.md — Uso de `APIOLT1240XA` (Zyxel MSC/OLT1240XA vía Telnet)

Cliente Python para interactuar con una **Zyxel MSC/OLT 1240XA** mediante **Telnet**, con parsing de salidas típicas de la CLI y métodos de consulta de ONTs.

Incluye correcciones específicas para el comportamiento real de la MSC/OLT1240XA observado en logs/salidas reales:
- **Manejo de ANSI/VT100**: auto-respuesta a `ESC[6n` con `ESC[1;1R` para evitar bloqueos de CLI.
- **Detección robusta de prompt**: el prompt puede venir sin salto de línea; se detecta al final del buffer.
- **Evita cortar por “prompt viejo”**: `require_progress` ignora buffers que son solo prompt/whitespace.
- **Debug opcional**: dumps en consola con timestamps y/o volcado RAW a fichero.
- **Enriquecimiento de potencia óptica (“ONT Rx”) en `get_all_onts(filter="1")`**:  
  además de `show interface remote ont filter 1`, ejecuta `show interface gpon 1-* ddmi status` y cruza `ont-<AID>` → `ONT Rx`.

---

## 1) Estructura esperada del paquete

Ejemplo:

```

jmq_olt_zyxel/
**init**.py
OLT1240XA.py
tests/
test1240XA.py

````

---

## 2) Dependencias

- Python 3.10+ recomendado.
- Nota: `telnetlib` está deprecado en Python recientes, pero sigue funcionando y es válido para este caso.

---

## 3) API pública disponible

Clase principal: `jmq_olt_zyxel.OLT1240XA.APIOLT1240XA`

Métodos:
- `get_all_onts(filter: str = "1") -> List[Dict[str, Any]]`  
  Ejecuta `show interface remote ont filter <filter>` y devuelve tabla parseada (ONTs registradas).  
  Para `filter="1"` enriquece con `"ONT Rx"` cruzando con DDMI (`show interface gpon 1-* ddmi status`).
- `get_unregistered_onts() -> List[Dict[str, Any]]`  
  Ejecuta `show interface remote ont unreg` y parsea formato real `Pon_AID | Type SN Password Status`.
- `get_ont_details(aid: str) -> Dict[str, Any]`  
  Ejecuta `show interface remote ont {aid} status` y devuelve un **dict plano** `clave: valor`.
- `get_ont_status_history(aid: str) -> List[Dict[str, Any]]`  
  Ejecuta `show interface remote ont {aid} status-history` y devuelve lista de eventos `{status, tt}`.
- `get_ont_config(aid: str) -> Dict[str, Any]`  
  Ejecuta `show interface remote ont {aid} config` y devuelve estructura:
  - `{"aid": "...", "ont": {...}, "uni": {"<aid>-...": {...}}}`
- `to_json(data) -> str`  
  Pretty-print JSON.
- `close() -> None`  
  Cierra sesión Telnet (intenta `exit`).

---

## 4) Parámetros de conexión

Constructor:

```python
client = APIOLT1240XA(
    host="IP_O_HOST",
    port=18104,
    username="admin",
    password="***",
    prompt="MSC1240XA#",
    timeout=30,
    debug=False,
    debug_telnet_dump=False,
    debug_telnet_raw_file="/tmp/olt1240xa_telnet_raw.log",
    eol=b"\r\n",
)
````

Parámetros relevantes:

* `prompt`: normalmente `"MSC1240XA#"`.
* `timeout`: timeout global de lectura/ejecución de comando.
* `debug`: habilita logs `[DEBUG]`.
* `debug_telnet_dump`: si `True`, imprime dumps de salida Telnet en consola (filtrando ANSI).
* `debug_telnet_raw_file`: si no es `None`, guarda volcado RAW en fichero (útil para forense).
* `eol`: por defecto `\r\n` para máxima compatibilidad con equipos.
* (si está implementado en tu versión) `ddmi_timeout`: timeout específico para el comando DDMI (`show interface gpon 1-* ddmi status`), recomendable si hay muchas PONs.

---

## 5) Ejecución de smoke test (manual)

Archivo: `tests/test1240XA.py`

### Código de ejemplo (tal cual)

```python
# -*- coding: utf-8 -*-
"""
tests/test1240XA.py

Test manual (smoke test) para la API de OLT/MSC1240XA.
Ejecuta (vía métodos de la API):
  - show interface remote ont filter 1
  - show interface remote ont unreg
  - show interface remote ont {aid} status
  - show interface remote ont {aid} status-history
  - show interface remote ont {aid} config
"""

from jmq_olt_zyxel.OLT1240XA import APIOLT1240XA

HOST = "X.X.X.X"
PORT = 23
USER = "admin"
PASS = "****"
PROMPT_BASE = "MSC1240XA#"

# AID de prueba (en 1240XA NO lleva prefijo "ont-": ejemplo real "2-16-40")
AID_TEST = "2-16-40"

if __name__ == "__main__":
    client = APIOLT1240XA(
        host=HOST,
        port=PORT,
        username=USER,
        password=PASS,
        prompt=PROMPT_BASE,
        timeout=30,
        debug=False,
    )

    try:
        # 1) Todas las ONTs registradas (filter 1)
        all_onts = client.get_all_onts("1")
        print("--- Todas las ONTs registradas (filter 1) ---")
        print(client.to_json(all_onts))

        # 2) ONTs no registradas (UnReg)
        unreg = client.get_unregistered_onts()
        print("--- ONTs no registradas (UnReg) ---")
        print(client.to_json(unreg))

        aid = AID_TEST

        if aid:
            # 3) Detalles de la ONT (status)
            details = client.get_ont_details(aid)
            print(f"--- get_ont_details - Detalles de la ONT {aid} (status) ---")
            print(client.to_json(details))

            # 4) Historial de estado de la ONT
            history = client.get_ont_status_history(aid)
            print(f"--- get_ont_status_history - Historial de estado de la ONT {aid} ---")
            print(client.to_json(history))

            # 5) Configuración de la ONT
            config = client.get_ont_config(aid)
            print(f"--- get_ont_config - Configuración de la ONT {aid} ---")
            print(client.to_json(config))
        else:
            print("No hay ONTs registradas (o no se pudo inferir AID) para probar detalles/historial/config.")

    finally:
        client.close()
```

### Ejecución

Desde la raíz del proyecto:

```bash
python3 tests/test1240XA.py
```

---

## 6) Salida esperada (ejemplo real)

A continuación se documenta un ejemplo de salida **real** (tal y como has proporcionado), para validar que las llamadas y el parsing son correctos.

### 6.1 `get_all_onts("1")` — Todas las ONTs registradas (filter 1) + ONT Rx

**Llamada:**

```python
all_onts = client.get_all_onts("1")
print(client.to_json(all_onts))
```

**Respuesta:**

```json
[
  {
    "AID": "1-1-1",
    "SN": "5A5965563E1539B0",
    "Password": "DEFAULT",
    "Status": "Active",
    "Model": "| 1 V V540ABNA2E0a06 | ZYeV",
    "Type": "Config",
    "ONT Rx": "-24.81"
  },
  {
    "AID": "1-1-10",
    "SN": "5A59495397426AA0",
    "Password": "DEFAULT",
    "Status": "Active",
    "Model": "| 1 V540ABNA2E0a06 | ZYIS",
    "Type": "Config",
    "ONT Rx": "-25.73"
  },
  {
    "AID": "1-1-11",
    "SN": "5A5949539741B300",
    "Password": "DEFAULT",
    "Status": "Active",
    "Model": "| 1 V V540ABNA2E0a12 | ZYIS",
    "Type": "Config",
    "ONT Rx": "-30.71"
  },
  {
    "AID": "1-1-12",
    "SN": "5A59495397427DC0",
    "Password": "DEFAULT",
    "Status": "Active",
    "Model": "| 1 V V540ABNA1b4 | ZYIS",
    "Type": "Config",
    "ONT Rx": "-33.01"
  },
  {
    "AID": "1-1-13",
    "SN": "5A5949539741D9F0",
    "Password": "DEFAULT",
    "Status": "Active",
    "Model": "| 1 V V540ABNA2E0a12 | ZYIS",
    "Type": "Config",
    "ONT Rx": "-25.02"
  }
]
```

**Nota sobre ONT Rx**
El campo `"ONT Rx"` se obtiene ejecutando:

* `show interface gpon 1-* ddmi status`

y parseando líneas del estilo:

```
ont-1-1-10              -25.27
ont-1-1-12       -      -32.80
ont-1-10-28     ++       -7.06
```

Luego se cruza con el listado `filter 1` por `ont-<AID>`.

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
    "Pon_AID": "pon-5-10",
    "Type": "UnReg",
    "SN": "5A59454AF38F74D0",
    "Password": "DEFAULT",
    "Status": "Active"
  },
  {
    "Pon_AID": "pon-5-15",
    "Type": "UnReg",
    "SN": "5A5955501648EB50",
    "Password": "DEFAULT",
    "Status": "Active"
  }
]
```

---

### 6.3 `get_ont_details(aid)` — Detalles de ONT (dict plano)

**Llamada:**

```python
details = client.get_ont_details("2-16-40")
print(client.to_json(details))
```

**Respuesta:**

```json
{
  "Status": "OOS-Loss of Signal (2d 23h 6m 3s)",
  "Estimated distance": "0 m",
  "OMCI GEM port": "0",
  "Model name": "PMG5617T20B2",
  "Model ID": "5",
  "Full bridge": "disable",
  "US FEC": "disable",
  "Alarm profile": "DEFVAL",
  "Anti MAC Spoofing": "disable",
  "Planned Version": "actualizar",
  "Template Description": "100Megas"
}
```

---

### 6.4 `get_ont_status_history(aid)` — Historial de estado

**Llamada:**

```python
history = client.get_ont_status_history("2-16-40")
print(client.to_json(history))
```

**Respuesta:**

```json
[
  { "status": "OOS-LS", "tt": "2026/ 1/16 9:18:27" },
  { "status": "IS", "tt": "2026/ 1/15 18:54:46" },
  { "status": "OOS-NP", "tt": "2026/ 1/15 18:54:46" },
  { "status": "OOS-CD", "tt": "2026/ 1/15 18:54:23" },
  { "status": "OOS-DG", "tt": "2026/ 1/15 18:52:39" }
]
```

---

### 6.5 `get_ont_config(aid)` — Configuración de ONT + UNI blocks

**Llamada:**

```python
config = client.get_ont_config("2-16-40")
print(client.to_json(config))
```

**Respuesta:**

```json
{
  "aid": "2-16-40",
  "ont": {
    "inactive": false,
    "sn": "5A5958458CAEF052",
    "password": "b1",
    "description": "472Y86",
    "template_description": "100Megas",
    "plan_version": "actualizar",
    "alarm_profile": "DEFVAL",
    "anti_mac_spoofing": "inactive",
    "bwgroup": "1",
    "usbwprofname": "50Megas",
    "dsbwprofname": "50Megas",
    "lines": [
      "ontServiceControl ftp enable LAN",
      "ontServiceControl ftp port 21",
      "ontServiceControl http enable ALL",
      "ontServiceControl http port 80",
      "ontServiceControl https enable LAN",
      "ontServiceControl https port 443",
      "ontServiceControl icmp enable LAN",
      "ontServiceControl snmp enable LAN",
      "ontServiceControl snmp port 161",
      "ontServiceControl ssh enable LAN",
      "ontServiceControl ssh port 22",
      "ontServiceControl telnet enable LAN",
      "ontServiceControl telnet port 23",
      "connection-type pppoe username 472Y86 password 472Y86",
      "default",
      "enable",
      "exit",
      "binding wifi 2.4g 2",
      "enable",
      "exit",
      "ontWifi 2.4g 2",
      "b1$C6(d4#",
      "exit"
    ],
    "ontwan": "3",
    "vlans": [
      { "vlan": "107", "priority": "0", "mvlan": "107" },
      { "vlan": "4000", "priority": "0", "mvlan": "4000" }
    ],
    "service": "data",
    "ip": "nat",
    "connection_type": "bridge",
    "enable": "2",
    "ssid": "lec_med"
  },
  "uni": {
    "2-16-40-2-1": {
      "inactive": false,
      "pmenable": false,
      "queues": [
        {
          "tc": 0,
          "priority": 0,
          "weight": 0,
          "usbwprofname": "50Megas",
          "dsbwprofname": "50Megas",
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
      "lines": [ "1" ],
      "vlans": [
        { "vlan": "41", "ingprof": "cero", "network": "41", "gemport": "373", "aesencrypt": "disable" },
        { "vlan": "104", "ingprof": "cero", "network": "104", "gemport": "374", "aesencrypt": "disable" },
        { "vlan": "107", "ingprof": "cero", "network": "107", "gemport": "375", "aesencrypt": "disable" }
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
client = APIOLT1240XA(..., debug=True)
```

Obtendrás mensajes tipo:

* `[DEBUG] Abriendo sesión Telnet...`
* `[DEBUG] _send_command: preparando comando=...`
* `[DEBUG] _read_until_prompt: prompt detectado al final del buffer.`

### 7.2 Dumps de Telnet en consola (START/END)

Activa ambos:

```python
client = APIOLT1240XA(..., debug=True, debug_telnet_dump=True)
```

La salida se imprime filtrando ANSI para evitar que tu terminal interprete secuencias como `^[[25;1R`.

### 7.3 Volcado RAW exacto a fichero

```python
client = APIOLT1240XA(..., debug=True, debug_telnet_raw_file="/tmp/olt1240xa_telnet_raw.log")
```

Útil cuando:

* el prompt llega “pegado” al output,
* hay caracteres invisibles,
* hay negociación ANSI/VT100 adicional.

### 7.4 `get_all_onts("1")` tarda demasiado (por DDMI)

El enriquecimiento de `"ONT Rx"` ejecuta `show interface gpon 1-* ddmi status`, que puede generar un output muy grande.

Mitigaciones recomendadas:

* Aumentar el timeout global `timeout`, o (si existe) `ddmi_timeout`.
* Si tu implementación lo permite, añadir un flag para desactivar enriquecimiento y llamar solo a `filter 1`.

---

## 8) Consideraciones operativas y de seguridad

* **Telnet no cifra**: usa esta API únicamente en entornos controlados (VPN/red de gestión) y evita exponer el puerto a Internet.
* No hardcodees credenciales en repos públicos; usa variables de entorno o un `.env`.
* Si necesitas rotación de credenciales o multi-OLT, encapsula configuración en un loader externo.

---

## 9) Ejemplo mínimo de uso (sin test completo)

```python
from jmq_olt_zyxel.OLT1240XA import APIOLT1240XA

client = APIOLT1240XA(
    host="201.251.78.101",
    port=18104,
    username="admin",
    password="***",
    prompt="MSC1240XA#",
    timeout=30,
    debug=False,
)

try:
    onts = client.get_all_onts("1")  # incluye "ONT Rx"
    print(client.to_json(onts))

    aid = "2-16-40"
    details = client.get_ont_details(aid)
    print(client.to_json(details))
finally:
    client.close()
```

---

## 10) Notas sobre parsing (para mantenimiento)

* `get_all_onts(filter)` parsea la tabla de `show interface remote ont filter <filter>`:

  * Consolidación `Config`/`Actual` por `AID` (prioriza `Actual`).
* Enriquecimiento de `"ONT Rx"` (para `filter="1"`):

  * Ejecuta `show interface gpon 1-* ddmi status`
  * Parseo de líneas `ont-<AID>  <alarm?>  <rx>`
  * Cruce por `ont-<AID>` contra el listado `filter 1`.
* `get_unregistered_onts()` parsea el formato determinista `Pon_AID | ...`.
* `get_ont_details()` devuelve **salida plana** `Dict[str, Any]` (parseo por `:`).
* `get_ont_config()` construye estructura `ont/uni` parseando líneas tipo:

  * `queue tc ...`
  * `vlan ...`
  * `bwgroup ...`
  * y líneas no clasificadas en `lines`.


