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

### OLTs Integradas

 - 1408A
 - 2406
 - 1240XA 

### Versión

#### 1.1.0
- Integradas OLTs 1240XA y OLT2406

#### 1.1.1
- Errata que no permitia extracción en 1240XA si se ponía un nombre personalizado.

## Licencia

MIT License
