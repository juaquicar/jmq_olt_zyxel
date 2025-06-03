## Descripción

**`jmq_olt_zyxel`** es un paquete en Python que proporciona una interfaz basada en clases para conectar vía Telnet a un OLT Zyxel (por ejemplo, modelo `OLT1408A`) y extraer información de las ONT (Optical Network Terminations) en formato JSON. Todo se realiza sin SNMP, únicamente mediante comandos Telnet y parseo de las salidas ASCII devueltas por el dispositivo.

La clase principal se encuentra en:

```
jmq_olt_zyxel/OLT1408A.py
```

y se llama:

```python
class APIOLT1408A
```

---

## Tabla de contenidos

1. [Características principales](#características-principales)
2. [Requisitos](#requisitos)
3. [Instalación](#instalación)
4. [Estructura del proyecto](#estructura-del-proyecto)
5. [Uso básico](#uso-básico)

   1. [Inicialización y login](#inicialización-y-login)
   2. [Obtener todas las ONT](#obtener-todas-las-ont)
   3. [Obtener detalles de una ONT específica](#obtener-detalles-de-una-ont-específica)
   4. [Cerrar la sesión Telnet](#cerrar-la-sesión-telnet)
6. [Referencia de la API](#referencia-de-la-api)

   1. [`__init__(...)`](#init)
   2. [`send_command(cmd: str) → str`](#send_commandcmd-str--str)
   3. [`get_all_onts() → List[Dict[str, str]]`](#get_all_onts--listdictstr-str)
   4. [`get_ont_details(aid: str) → Dict[str, object]`](#get_ont_detailsaid-str--dictstr-object)
   5. [`close()`](#close)
   6. [`to_json(data: object, indent: int = 2) → str`](#to_jsondata-object-indent-int--2--str)
7. [Ejemplos de salida JSON](#ejemplos-de-salida-json)

   1. [Formato de `get_all_onts()`](#formato-de-get_all_onts)
   2. [Formato de `get_ont_details("ont-1-2")`](#formato-de-get_ont_detailsont-1-2)
8. [Diseño y consideraciones de parseo](#diseño-y-consideraciones-de-parseo)
9. [Pruebas y desarrollo](#pruebas-y-desarrollo)
10. [Cómo contribuir](#cómo-contribuir)
11. [Licencia](#licencia)

---

## Características principales

* Conexión y autenticación vía **Telnet** (sin SNMP).
* Parametrización completa del prompt de dispositivo (por ejemplo, `"OLT1408A#"`).
* Métodos para:

  * Listar todas las ONT activas con `show remote ont` (parseo de tabla).
  * Obtener detalles profundos de una ONT (`show remote ont <AID>`, `show remote ont <AID> config`, `show remote ont <AID> status-history`).
* Parseo de tablas ASCII y bloques de detalles en líneas clave\:valor.
* Salida en estructuras de datos (listas y diccionarios) fácilmente serializables a JSON.
* Ejemplo de uso y método auxiliar `to_json(...)` para convertir a JSON formateado.

---

## Requisitos

* **Python** ≥ 3.7
* Dependencias (todas disponibles en PyPI):

  * `telnetlib` (incluida en la librería estándar)
  * `json` (incluida en la librería estándar)
  * Módulos comunes: `re`, `time`, `typing` (todos estándar en Python).

> **Importante**: Asegúrate de que el OLT Zyxel esté accesible por Telnet en el puerto adecuado (por defecto, Zyxel suele usar puerto **2300** en modelos `OLT1408A`, pero esto puede variar). Verifica que las credenciales de Telnet (usuario y contraseña) estén correctamente definidas en el constructor de la clase.

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu_organizacion/jmq_olt_zyxel.git
cd jmq_olt_zyxel
```

Si prefieres instalarlo globalmente o en un entorno virtual, puedes usar:

```bash
pip install .
```

ó, directamente desde GitHub:

```bash
pip install git+https://github.com/tu_organizacion/jmq_olt_zyxel.git
```

### 2. Instalación manual (modo editable)

Si quieres modificar el código y que los cambios se reflejen en tu entorno, instala en modo editable:

```bash
pip install -e .
```

Así podrás editar `jmq_olt_zyxel/OLT1408A.py` y probar los cambios sin reinstalar.

---

## Estructura del proyecto

```
jmq_olt_zyxel/
├── jmq_olt_zyxel/
│   ├── __init__.py
│   └── OLT1408A.py
├── tests/
│   ├── __init__.py
│   └── test_olt1408a.py
├── README.md
├── setup.py            # ó pyproject.toml
└── LICENSE
```

* **`jmq_olt_zyxel/OLT1408A.py`**: contiene la clase principal `APIOLT1408A`.
* **`tests/`**: tests unitarios (por ejemplo, usando `unittest.mock` para simular respuestas Telnet).
* **`setup.py` o `pyproject.toml`**: configuración para empaquetar e instalar.
* **`README.md`**: esta documentación.
* **`LICENSE`**: archivo de licencia (MIT, Apache o la que prefieras).

---

## Uso básico

A continuación se muestran los pasos mínimos necesarios para conectar al OLT, listar las ONT y obtener detalles.

### Inicialización y login

```python
from jmq_olt_zyxel.OLT1408A import APIOLT1408A

# Parámetros de conexión
HOST     = "152.170.97.181"      # IP del OLT Zyxel
PORT     = 2300                 # Puerto Telnet (por defecto Zyxel 2300)
USERNAME = "admin"
PASSWORD = "tu_password"
PROMPT   = "OLT1408A#"

# Instanciar el cliente
client = APIOLT1408A(
    host=HOST,
    port=PORT,
    username=USERNAME,
    password=PASSWORD,
    prompt=PROMPT,
    timeout=10                # (opcional) timeout en segundos para read_until
)

# En este punto, client.tn ya está autenticado y listo para enviar comandos.
```

### Obtener todas las ONT

```python
# Llama a show remote ont y parsea la tabla resumida.
all_onts = client.get_all_onts()

# all_onts es una lista de diccionarios, p. ej.:
# [
#   {
#     "AID": "ont-1-2",
#     "SN": "5A5958458CADA659",
#     "Template-ID": "Laboratorio",
#     "Status": "IS",
#     "FW Version": "V544ACHK1b1_20",
#     "Model": "PX3321-T1",
#     "Distance": "0 m",
#     "ONT Rx": "-25.81",
#     "Description": ""
#   },
#   ...
# ]

# Para verlos en JSON legible:
print(client.to_json(all_onts))
```

### Obtener detalles de una ONT específica

```python
# Supongamos que queremos detalles de la primera ONT de la lista:
if len(all_onts) > 0:
    first_aid = all_onts[0]["AID"]  # ej. "ont-1-2"
    details = client.get_ont_details(first_aid)

    # 'details' es un diccionario con tres keys:
    #   - "summary": diccionario con fila única (AID, Type, SN, Password, Status, Image Active, SW Version, Vendor/Version, detalles adicionales como detail_Status, detail_Model name, etc.)
    #   - "config": diccionario con claves de configuración (sn, password, template-description, ontServiceControl, ontWan, etc.)
    #   - "status_history": lista de diccionarios con historial (puede estar vacía)
    print(client.to_json(details))
```

### Cerrar la sesión Telnet

```python
client.close()
```

> **Recomendación**: siempre envuelve tus llamadas en un bloque `try/except/finally` o usa `contextlib` para asegurarte de cerrar la conexión incluso si ocurre un error:

```python
try:
    client = APIOLT1408A(...)

    all_onts = client.get_all_onts()
    # ... más acciones ...
finally:
    client.close()
```

---

## Referencia de la API

A continuación, se documentan cada uno de los métodos públicos de la clase `APIOLT1408A`, así como su comportamiento, parámetros y valores de retorno.

### `__init__(self, host: str, port: int, username: str, password: str, prompt: str, timeout: int = 10)`

* **Descripción**:
  Inicializa la conexión Telnet con el OLT Zyxel, envía credenciales y bloquea hasta encontrar el prompt definido. Debe utilizarse previamente a cualquier otro método.

* **Parámetros**:

  * `host` (str): IP o hostname del OLT (ej. `"152.170.97.181"`).
  * `port` (int): puerto Telnet (suele ser `2300`).
  * `username` (str): nombre de usuario Telnet (ej. `"admin"`).
  * `password` (str): contraseña Telnet.
  * `prompt` (str): cadena exacta que identifica el fin del prompt (ej. `"OLT1408A#"`).

    * **Requisito**: el prompt debe terminar en `"#"`.
  * `timeout` (int, opcional): tiempo máximo en segundos para cada `read_until` en la sesión Telnet.

    * Valor por defecto: `10`.

* **Excepciones/Errores**:

  * `ValueError`: si `prompt` no termina en `"#"`.
  * Excepciones de `telnetlib`: si no se puede conectar al host/puerto, o si hay timeout al leer el prompt.

* **Efecto secundario**:

  * Abre internamente `self.tn = telnetlib.Telnet(host, port, timeout=timeout)`.
  * Realiza handshake de login (lee `"User name:"`, envía usuario, lee `"Password:"`, envía contraseña).
  * Bloquea hasta que aparezca el prompt.

---

### `send_command(self, cmd: str) → str`

* **Descripción**:
  Envía un comando al OLT (sin incluir el prompt), bloquea hasta que vuelva a aparecer el prompt, y devuelve la salida intermedia de texto (sin incluir el eco del comando ni la línea del prompt final).

* **Parámetros**:

  * `cmd` (str): cadena del comando a enviar (por ejemplo, `"show remote ont"`).

* **Retorno**:

  * `(str)`: el texto crudo que devuelve el OLT entre el eco del comando y el siguiente prompt.

* **Funcionamiento interno**:

  1. Se asegura de que `cmd` termine con un salto de línea (`"\n"`).
  2. Llama a `self.tn.write(cmd.encode('ascii'))`.
  3. Llama a `self._read_until_prompt()`, que internamente hace `self.tn.read_until(self.prompt.encode(...))`.
  4. Decodifica bytes a `str`, lo divide en líneas, descarta la primera línea (eco) si coincide con el comando y la última línea (el prompt) antes de devolverlo.

* **Ejemplo**:

  ```python
  raw = client.send_command("show remote ont")
  print(raw)
  ```

---

### `get_all_onts(self) → List[Dict[str, str]]`

* **Descripción**:
  Obtiene la lista de todas las ONT asociadas al OLT Zyxel, ejecutando el comando `show remote ont` y parseando la tabla ASCII resultante.

* **Parámetros**:
  Ninguno.

* **Retorno**:

  * `List[Dict[str, str]]`: cada elemento de la lista es un diccionario con las siguientes claves (todas como `str`):

    * `"AID"`
    * `"SN"`
    * `"Template-ID"`
    * `"Status"`
    * `"FW Version"`
    * `"Model"`
    * `"Distance"`
    * `"ONT Rx"`
    * `"Description"`

  Por ejemplo:

  ```python
  [
    {
      "AID": "ont-1-2",
      "SN": "5A5958458CADA659",
      "Template-ID": "Laboratorio",
      "Status": "IS",
      "FW Version": "V544ACHK1b1_20",
      "Model": "PX3321-T1",
      "Distance": "0 m",
      "ONT Rx": "-25.81",
      "Description": ""
    },
    ...
  ]
  ```

* **Errores/Excepciones**:

  * Si `send_command("show remote ont")` falla (timeout o Telnet cerrado), se propagará la excepción de `telnetlib` o un índice de parseo mal formado.

* **Uso recomendado**:

  ```python
  all_onts = client.get_all_onts()
  ```

---

### `get_ont_details(self, aid: str) → Dict[str, object]`

* **Descripción**:
  Recupera todos los detalles de una ONT concreta (identificada por su `AID`) en tres pasos:

  1. `show remote ont <aid>` → parseo de resumen + bloque de detalles generales.
  2. `show remote ont <aid> config` → parseo de configuración avanzada.
  3. `show remote ont <aid> status-history` → parseo del histórico de estados.

  Devuelve un diccionario con tres secciones:

  ```python
  {
    "summary": { ... },         # diccionario de resumen + detalles (líneas clave:valor)
    "config": { ... },          # diccionario de configuración (claves sueltas o listas)
    "status_history": [ ... ]   # lista de diccionarios: {"AID": ..., "Status": ..., "Time": ...}
  }
  ```

* **Parámetros**:

  * `aid` (str): identificador de la ONT, p. ej. `"ont-1-2"`.

* **Retorno**:

  * `Dict[str, object]`:

    * **`"summary"`** (`Dict[str, str]`):

      * Llaves originales de la tabla de resumen (ej. `"AID"`, `"Type"`, `"SN"`, `"Password"`, `"Status"`, `"Image Active"`, `"SW Version"`, `"Vendor/Version"`).
      * Además, para cada línea adicional de detalles en formato clave\:valor (p. ej. `"Status"`, `"Estimated distance"`, `"Model name"`, etc.), se crea una clave **prefijada** con `"detail_<clave>"`.
      * Ejemplo parcial:

        ```python
        {
          "AID": "ont-1-2",
          "Type": "Config",
          "SN": "5A5958458CADA659",
          "Password": "DEFAULT",
          "Status": "Active",
          "Image Active": "1",
          "SW Version": "V544ACHK1b1_20",
          "Vendor/Version": "ZYXE",
          "detail_Status": "IS (3d 21h 16m 33s)",
          "detail_Estimated distance": "0 m",
          "detail_Model name": "N/A",
          ...
        }
        ```
    * **`"config"`** (`Dict[str, object]`):

      * Cada fragmento separado por `"|"` en las líneas de `show remote ont <aid> config` se parsea como un campo:

        * Si el fragmento contiene `"clave: valor"`, se guarda como `config["clave"] = "valor"`.
        * Si el fragmento no contiene `":"`, se asume que la primera palabra es la clave y el resto el valor; si la misma clave aparece varias veces, se agrupan en una lista.
        * Ejemplo:

          ```python
          {
            "sn": "5A5958458CADA659",
            "password": "DEFAULT",
            "full-bridge": "disable",
            "template-description": "Laboratorio",
            "ontServiceControl": [
              "ftp enable LAN",
              "ftp port 21",
              "http enable ALL",
              "http port 80",
              # ...
            ],
            "ontWan": "1 vlan 10 priority 0 mvlan 10 connection-type ipoe default service data ip dynamic enable exit",
            "uniport-1-2-2-1": [
              "no inactive",
              "no pmenable",
              "queue tc 0 priority 0 weight 0 usbwprofname 1G dsbwprofname 1G dsoption olt bwsharegroupid 1",
              "vlan 10 gemport 256 ingprof alltc0 aesencrypt disable",
              "vlan 20 gemport 257 ingprof alltc0 aesencrypt disable"
            ],
            # ... otros campos que no contengan ':'
          }
          ```
    * **`"status_history"`** (`List[Dict[str, str]]`):

      * Cada entrada de la tabla `show remote ont <aid> status-history`.
      * Si no hay entradas, se devuelve lista vacía (`[]`).
      * Ejemplo:

        ```python
        [
          {
            "AID": "ont-1-2",
            "Status": "IS",
            "Time": "2025-06-01 12:34:56"
          },
          {
            "AID": "ont-1-2",
            "Status": "DS",
            "Time": "2025-05-30 08:15:10"
          }
        ]
        ```

* **Errores/Excepciones**:

  * Si algún `send_command(...)` falla: se propaga la excepción de `telnetlib`.
  * Si el parseo produce datos inconsistentes, nunca falla (como excepción), sino que omite filas mal formadas.

* **Uso recomendado**:

  ```python
  details = client.get_ont_details("ont-1-2")
  ```

---

### `close(self)`

* **Descripción**:
  Envía un `exit` al OLT y cierra la sesión Telnet.

* **Parámetros**:
  Ninguno.

* **Retorno**:
  Ninguno.

* **Notas**:

  * Tras llamar a `close()`, no se deben invocar más métodos que usen `self.tn`.
  * Se recomienda envolver la lógica en `try/finally` para garantizar el cierre.

---

### `to_json(self, data: object, indent: int = 2) → str`

* **Descripción**:
  Transforma cualquier objeto serializable en JSON con indentación “legible” (por defecto, 2 espacios).

* **Parámetros**:

  * `data` (object): cualquier estructura de Python (lista, dict, etc.) que sea serializable por `json.dumps`.
  * `indent` (int, opcional): espacios de indentación. Por defecto, `2`.

* **Retorno**:

  * `str`: cadena JSON formateada.

* **Ejemplo**:

  ```python
  json_str = client.to_json(all_onts, indent=4)
  print(json_str)
  ```

---

## Ejemplos de salida JSON

A modo de ilustración, estos ejemplos parten de la salida que mostraste en tu prompt.

> **Ojo**: los valores (fechas, horas, números) son ficticios o sacados textualmente de tu muestra para mostrar la forma.

### Formato de `get_all_onts()`

Salida de `show remote ont`:

```
----------+------------------+----------------------------------+----------+----------------+----------------+----------+--------+----------------------------------
 AID       |               SN |                      Template-ID |   Status |     FW Version |          Model | Distance | ONT Rx |                      Description
----------+------------------+----------------------------------+----------+----------------+----------------+----------+--------+----------------------------------
 ont-1-2   | 5A5958458CADA659 |                      Laboratorio |       IS | V544ACHK1b1_20 |      PX3321-T1 |      0 m | -25.81 | 
----------+------------------+----------------------------------+----------+----------------+----------------+----------+--------+----------------------------------
 Total: 1
```

```json
[
  {
    "AID": "ont-1-2",
    "SN": "5A5958458CADA659",
    "Template-ID": "Laboratorio",
    "Status": "IS",
    "FW Version": "V544ACHK1b1_20",
    "Model": "PX3321-T1",
    "Distance": "0 m",
    "ONT Rx": "-25.81",
    "Description": ""
  }
]
```

### Formato de `get_ont_details("ont-1-2")`

1. **Salida de `show remote ont ont-1-2`:**

   ```
   ----------------------+-------------------------------------------------------+----------------------------+-----------------
   AID                   |   Type               SN             Password   Status  Image Active     SW Version     Vendor/Version
   ----------------------+-------------------------------------------------------+----------------------------+-----------------
   ont-1-2               | Config 5A5958458CADA659              DEFAULT   Active |    1      V V544ACHK1b1_20 |             ZYXE
   Actual 5A5958458CADA659              DEFAULT       IS |    2        V544ACHK1b1_20 |        PX3321-T1
   +------------------------------------------------------------------------------------------------------
   | Status                               : IS (3d 21h 16m 33s)
   | Estimated distance                   : 0 m
   | OMCI GEM port                        : 1
   | Model name                           : N/A
   | Model ID                             : 0
   | Full bridge                          : disable
   | US FEC                               : disable
   | Alarm profile                        : DEFVAL
   | Anti MAC Spoofing                    : disable
   | Planned Version                      : ontImage
   | Description                          : 
   | Template Description                 : Laboratorio
   | Management IP Address                : N/A
   +------------------------------------------------------------------------------------------------------
   | Ethernet 1                           : Link Down
   | Ethernet 2                           : Link Down
   | Ethernet 3                           : Link Down
   | Ethernet 4                           : Link Down
   | POTS/VoIP 1                          : On-hook      Port not configured
   +------------------------------------------------------------------------------------------------------
   | Wan 1                                : Enable
   | Connection Type                      : IPoE
   | Status                               : Up
   | Nat                                  : Disable
   | Service                              : 
   | Default Wan                          : Enable
   | Vlan                                 : 10
   | Priority                             : 0
   | MVLAN                                : 10
   | Auto get IP                          : Enable
   | IP address                           : 192.168.0.202
   | IP Mask                              : 255.255.255.0
   | Gateway                              : 192.168.0.1
   | Primary DNS                          : 192.168.0.1
   | Secondary DNS                        : 0.0.0.0
   +------------------------------------------------------------------------------------------------------
   | Wan 2                                : Disable
   | Wan 3                                : Disable
   | Wan 4                                : Disable
   | Wan 5                                : Disable
   | Wan 6                                : Disable
   | Wan 7                                : Disable
   | Wan 8                                : Disable
   +------------------------------------------------------------------------------------------------------
   | Control Supported                    : WAN(full) LAN WiFi ACS ServiceControl DMZ UPnP Firewall
   ```

2. **Salida de `show remote ont ont-1-2 config`:**

   ```
   ----------------------+------------------------------------------------------------------------------------------------------
   AID                   | Details
   ----------------------+------------------------------------------------------------------------------------------------------
   ont-1-2               | no inactive
                        | sn 5A5958458CADA659
                        | password DEFAULT
                        | full-bridge disable
                        | template-description Laboratorio
                        | plan-version ontImage
                        | alarm-profile DEFVAL
                        | anti-mac-spoofing inactive
                        | bwgroup 1 usbwprofname 1G dsbwprofname 1G allocid 256
                        | ontServiceControl ftp enable LAN
                        | ontServiceControl ftp port 21
                        | ontServiceControl http enable ALL
                        | ontServiceControl http port 80
                        | ontServiceControl https enable LAN
                        | ontServiceControl https port 443
                        | ontServiceControl icmp enable LAN
                        | ontServiceControl snmp enable LAN
                        | ontServiceControl snmp port 161
                        | ontServiceControl ssh enable LAN
                        | ontServiceControl ssh port 22
                        | ontServiceControl telnet enable LAN
                        | ontServiceControl telnet port 23
                        | ontWan 1
                        |     vlan 10 priority 0 mvlan 10
                        |     connection-type ipoe
                        |     default
                        |     service data
                        |     ip dynamic
                        |     enable
                        | exit
   ----------------------+------------------------------------------------------------------------------------------------------
   uniport-1-2-2-1       | no inactive
                        | no pmenable
                        | queue tc 0 priority 0 weight 0 usbwprofname 1G dsbwprofname 1G dsoption olt bwsharegroupid 1
                        | vlan 10 gemport 256 ingprof alltc0 aesencrypt disable
                        | vlan 20 gemport 257 ingprof alltc0 aesencrypt disable
   ----------------------+------------------------------------------------------------------------------------------------------
   ```

3. **Salida de `show remote ont ont-1-2 status-history`:**

   ```
   ----------------------+------------------------------------------------------------------------------------------------------
   AID                   |       Status                         Time
   ----------------------+------------------------------------------------------------------------------------------------------
   ont-1-2               |   IS                               2025-06-01 12:34:56
   ont-1-2               |   DS                               2025-05-30 08:15:10
   ```

Dando como resultado final:

```json
{
  "summary": {
    "AID": "ont-1-2",
    "Type": "Config",
    "SN": "5A5958458CADA659",
    "Password": "DEFAULT",
    "Status": "Active",
    "Image Active": "1",
    "SW Version": "V544ACHK1b1_20",
    "Vendor/Version": "ZYXE",
    "detail_Status": "IS (3d 21h 16m 33s)",
    "detail_Estimated distance": "0 m",
    "detail_OMCI GEM port": "1",
    "detail_Model name": "N/A",
    "detail_Model ID": "0",
    "detail_Full bridge": "disable",
    "detail_US FEC": "disable",
    "detail_Alarm profile": "DEFVAL",
    "detail_Anti MAC Spoofing": "disable",
    "detail_Planned Version": "ontImage",
    "detail_Description": "",
    "detail_Template Description": "Laboratorio",
    "detail_Management IP Address": "N/A",
    "detail_Ethernet 1": "Link Down",
    "detail_Ethernet 2": "Link Down",
    "detail_Ethernet 3": "Link Down",
    "detail_Ethernet 4": "Link Down",
    "detail_POTS/VoIP 1": "On-hook      Port not configured",
    "detail_Wan 1": "Enable",
    "detail_Connection Type": "IPoE",
    "detail_Status": "Up",
    "detail_Nat": "Disable",
    "detail_Service": "",
    "detail_Default Wan": "Enable",
    "detail_Vlan": "10",
    "detail_Priority": "0",
    "detail_MVLAN": "10",
    "detail_Auto get IP": "Enable",
    "detail_IP address": "192.168.0.202",
    "detail_IP Mask": "255.255.255.0",
    "detail_Gateway": "192.168.0.1",
    "detail_Primary DNS": "192.168.0.1",
    "detail_Secondary DNS": "0.0.0.0",
    "detail_Wan 2": "Disable",
    "detail_Wan 3": "Disable",
    "detail_Wan 4": "Disable",
    "detail_Wan 5": "Disable",
    "detail_Wan 6": "Disable",
    "detail_Wan 7": "Disable",
    "detail_Wan 8": "Disable",
    "detail_Control Supported": "WAN(full) LAN WiFi ACS ServiceControl DMZ UPnP Firewall"
  },
  "config": {
    "no": "inactive",
    "sn": "5A5958458CADA659",
    "password": "DEFAULT",
    "full-bridge": "disable",
    "template-description": "Laboratorio",
    "plan-version": "ontImage",
    "alarm-profile": "DEFVAL",
    "anti-mac-spoofing": "inactive",
    "bwgroup": "1 usbwprofname 1G dsbwprofname 1G allocid 256",
    "ontServiceControl": [
      "ftp enable LAN",
      "ftp port 21",
      "http enable ALL",
      "http port 80",
      "https enable LAN",
      "https port 443",
      "icmp enable LAN",
      "snmp enable LAN",
      "snmp port 161",
      "ssh enable LAN",
      "ssh port 22",
      "telnet enable LAN",
      "telnet port 23"
    ],
    "ontWan": "1 vlan 10 priority 0 mvlan 10 connection-type ipoe default service data ip dynamic enable exit",
    "uniport-1-2-2-1": [
      "no inactive",
      "no pmenable",
      "queue tc 0 priority 0 weight 0 usbwprofname 1G dsbwprofname 1G dsoption olt bwsharegroupid 1",
      "vlan 10 gemport 256 ingprof alltc0 aesencrypt disable",
      "vlan 20 gemport 257 ingprof alltc0 aesencrypt disable"
    ]
  },
  "status_history": [
    {
      "AID": "ont-1-2",
      "Status": "IS",
      "Time": "2025-06-01 12:34:56"
    },
    {
      "AID": "ont-1-2",
      "Status": "DS",
      "Time": "2025-05-30 08:15:10"
    }
  ]
}
```

---

## Diseño y consideraciones de parseo

1. **Identificación del prompt**

   * El constructor exige que el prompt termine en `"#"`.
   * Cuando se envía un comando, se lee hasta que aparezca exactamente ese prompt (bytes), utilizando `read_until(prompt.encode('ascii'))`.

2. **Parseo de tablas ASCII**

   * Para **listado de ONT** (`show remote ont`):

     * Se busca la línea que contenga simultáneamente `"AID"` y `"SN"`. Esa línea se considera encabezado.
     * Se dividen los encabezados con `re.split(r"\s*\|\s*", line)` y se recortan espacios.
     * Se omite la línea de guiones siguiente (`^[\-\s\+]+`).
     * Cada línea con `"|"` se separa en celdas usando el mismo split y se crea un diccionario emparejando encabezado → contenido.
     * Al encontrar la línea que comienza en `"Total:"`, se interrumpe el parseo.

3. **Parseo de bloque de detalles en `show remote ont <aid>`**

   * Tras la tabla (fila única con campos: `AID | Type | SN | Password | Status | Image Active | SW Version | Vendor/Version`), aparece un bloque de varias líneas que comienzan con `|   key   :   value`.
   * Para cada línea que cumpla `r".*\|\s*([^:]+):\s*(.+)$"`, se extrae `key` y `value`.
   * En el resultado final, se guarda cada `key` como `"detail_<key>"` para evitar colisiones con los campos del encabezado.

4. **Parseo de configuración en `show remote ont <aid> config`**

   * Cada línea que contenga `"|"` se divide en fragmentos (`parts = [p.strip() for p in line.split("|") if p.strip()]`).
   * Si un fragmento incluye `":"`, se considera `"clave: valor"`.
   * Si no incluye `":"`, se separa por espacios para tomar la primera palabra como clave y el resto como valor continuo.
   * Cuando la misma clave aparece varias veces (por ejemplo, varias líneas de `ontServiceControl`), los valores se agrupan en una lista.
   * Fragmentos que no se pueden encajar en ninguno de los anteriores se agrupan en `config["raw_others"]` (opcional).

5. **Parseo de histórico en `show remote ont <aid> status-history`**

   * Se busca la línea de encabezado que incluya `"AID"`, `"Status"`, `"Time"`.
   * Se ignora la línea de guiones siguiente.
   * Cada línea subsiguiente con `"|"` se divide en celdas y se mapea encabezados → celdas. Se detiene al encontrar una línea sin `"|"` o en blanco.

6. **Flexibilidad y robustez**

   * El código está diseñado para ignorar filas mal formadas (p. ej. con menos columnas).
   * Si Zyxel cambia ligeramente el espaciado de la tabla, mientras mantenga los separadores `"|"`, el parseo seguirá funcionando.
   * Si alguno de los comandos no retorna tablas (por ejemplo, la ONT no existe), los resultados parciales pueden estar vacíos.

---

## Pruebas y desarrollo

### 1. Organización de tests

Dentro de la carpeta `tests/` puedes crear un archivo, por ejemplo `test_olt1408a.py`, que simule distintos escenarios. Usualmente se recomienda:

* **`unittest.mock`** para “mockear” la instancia de `telnetlib.Telnet` y sus métodos `read_until()` y `write()`.
* Considerar casos como:

  * Conexión exitosa vs. fallo de conexión.
  * Salidas de `show remote ont` con varias filas, con “Total: 0” (sin ONT).
  * Salida de `show remote ont <aid>` sin detalles (ONT no registrada).
  * Parsing de bloques de detalles con campos extraños.

#### Ejemplo simplificado de test usando `pytest`:

```python
import pytest
from unittest.mock import MagicMock, patch
from jmq_olt_zyxel.OLT1408A import APIOLT1408A

@pytest.fixture
def fake_telnet(monkeypatch):
    """
    Fixture que reemplaza telnetlib.Telnet por un objeto simulado.
    """
    class FakeTelnet:
        def __init__(self, host, port, timeout):
            pass
        def read_until(self, expected, timeout):
            # Retornar algo neutro (por ejemplo, prompt vacío)
            return b""
        def write(self, data):
            pass
        def close(self):
            pass

    monkeypatch.setattr("telnetlib.Telnet", FakeTelnet)
    return FakeTelnet

def test_init_login(fake_telnet):
    # Se espera que no levante excepción si el prompt termina en "#"
    client = APIOLT1408A(
        host="1.2.3.4",
        port=2300,
        username="admin",
        password="1234",
        prompt="OLT1408A#"
    )
    client.close()

def test_invalid_prompt():
    with pytest.raises(ValueError):
        APIOLT1408A(
            host="1.2.3.4",
            port=2300,
            username="admin",
            password="1234",
            prompt="OLT1408A"  # no termina en "#"
        )

# Aquí podrías añadir más tests que verifiquen el parseo de tablas
```

### 2. Ejecutar pruebas

Si usas `pytest`, simplemente:

```bash
pytest
```

o, si prefieres `unittest`:

```bash
python -m unittest discover tests
```

### 3. Configuración de linters y formateo

* Instalar y configurar **`flake8`** para análisis de estilo y errores comunes.
* Usar **`black`** o **`autopep8`** para formateo automático (opcional).

---

## Cómo contribuir

1. **Fork** este repositorio.
2. Crea una **rama (branch)** nueva para tu característica o corrección de error:

   ```bash
   git checkout -b feature/mipeticion
   ```
3. **Realiza tus cambios** (añade código, actualiza tests, documenta).
4. Ejecuta las pruebas localmente:

   ```bash
   pytest
   ```
5. Haz **commit** y **push** a tu fork:

   ```bash
   git add .
   git commit -m "Agrega parseo de nuevo campo en show remote ont"
   git push origin feature/mipeticion
   ```
6. Abre un **Pull Request** contra la rama principal de `jmq_olt_zyxel`.
7. Se revisarán los cambios, se harán observaciones y, al aprobarse, se fusionarán (merge).

> **Nota**: Asegúrate de que el estilo de código sigue las guías de PEP 8 y que todas las pruebas pasen antes de enviar el Pull Request.

---

## Licencia

Este proyecto está licenciado bajo **MIT License**. Consulta el archivo [LICENSE](LICENSE) para más detalles.

```
MIT License

Copyright (c) 2025 Tu_Organización

Permission is hereby granted, free of charge, to any person obtaining a copy
...
```

---

> **Resumen**: Con esta estructura ya dispones de un paquete completamente documentado que:
>
> 1. Permite conectar a un OLT Zyxel vía Telnet.
> 2. Extraer toda la información relevante de las ONT (rodando comandos `show remote ont`, parseando tablas ASCII y bloques de detalle).
> 3. Retornar los datos en estructuras de Python (lista de diccionarios), listas para convertir a JSON o consumirse por otros módulos.
> 4. Incluye ejemplos claros de uso, tests de base y pautas de contribución.

