# -*- coding: utf-8 -*-
"""
OLT2406.py

Cliente API para interactuar con una OLT Zyxel OLT2406 vía Telnet.

Reparaciones incluidas (basadas en tus logs reales):
- Manejo de ANSI/VT100: la OLT envía ESC[6n (Device Status Report). Si no respondes,
  la CLI puede quedarse “bloqueada” y no ejecutar/retornar comandos.
  -> Se auto-responde ESC[1;1R por el socket telnet.
- Manejo de prompt NO necesariamente como “línea completa”: el prompt puede venir sin \n.
  -> Se detecta prompt al final del buffer (no solo ^...$ multiline).
- Evitar cortar por “prompt viejo”: require_progress ignora buffers que son solo prompt/whitespace.
- Debug de salida telnet:
  - Impresión a consola con timestamps en bloques START/END.
  - (Opcional) guardado RAW exacto a fichero para análisis forense.
  - En consola se filtran secuencias ANSI para que el terminal no “meta” respuestas como ^[[25;1R.

Mantiene la misma API pública:
- get_all_onts, get_unregistered_onts, get_ont_details, get_ont_status_history, get_ont_config, to_json, close
"""

import telnetlib
import re
import json
import time
import sys
from typing import List, Dict, Any, Optional


class APIOLT2406:
    """
    Cliente API para interactuar con una OLT Zyxel OLT2406 vía Telnet.
    """

    # AID típico: ont-6-4-4 (un índice más que 1408A)
    AID_RE = re.compile(r"^ont-\d+(?:-\d+){2,}$")   # ont-x-y-z...
    PON_AID_RE = re.compile(r"^pon-\d+(?:-\d+){1,}$")

    # Separadores: "-----+-----" o "------------+------"
    SEP_RE = re.compile(r"^\s*-+\s*\+\s*-+.*$")

    # ANSI / VT100 (para filtrar en consola y evitar efectos colaterales del terminal)
    ANSI_RE = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        prompt_base: str = "OLT2406#",
        timeout: int = 30,
        login_user_prompt: bytes = b"User name:",
        login_pass_prompt: bytes = b"Password:",
        debug: bool = False,
        debug_telnet_dump: bool = False,
        debug_telnet_raw_file: Optional[str] = "/tmp/olt2406_telnet_raw.log",
        eol: bytes = b"\r\n",
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password

        self.prompt_base = prompt_base
        self.timeout = timeout
        self.login_user_prompt = login_user_prompt
        self.login_pass_prompt = login_pass_prompt
        self.debug = debug
        self.debug_telnet_dump = debug_telnet_dump
        self.debug_telnet_raw_file = debug_telnet_raw_file
        self.eol = eol

        # Prompt detection robusto:
        # - prompt al final del buffer (sin necesidad de newline)
        self._prompt_end_re = re.compile(re.escape(self.prompt_base).encode("ascii") + rb"\s*$")

        # Prompt “solo” (para ignore_progress)
        self._prompt_only_re = re.compile(rb"^\s*" + re.escape(self.prompt_base).encode("ascii") + rb"\s*$")

        self.tn = telnetlib.Telnet()

        self._d(
            "Init APIOLT2406 "
            f"(host={self.host}, port={self.port}, timeout={self.timeout}, "
            f"prompt_base={self.prompt_base!r}, debug={self.debug}, "
            f"debug_telnet_dump={self.debug_telnet_dump}, "
            f"debug_telnet_raw_file={self.debug_telnet_raw_file!r}, "
            f"eol={self.eol!r})"
        )

        self._open_session()

    # -----------------------------
    # Debug helpers
    # -----------------------------
    def _ts(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def _d(self, msg: str) -> None:
        if self.debug:
            print(f"[{self._ts()}] [DEBUG] {msg}")

    def _strip_ansi(self, raw: bytes) -> bytes:
        """
        Elimina secuencias ANSI para imprimir en consola sin que el terminal reaccione.
        """
        return self.ANSI_RE.sub(b"", raw)

    def _dump_telnet(self, context: str, raw: bytes) -> None:
        """
        Dump de TELNET para depuración:
        - Guarda RAW exacto a fichero (si configurado).
        - Imprime en consola un bloque START/END con timestamps.
          Para evitar que tu terminal responda a ANSI (p.ej. ESC[6n), filtramos ANSI.
        """
        if not self.debug:
            return

        # 1) Guardado raw exacto (opcional)
        if self.debug_telnet_raw_file:
            try:
                with open(self.debug_telnet_raw_file, "ab") as f:
                    header = f"\n\n===== {self._ts()} {context} =====\n".encode("utf-8", errors="ignore")
                    f.write(header)
                    f.write(raw)
            except Exception as e:
                self._d(f"_dump_telnet: error escribiendo RAW a fichero => {e!r}")

        # 2) Impresión a consola (opcional)
        if not self.debug_telnet_dump:
            return

        print(f"[{self._ts()}] [TELNET] --- {context} START ---")
        try:
            safe = self._strip_ansi(raw)
            txt = safe.decode("latin-1", errors="strict")
        except Exception:
            txt = raw.decode("utf-8", errors="replace")

        # imprimir tal cual (sin añadir prefijos dentro del bloque)
        sys.stdout.write(txt)
        sys.stdout.flush()
        if not txt.endswith("\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()

        print(f"[{self._ts()}] [TELNET] --- {context} END ---")

    # -----------------------------
    # ANSI/VT100 autoresponse (CRÍTICO en tu OLT)
    # -----------------------------
    def _ansi_autoreply(self, data: bytes) -> None:
        """
        La OLT envía ESC[6n (Device Status Report). Si no respondemos, la CLI se queda
        en estado incompleto y no ejecuta/retorna comandos.

        Respondemos con ESC[1;1R (cursor 1,1).
        """
        if b"\x1b[6n" in data:
            self._d("ANSI query detectada: ESC[6n. Respondiendo ESC[1;1R por telnet.")
            try:
                self.tn.write(b"\x1b[1;1R")
            except Exception as e:
                self._d(f"Error enviando respuesta ANSI => {e!r}")

    # -----------------------------
    # Sesión / IO
    # -----------------------------
    def _open_session(self) -> None:
        self._d("Abriendo sesión Telnet...")
        self.tn.open(self.host, self.port, timeout=self.timeout)

        self._d("Esperando prompt de usuario...")
        _ = self.tn.read_until(self.login_user_prompt, timeout=self.timeout)
        self._d("Prompt de usuario recibido. Enviando username...")
        self.tn.write(self.username.encode("ascii") + self.eol)

        self._d("Esperando prompt de password...")
        _ = self.tn.read_until(self.login_pass_prompt, timeout=self.timeout)
        self._d("Prompt de password recibido. Enviando password...")
        self.tn.write(self.password.encode("ascii") + self.eol)

        self._d("Esperando prompt de CLI (post-login)...")
        buf = self._read_until_prompt(timeout=self.timeout, require_progress=False, context="POST-LOGIN")
        self._d(f"Post-login read bytes={len(buf)} (prompt detectado o timeout).")
        self._dump_telnet("POST-LOGIN", buf)

        # Asegurar prompt “vivo” tras login (muchas CLIs solo lo muestran tras Enter)
        self._d("Post-login: forcing resync newline para obtener prompt...")
        self.tn.write(self.eol)
        buf2 = self._read_until_prompt(timeout=min(5, self.timeout), require_progress=False, context="POST-LOGIN-RESYNC")
        self._dump_telnet("POST-LOGIN-RESYNC", buf2)

        self._d("Sesión iniciada (si hay prompt visible en dumps).")

    def _drain_input(self, drain_for: float = 0.25) -> bytes:
        """
        Vacia el buffer de entrada durante un pequeño intervalo.
        """
        self._d(f"_drain_input(drain_for={drain_for}) => start")
        end = time.time() + drain_for
        buf = b""
        while time.time() < end:
            chunk = self.tn.read_very_eager()
            if chunk:
                self._ansi_autoreply(chunk)
                buf += chunk
                end = max(end, time.time() + 0.05)
            else:
                time.sleep(0.02)
        self._d(f"_drain_input => drained bytes={len(buf)}")
        if buf:
            self._dump_telnet("DRAIN", buf)
        return buf

    def _has_real_progress(self, buf: bytes) -> bool:
        """
        Progreso real: algo que no sea whitespace y que no sea SOLO el prompt.
        """
        tmp = buf.strip(b"\r\n\t ")
        if not tmp:
            return False
        # si el buffer reducido es solo prompt -> no es progreso real
        if self._prompt_only_re.match(tmp):
            return False
        return True

    def _read_until_prompt(
        self,
        timeout: Optional[int] = None,
        *,
        require_progress: bool = False,
        context: str = "READ",
    ) -> bytes:
        """
        Lee del socket hasta detectar prompt al final del buffer.
        - Detecta prompt aunque no venga como línea completa (sin newline).
        - Maneja ANSI queries (ESC[6n) respondiendo por telnet.
        - Si require_progress=True, no devuelve si solo hemos visto prompt “vacío”.
        """
        if timeout is None:
            timeout = self.timeout

        end_time = time.time() + timeout
        buf = b""
        saw_progress = not require_progress

        self._d(f"_read_until_prompt(timeout={timeout}, require_progress={require_progress}, context={context}) => start")

        last_stat = 0.0
        while time.time() < end_time:
            chunk = self.tn.read_very_eager()
            if chunk:
                # autoresponder ANSI si aplica
                self._ansi_autoreply(chunk)

                buf += chunk

                if not saw_progress and self._has_real_progress(buf):
                    saw_progress = True

                # debug ligero
                now = time.time()
                if self.debug and (now - last_stat) >= 0.8:
                    last_stat = now
                    self._d(f"_read_until_prompt: bytes={len(buf)} saw_progress={saw_progress}")

                # prompt al final del buffer (robusto)
                if self._prompt_end_re.search(buf.rstrip(b"\r\n")):
                    if require_progress and not saw_progress:
                        # es solo prompt viejo (o nada real), seguimos leyendo
                        continue
                    self._d("_read_until_prompt: prompt detectado al final del buffer.")
                    return buf
            else:
                time.sleep(0.05)

        self._d(f"_read_until_prompt: TIMEOUT (bytes={len(buf)})")
        if buf:
            self._dump_telnet(f"{context}-TIMEOUT-BUF", buf)
        return buf

    def _resync_cli(self) -> None:
        """
        Fuerza que la CLI esté en estado "prompt listo".
        """
        self._d("_resync_cli: enviando EOL para resincronizar...")
        self.tn.write(self.eol)
        buf = self._read_until_prompt(timeout=min(5, self.timeout), require_progress=False, context="RESYNC")
        self._dump_telnet("RESYNC", buf)
        _ = self._drain_input(drain_for=0.15)

    def _send_command(self, command: str) -> str:
        """
        Envía comando y devuelve output (sin el prompt final).
        """
        self._d(f"_send_command: preparando comando={command!r}")

        # asegurar prompt
        self._resync_cli()

        # limpiar residuos
        _ = self._drain_input(drain_for=0.2)

        # enviar comando
        self._d(f"CMD => {command}")
        self.tn.write(command.encode("ascii") + self.eol)

        # leer hasta prompt, exigiendo progreso real
        raw = self._read_until_prompt(timeout=self.timeout, require_progress=True, context=f"CMD:{command}")
        self._d(f"_send_command: raw bytes={len(raw)}")
        self._dump_telnet(f"CMD OUTPUT: {command}", raw)

        # limpiar prompt final del raw
        text = raw.decode("latin-1", errors="ignore")
        # Eliminamos el prompt final aunque no tenga newline
        # -> cortamos desde el último match del prompt en el final
        # Nota: si el prompt apareció también antes, esto conserva lo anterior.
        m = self._prompt_end_re.search(raw.rstrip(b"\r\n"))
        if m:
            # posición en bytes del match
            cut = m.start()
            raw_wo_prompt = raw[:cut]
        else:
            raw_wo_prompt = raw

        out = raw_wo_prompt.decode("latin-1", errors="ignore")

        # quitar eco del comando si aparece como primera línea visible
        lines = out.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and lines[0].strip() == command.strip():
            lines.pop(0)

        out2 = "\n".join(lines).strip("\n")
        self._d(f"_send_command: out chars={len(out2)} líneas={len(out2.splitlines()) if out2 else 0}")
        return out2

    # -----------------------------
    # API pública
    # -----------------------------
    def get_all_onts(self) -> List[Dict[str, Any]]:
        self._d("get_all_onts: start")
        raw = self._send_command("show remote ont")
        rows = self._parse_table_any(raw, row_prefix="ont-")
        self._d(f"get_all_onts: rows={len(rows)}")
        return rows

    def get_unregistered_onts(self) -> List[Dict[str, Any]]:
        self._d("get_unregistered_onts: start")
        raw = self._send_command("show remote ont unreg")
        rows = self._parse_table_any(raw, row_prefix="pon-")
        self._d(f"get_unregistered_onts: rows={len(rows)}")
        return rows

    def get_ont_details(self, aid: str) -> Dict[str, Any]:
        self._d(f"get_ont_details: start aid={aid!r}")
        raw = self._send_command(f"show remote ont {aid}")
        lines = raw.splitlines()

        details: Dict[str, Any] = {
            "aid": aid,
            "kv": {},
            "sections": {},
        }

        for line in lines:
            stripped = line.strip()
            cleaned = stripped.lstrip("|").strip() if stripped.startswith("|") else stripped

            if ":" in cleaned:
                key, val = cleaned.split(":", 1)
                k = key.strip()
                v = val.strip()

                section_key = None
                for prefix in ("Wan ", "Ethernet ", "POTS/VoIP ", "Status", "Control Supported"):
                    if k.startswith(prefix):
                        section_key = prefix.strip()
                        break

                details["kv"][k] = v
                if section_key:
                    details["sections"].setdefault(section_key, []).append({k: v})

        return details

    def get_ont_status_history(self, aid: str) -> List[Dict[str, Any]]:
        self._d(f"get_ont_status_history: start aid={aid!r}")
        raw = self._send_command(f"show remote ont {aid} status-history")
        lines = raw.splitlines()

        history: List[Dict[str, Any]] = []
        for line in lines:
            if "|" not in line:
                continue
            _, right = line.split("|", 1)
            right = right.strip()
            if not right:
                continue

            tokens = right.split()
            if len(tokens) < 4:
                continue

            idx_token = tokens[0]
            status = tokens[1]
            time_str = " ".join(tokens[2:])

            if not idx_token.isdigit():
                continue

            history.append({"idx": int(idx_token), "status": status, "tt": time_str})

        return history

    def get_ont_config(self, aid: str) -> Dict[str, Any]:
        self._d(f"get_ont_config: start aid={aid!r}")
        raw = self._send_command(f"show remote ont {aid} config")
        lines = raw.splitlines()

        result: Dict[str, Any] = {
            "aid": aid,
            "ont": {},
            "uniports": {},
            "raw_lines": [],
        }

        current_block: Optional[str] = None
        current_uniport: Optional[str] = None

        for line in lines:
            result["raw_lines"].append(line)

            if self.SEP_RE.match(line.strip()):
                continue

            if "|" in line:
                left, right = line.split("|", 1)
                left = left.strip()
                right = right.strip()

                if left.startswith("ont-"):
                    current_block = "ont"
                    current_uniport = None
                    self._parse_config_line_into(result["ont"], right)
                    continue

                if left.startswith("uniport-"):
                    current_block = "uni"
                    current_uniport = left
                    result["uniports"].setdefault(current_uniport, {})
                    self._parse_config_line_into(result["uniports"][current_uniport], right)
                    continue

                if left == "" and current_block == "ont":
                    self._parse_config_line_into(result["ont"], right)
                    continue
                if left == "" and current_block == "uni" and current_uniport:
                    self._parse_config_line_into(result["uniports"][current_uniport], right)
                    continue

            stripped = line.strip()
            if not stripped:
                continue

            if current_block == "ont":
                self._parse_config_line_into(result["ont"], stripped)
            elif current_block == "uni" and current_uniport:
                self._parse_config_line_into(result["uniports"][current_uniport], stripped)

        return result

    # -----------------------------
    # Parsing helpers
    # -----------------------------
    def _parse_table_any(self, raw: str, row_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Parser tolerante a:
        - separadores tipo "-----+-----" y tablas con pipes
        - tablas con múltiples bloques (unreg)
        """
        self._d(f"_parse_table_any: start row_prefix={row_prefix!r} raw chars={len(raw)}")
        lines = [l.rstrip("\r") for l in raw.splitlines() if l.strip()]
        self._d(f"_parse_table_any: non-empty lines={len(lines)}")

        headers: Optional[List[str]] = None
        rows: List[Dict[str, Any]] = []

        for i, line in enumerate(lines):
            s = line.strip()

            # separadores con "+" (unreg/detalles)
            if self.SEP_RE.match(s):
                continue

            if "Total:" in s:
                break

            if "|" in s:
                cols = [c.strip() for c in s.split("|")]

                if headers is None:
                    first = cols[0] if cols else ""
                    looks_like_aid = (
                        first.startswith("ont-")
                        or first.startswith("pon-")
                        or first.startswith("Pon_AID")
                        or first.startswith("AID")
                    )

                    # cabecera típica
                    if first in ("AID", "Pon_AID") or ("Template-ID" in s) or ("Status" in s and "Time" in s):
                        headers = cols
                        continue
                    if "SN" in cols and ("Status" in cols or "Password" in cols):
                        headers = cols
                        continue
                    if not looks_like_aid:
                        headers = cols
                        continue

                if headers is None:
                    headers = [f"col_{k}" for k in range(len(cols))]

                if len(cols) != len(headers):
                    if len(cols) < len(headers):
                        cols = cols + [""] * (len(headers) - len(cols))
                    else:
                        cols = cols[: len(headers)]

                row = dict(zip(headers, cols))

                if row_prefix:
                    first_val = cols[0].strip() if cols else ""
                    if not first_val.startswith(row_prefix):
                        continue

                rows.append(row)

        self._d(f"_parse_table_any: rows={len(rows)} headers={'set' if headers else 'None'}")
        return rows

    def _parse_config_line_into(self, target: Dict[str, Any], line: str) -> None:
        s = line.strip()
        if not s:
            return

        tokens = s.split()
        if not tokens:
            return

        if len(tokens) >= 2 and tokens[0] == "no":
            key = tokens[1].replace("-", "_")
            target[key] = False
            return

        key0 = tokens[0].replace("-", "_").lower()

        if key0 == "queue" and len(tokens) >= 4 and tokens[1] == "tc":
            entry: Dict[str, Any] = {"tc": int(tokens[2]) if tokens[2].isdigit() else tokens[2]}
            i = 3
            while i < len(tokens) - 1:
                k = tokens[i].replace("-", "_").lower()
                v = tokens[i + 1]
                entry[k] = int(v) if v.isdigit() else v
                i += 2
            target.setdefault("queues", []).append(entry)
            return

        if key0 == "bwgroup":
            target["bwgroup"] = tokens[1] if len(tokens) > 1 else ""
            i = 2
            while i < len(tokens) - 1:
                k = tokens[i].replace("-", "_").lower()
                v = tokens[i + 1]
                target[k] = v
                i += 2
            return

        if key0 == "vlan":
            entry: Dict[str, Any] = {"vlan": tokens[1] if len(tokens) > 1 else ""}
            i = 2
            while i < len(tokens) - 1:
                k = tokens[i].replace("-", "_").lower()
                v = tokens[i + 1]
                entry[k] = v
                i += 2
            target.setdefault("vlans", []).append(entry)
            return

        if len(tokens) >= 2:
            if len(tokens) == 2:
                target[key0] = tokens[1]
            else:
                target.setdefault("lines", []).append(s)
            return

        target.setdefault("flags", []).append(key0)

    # -----------------------------
    # Utilidades
    # -----------------------------
    def to_json(self, data: Any) -> str:
        return json.dumps(data, indent=2, ensure_ascii=False)

    def close(self) -> None:
        self._d("close: closing telnet session...")
        try:
            self.tn.write(b"exit" + self.eol)
        except Exception:
            pass
        try:
            self.tn.close()
        except Exception:
            pass


if __name__ == "__main__":
    pass
