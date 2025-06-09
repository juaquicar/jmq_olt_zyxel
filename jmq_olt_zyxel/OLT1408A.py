# jmq_olt_zyxel/OLT1408A.py

import telnetlib
import time
import re
import json
from typing import List, Dict, Optional


class APIOLT1408A:
    def __init__(self, host: str, port: int, username: str, password: str, prompt: str, timeout: int = 10):
        print(f"[DEBUG] Inicializando conexión con {host}:{port}")
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.prompt = prompt.strip()
        if not self.prompt.endswith("#"):
            raise ValueError("El prompt debe terminar con '#' (ej. 'OLT1408A#').")
        self.timeout = timeout

        print("[DEBUG] Abriendo sesión Telnet...")
        self.tn = telnetlib.Telnet(self.host, self.port, timeout=self.timeout)

        print("[DEBUG] Esperando 'User name:'...")
        self.tn.read_until(b"User name:", timeout=self.timeout)
        self.tn.write(self.username.encode('ascii') + b"\n")

        print("[DEBUG] Enviando contraseña...")
        self.tn.read_until(b"Password:", timeout=self.timeout)
        self.tn.write(self.password.encode('ascii') + b"\n")

        print("[DEBUG] Esperando prompt...")
        self._read_until_prompt()
        print("[DEBUG] Sesión iniciada correctamente.")

    def _read_until_prompt(self) -> bytes:
        print(f"[DEBUG] Esperando hasta el prompt '{self.prompt}'...")
        result = self.tn.read_until(self.prompt.encode('ascii'), timeout=self.timeout)
        print("[DEBUG] Prompt detectado.")
        return result

    def send_command(self, command: str) -> str:
        print(f"[DEBUG] Enviando comando: {command}")
        cmd = command.strip() + "\n"
        self.tn.write(cmd.encode('ascii'))
        raw_output = self._read_until_prompt()
        text = raw_output.decode('ascii', errors='ignore')

        print(f"[DEBUG] Comando enviado. Procesando salida...")
        lines = text.splitlines()
        if len(lines) >= 1 and lines[0].strip() == command.strip():
            lines = lines[1:]
        if len(lines) >= 1 and lines[-1].strip().endswith(self.prompt.rstrip("#")):
            lines = lines[:-1]
        output = "\n".join(lines)
        print(f"[DEBUG] Resultado del comando:\n{output[:500]}...\n[DEBUG] --- Fin salida ---")
        return output

    def get_all_onts(self) -> List[Dict[str, str]]:
        print("[DEBUG] Obteniendo lista de todas las ONTs...")
        raw = self.send_command("show remote ont")
        results = self._parse_onts_summary(raw)
        print(f"[DEBUG] {len(results)} ONTs parseadas.")
        return results

    def _parse_onts_summary(self, text: str) -> List[Dict[str, str]]:
        print("[DEBUG] Parseando resumen de ONTs...")
        lines = text.splitlines()
        data_started = False
        headers: List[str] = []
        results: List[Dict[str, str]] = []
        for idx, line in enumerate(lines):
            if not data_started and re.search(r"\bAID\b.*\bSN\b", line):
                headers = [h.strip() for h in re.split(r"\s*\|\s*", line) if h.strip()]
                data_started = True
                print(f"[DEBUG] Encabezados detectados: {headers}")
                continue
            if data_started:
                if re.match(r"[-\s\+]+", line):
                    continue
                if line.strip().lower().startswith("total:"):
                    print("[DEBUG] Fin de tabla detectado.")
                    break
                if "|" in line:
                    cells = [c.strip() for c in re.split(r"\s*\|\s*", line)]
                    if len(cells) < len(headers):
                        print(f"[DEBUG] Fila malformada saltada: {cells}")
                        continue
                    row = {headers[i]: cells[i] for i in range(len(headers))}
                    results.append(row)
        return results

    def get_ont_details(self, aid: str) -> Dict[str, Optional[object]]:
        print(f"[DEBUG] Obteniendo detalles para ONT {aid}")
        raw_summary = self.send_command(f"show remote ont {aid}")
        summary = self._parse_single_ont_summary(raw_summary)

        raw_config = self.send_command(f"show remote ont {aid} config")
        config = self._parse_ont_config(raw_config)

        raw_hist = self.send_command(f"show remote ont {aid} status-history")
        history = self._parse_status_history(raw_hist)

        print(f"[DEBUG] Detalles completos obtenidos para {aid}")
        return {
            "summary": summary,
            "config": config,
            "status_history": history
        }

    def _parse_single_ont_summary(self, text: str) -> Dict[str, str]:
        print("[DEBUG] Parseando resumen de ONT individual...")
        lines = text.splitlines()
        result: Dict[str, str] = {}
        in_header = False
        headers: List[str] = []

        for idx, line in enumerate(lines):
            if not in_header and re.search(r"\bAID\b.*\bSN\b", line):
                headers = [h.strip() for h in re.split(r"\s*\|\s*", line) if h.strip()]
                in_header = True
                continue
            if in_header and "|" in line and not re.match(r"[-\s\+]+", line):
                cells = [c.strip() for c in re.split(r"\s*\|\s*", line)]
                for i, key in enumerate(headers):
                    result[key] = cells[i] if i < len(cells) else ""
                break

        details: Dict[str, str] = {}
        for line in lines:
            m = re.match(r".*\|\s*([^:]+):\s*(.+)$", line)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                details[key] = val

        for k, v in details.items():
            result[f"detail_{k}"] = v

        return result

    def _parse_ont_config(self, text: str) -> Dict[str, object]:
        print("[DEBUG] Parseando configuración de ONT...")
        lines = text.splitlines()
        config: Dict[str, object] = {}

        for line in lines:
            if "|" in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                for fragment in parts:
                    if ":" in fragment:
                        fld, val = fragment.split(":", 1)
                        config[fld.strip()] = val.strip()
                    else:
                        tokens = fragment.split()
                        if len(tokens) >= 2:
                            fld, val = tokens[0], " ".join(tokens[1:])
                            if fld in config:
                                if isinstance(config[fld], list):
                                    config[fld].append(val)
                                else:
                                    config[fld] = [config[fld], val]
                            else:
                                config[fld] = val
                        else:
                            config.setdefault("raw_others", []).append(fragment)
        return config

    def _parse_status_history(self, text: str) -> List[Dict[str, str]]:
        print("[DEBUG] Parseando histórico de estado...")
        lines = text.splitlines()
        in_header = False
        headers: List[str] = []
        entries: List[Dict[str, str]] = []

        for idx, line in enumerate(lines):
            if not in_header and re.search(r"\bAID\b.*\bStatus\b.*\bTime\b", line):
                headers = [h.strip() for h in re.split(r"\s*\|\s*", line) if h.strip()]
                in_header = True
                continue
            if in_header:
                if re.match(r"[-\s\+]+", line) or not line.strip() or "|" not in line:
                    continue
                cells = [c.strip() for c in re.split(r"\s*\|\s*", line)]
                if len(cells) < len(headers):
                    continue
                entries.append({headers[i]: cells[i] for i in range(len(headers))})
        return entries

    def close(self):
        print("[DEBUG] Cerrando sesión Telnet...")
        try:
            self.tn.write(b"exit\n")
            time.sleep(0.5)
            self.tn.close()
            print("[DEBUG] Sesión cerrada.")
        except Exception as e:
            print(f"[DEBUG] Error cerrando sesión: {e}")

    def to_json(self, data: object, indent: int = 2) -> str:
        print("[DEBUG] Serializando datos a JSON...")
        return json.dumps(data, indent=indent)
