# jmq_olt_zyxel/OLT1408A.py

import telnetlib
import time
import re
import json
from typing import List, Dict, Optional


class APIOLT1408A:
    """
    Cliente Telnet para OLT Zyxel (serie OLT1408A, etc.).
    Permite:
      - Conectarse vía Telnet (host, puerto, usuario, contraseña).
      - Ejecutar comandos como 'show remote ont' y 'show remote ont <AID>'.
      - Parsear la salida y devolver diccionarios o JSON.
    """

    def __init__(self, host: str, port: int, username: str, password: str, prompt: str, timeout: int = 10):
        """
        Inicializa la conexión Telnet y hace login. Luego deja listo el prompt para enviar comandos.

        :param host: IP o hostname del OLT Zyxel (ej. "152.170.97.181")
        :param port: puerto Telnet (ej. 2300)
        :param username: usuario Telnet (ej. "admin")
        :param password: contraseña Telnet
        :param prompt: cadena de fin de prompt (ej. "OLT1408A#")
        :param timeout: tiempo máximo para read_until en segundos
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        # Aseguramos que el prompt termine con el símbolo "#"
        self.prompt = prompt.strip()
        if not self.prompt.endswith("#"):
            raise ValueError("El prompt debe terminar con '#' (ej. 'OLT1408A#').")
        self.timeout = timeout

        # Abrimos la sesión Telnet
        self.tn = telnetlib.Telnet(self.host, self.port, timeout=self.timeout)
        # Leer hasta que aparezca "User name:" y enviar usuario
        self.tn.read_until(b"User name:", timeout=self.timeout)
        self.tn.write(self.username.encode('ascii') + b"\n")

        # Leer hasta "Password:" y enviar contraseña
        self.tn.read_until(b"Password:", timeout=self.timeout)
        self.tn.write(self.password.encode('ascii') + b"\n")

        # Leer hasta que aparezca nuestro prompt (puede venir el banner antes)
        # Convertimos el prompt a bytes para comparar
        self._read_until_prompt()

    def _read_until_prompt(self) -> bytes:
        """
        Lee desde la sesión Telnet hasta que aparezca el prompt definido.
        Devuelve los bytes leídos (incluye el prompt al final).
        """
        return self.tn.read_until(self.prompt.encode('ascii'), timeout=self.timeout)

    def send_command(self, command: str) -> str:
        """
        Envía un comando (sin prompt final) y devuelve la salida (str)
        entre el eco de comando y el siguiente prompt.
        """
        # Asegurarnos de que el comando termine en newline
        cmd = command.strip() + "\n"
        # Enviar el comando
        self.tn.write(cmd.encode('ascii'))
        # Leer hasta el próximo prompt (la respuesta incluirá el eco de comando + salida + prompt)
        raw_output = self._read_until_prompt()
        # raw_output es bytes: conviértelo a str
        text = raw_output.decode('ascii', errors='ignore')

        # Eliminar el eco del comando (primera línea) y el prompt final
        # Por ejemplo, raw_output puede ser:
        #   "show remote ont\n   <líneas de la tabla>\nOLT1408A#"
        lines = text.splitlines()
        if len(lines) >= 1 and lines[0].strip() == command.strip():
            # El eco está en la primera línea: descartarla
            lines = lines[1:]
        # La última línea es el prompt (u ocasionalmente prompt + espacios), descartamos
        if len(lines) >= 1 and lines[-1].strip().endswith(self.prompt.rstrip("#")):
            # O bien: if lines[-1].strip() == self.prompt:
            # A veces la línea final es solo el prompt, o prompt precedido de espacios.
            lines = lines[:-1]
        # Reensamblar
        return "\n".join(lines)

    def get_all_onts(self) -> List[Dict[str, str]]:
        """
        Ejecuta 'show remote ont' y parsea la tabla de resumen.
        Devuelve una lista de diccionarios, uno por cada ONT encontrada.
        Cada diccionario tendrá claves:
          'AID', 'SN', 'Template-ID', 'Status', 'FW Version',
          'Model', 'Distance', 'ONT Rx', 'Description'
        """
        raw = self.send_command("show remote ont")
        return self._parse_onts_summary(raw)

    def _parse_onts_summary(self, text: str) -> List[Dict[str, str]]:
        """
        A partir de la cadena completa de 'show remote ont', extrae las filas de ONT
        y devuelve una lista de diccionarios.
        """
        lines = text.splitlines()
        data_started = False
        headers: List[str] = []
        results: List[Dict[str, str]] = []
        for idx, line in enumerate(lines):
            # Detectamos la línea del encabezado (donde está 'AID' y 'SN')
            if not data_started and re.search(r"\bAID\b.*\bSN\b", line):
                data_started = True
                # Extraemos los nombres de columna a partir de la línea, según posición de pipes
                # Por ejemplo: " AID       |               SN | Template-ID | Status | FW Version | Model | Distance | ONT Rx | Description"
                headers = [h.strip() for h in re.split(r"\s*\|\s*", line) if h.strip()]
                continue

            if data_started:
                # La siguiente línea tras el encabezado es la de guiones, la ignoramos
                if re.match(r"[-\s\+]+", line):
                    continue
                # Si llega a "Total: N", detenemos el parsing
                if line.strip().lower().startswith("total:"):
                    break
                # Si la línea contiene '|' es una fila válida
                if "|" in line:
                    # Hacemos split por '|' y recortamos espacios
                    cells = [c.strip() for c in re.split(r"\s*\|\s*", line)]
                    # Asegurarnos de que coincida la cantidad de columnas
                    # Si hay más separadores de lo normal, tomamos solo los primeros len(headers)
                    if len(cells) < len(headers):
                        # fila malformada; la saltamos
                        continue
                    row = {}
                    for i, key in enumerate(headers):
                        row[key] = cells[i]
                    results.append(row)
                else:
                    # Línea que ya no forma parte de la tabla (por si hubiese saltos de línea); la ignoramos
                    continue
        return results

    def get_ont_details(self, aid: str) -> Dict[str, Optional[object]]:
        """
        Ejecuta los comandos necesarios para obtener todos los detalles de una ONT específica:
          - show remote ont <aid>
          - show remote ont <aid> config
          - show remote ont <aid> status-history
        Devuelve un diccionario con:
          {
            "summary": { ... },    # salida de show remote ont <aid> parseada
            "config": { ... },     # detalles de configuración
            "status_history": [ ... ]  # lista de entradas de histórico
          }
        """
        # 1) Resumen rápido
        raw_summary = self.send_command(f"show remote ont {aid}")
        summary = self._parse_single_ont_summary(raw_summary)

        # 2) Config
        raw_config = self.send_command(f"show remote ont {aid} config")
        config = self._parse_ont_config(raw_config)

        # 3) Status-history
        raw_hist = self.send_command(f"show remote ont {aid} status-history")
        history = self._parse_status_history(raw_hist)

        return {
            "summary": summary,
            "config": config,
            "status_history": history
        }

    def _parse_single_ont_summary(self, text: str) -> Dict[str, str]:
        """
        A partir de la salida de 'show remote ont <aid>', parsea la tabla
        de un único registro (AID, Type, SN, Password, Status, Image Active, SW Version, Vendor/Version)
        y los bloques de detalle que aparecen debajo.
        """
        lines = text.splitlines()
        result: Dict[str, str] = {}

        # 1) Detectar la primera tabla (una fila) de resumen
        in_header = False
        headers: List[str] = []
        for idx, line in enumerate(lines):
            if not in_header and re.search(r"\bAID\b.*\bSN\b", line):
                in_header = True
                headers = [h.strip() for h in re.split(r"\s*\|\s*", line) if h.strip()]
                continue
            if in_header:
                # La siguiente línea es la de guiones, saltar
                if re.match(r"[-\s\+]+", line):
                    continue
                # Si la línea contiene '|' -> fila de datos
                if "|" in line:
                    cells = [c.strip() for c in re.split(r"\s*\|\s*", line)]
                    for i, key in enumerate(headers):
                        # Cuidado: puede haber más columnas o menos; hacemos check
                        result[key] = cells[i] if i < len(cells) else ""
                    # Ya parseamos el único registro, rompemos
                    break

        # 2) Bloques de detalles (líneas que comienzan con '|  key  :  value')
        # Buscamos líneas que tengan '|' y un ':' para entender clave:valor
        details: Dict[str, str] = {}
        for line in lines:
            # Por ejemplo: "| Status                               : IS (3d 21h 16m 33s)"
            m = re.match(r".*\|\s*([^:]+):\s*(.+)$", line)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                details[key] = val

        # Combinamos resumen + detalles en un solo dict (prefijando “detail_” para evitar colisiones)
        for k, v in details.items():
            result[f"detail_{k}"] = v

        return result

    def _parse_ont_config(self, text: str) -> Dict[str, object]:
        """
        Parsea la salida de 'show remote ont <aid> config' en un diccionario de clave: valor.
        Cada línea que comience con '|' y contenga '|' y ':' la interpretamos como clave: valor.
        """
        lines = text.splitlines()
        config: Dict[str, object] = {}

        # Muchas líneas vienen agrupadas en bloques; detectamos cada línea que cumpla patrón “clave : valor”
        # Ejemplo: "| sn 5A5958458CADA659"
        key = None
        for line in lines:
            # Algunas líneas van sin ':', solo con lista de atributos en la misma línea (ej. "| no inactive")
            # También hay bloques como "| uniport-1-2-2-1       | no inactive | no pmenable | queue tc 0 ... "
            # Lo más práctico es separar por '|' y tomar cada fragmento como “campo” si no hay ':'
            if "|" in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                # Cada fragmento de parts puede ser:
                #  - "sn 5A5958458CADA659"      (sin ':', interpretamos toda la línea tras 'sn' como un campo)
                #  - "anti-mac-spoofing inactive"
                #  - "ontServiceControl ftp enable LAN"
                #  - "bwgroup 1 usbwprofname 1G dsbwprofname 1G allocid 256"
                #  - etc.
                # Buscamos si hay sub-partes que contengan ':' primero
                for fragment in parts:
                    if ":" in fragment:
                        # Ejemplo: "vlan 10 priority 0 mvlan 10"
                        # Si no hay ':', lo guardamos tal cual en una lista bajo la clave “raw”
                        # En este bloque concreto no hay ':', así que no entra aquí.
                        fld, val = fragment.split(":", 1)
                        config[fld.strip()] = val.strip()
                    else:
                        # Si el fragmento contiene más de 1 palabra, podemos tratar de tomar el primer token como clave
                        # y el resto como valor. Ejemplo: "sn 5A5958458CADA659"
                        tokens = fragment.split()
                        if len(tokens) >= 2:
                            # clave = primer token; valor = resto
                            fld = tokens[0]
                            val = " ".join(tokens[1:])
                            # Para evitar repetir, si ya existe la clave agregamos a lista
                            if fld in config:
                                # Si ya es lista, añadimos; si era escalar, convertimos en lista
                                if isinstance(config[fld], list):
                                    config[fld].append(val)
                                else:
                                    config[fld] = [config[fld], val]
                            else:
                                config[fld] = val
                        else:
                            # fragmento solitario, lo coleccionamos en raw_others
                            config.setdefault("raw_others", []).append(fragment)
                # seguimos con siguiente línea
        return config

    def _parse_status_history(self, text: str) -> List[Dict[str, str]]:
        """
        Parsea la tabla de 'show remote ont <aid> status-history'.
        Si no hay entradas, devolvemos lista vacía.
        Si las hay, cada fila tendrá {'AID': ..., 'Status': ..., 'Time': ...}.
        """
        lines = text.splitlines()
        in_header = False
        headers: List[str] = []
        entries: List[Dict[str, str]] = []

        for idx, line in enumerate(lines):
            if not in_header and re.search(r"\bAID\b.*\bStatus\b.*\bTime\b", line):
                in_header = True
                headers = [h.strip() for h in re.split(r"\s*\|\s*", line) if h.strip()]
                continue
            if in_header:
                # Saltamos la línea de guiones
                if re.match(r"[-\s\+]+", line):
                    continue
                # Si vemos una línea vacía o que no contenga '|', nos detenemos
                if not line.strip() or "|" not in line:
                    break
                cells = [c.strip() for c in re.split(r"\s*\|\s*", line)]
                if len(cells) < len(headers):
                    continue
                row = {}
                for i, key in enumerate(headers):
                    row[key] = cells[i]
                entries.append(row)
        return entries

    def close(self):
        """
        Cierra la sesión Telnet.
        """
        try:
            self.tn.write(b"exit\n")
            time.sleep(0.5)
            self.tn.close()
        except Exception:
            pass

    def to_json(self, data: object, indent: int = 2) -> str:
        """
        Devuelve una cadena JSON formateada a partir de cualquier estructura (lista, dict, etc.).
        """
        return json.dumps(data, indent=indent)

