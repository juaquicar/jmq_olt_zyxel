# -*- coding: utf-8 -*-
import telnetlib
import re
import json
import time
from typing import List, Dict, Any, Optional


class APIOLT2406:
    """
    Cliente API para OLT Zyxel 2406 vía Telnet.

    FIXES:
      - Prompt variable: a veces 'OLT2406#' y a veces 'OLT2406# ' (con espacio).
      - Lectura robusta: no dependemos de read_until(prompt_literal).
      - Resincronización de CLI antes de cada comando.
    """

    AID_RE = re.compile(r"^ont-\d+(?:-\d+){1,}$")
    SEP_RE = re.compile(r"^\s*-{2,}(\+-{2,})+\s*$")

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        prompt_base: str = "OLT2406#",   # base sin espacio
        timeout: int = 30,
        login_user_prompt: bytes = b"User name:",
        login_pass_prompt: bytes = b"Password:",
        debug: bool = False,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password

        # Prompt “base” + variantes típicas observadas
        self.prompt_base_str = prompt_base
        self.prompt_variants = [
            prompt_base.encode("ascii", errors="ignore"),
            (prompt_base + " ").encode("ascii", errors="ignore"),
        ]

        self.timeout = timeout
        self.login_user_prompt = login_user_prompt
        self.login_pass_prompt = login_pass_prompt
        self.debug = debug

        self.tn = telnetlib.Telnet()
        self._open_session()

    def _dprint(self, *args):
        if self.debug:
            print("[DEBUG]", *args)

    def _flush(self) -> None:
        try:
            _ = self.tn.read_very_eager()
        except Exception:
            pass

    def _buffer_has_prompt(self, buf: bytes) -> bool:
        return any(p in buf for p in self.prompt_variants)

    def _strip_trailing_prompt_lines(self, text: str) -> str:
        lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
        # Quita líneas finales que sean solo el prompt (con o sin espacio)
        while lines:
            last = lines[-1].strip()
            if last == self.prompt_base_str.strip():
                lines.pop()
                continue
            # algunas veces viene con espacios
            if last.startswith(self.prompt_base_str) and last.rstrip() == self.prompt_base_str:
                lines.pop()
                continue
            break
        return "\n".join(lines)

    def _read_until_any_prompt(self, overall_timeout: int) -> str:
        """
        Lee acumulando hasta que aparezca cualquiera de los prompts.
        """
        deadline = time.time() + overall_timeout
        buf = b""

        # Espera breve inicial para que el equipo empiece a emitir salida
        time.sleep(0.05)

        while time.time() < deadline:
            try:
                chunk = self.tn.read_very_eager()
            except EOFError:
                break
            except Exception:
                chunk = b""

            if chunk:
                buf += chunk
                if self._buffer_has_prompt(buf):
                    break
            else:
                time.sleep(0.05)

        # Decodifica
        return buf.decode("ascii", errors="ignore").replace("\r\n", "\n").replace("\r", "\n")

    def _sync_prompt(self, tries: int = 3) -> None:
        """
        Resincroniza el estado de la CLI:
          - manda ENTER
          - lee hasta ver prompt (cualquiera)
          - flush final
        """
        for _ in range(tries):
            self.tn.write(b"\r\n")
            _ = self._read_until_any_prompt(overall_timeout=2)
            # Si ya vimos prompt, suficiente
            # (No lo chequeamos por texto, lo chequeamos por buffer en read loop)
            # En caso de duda, repetimos.
        self._flush()

    def _open_session(self):
        self.tn.open(self.host, self.port, timeout=self.timeout)

        self.tn.read_until(self.login_user_prompt, timeout=self.timeout)
        self.tn.write(self.username.encode("ascii", errors="ignore") + b"\r\n")

        self.tn.read_until(self.login_pass_prompt, timeout=self.timeout)
        self.tn.write(self.password.encode("ascii", errors="ignore") + b"\r\n")

        # Consumimos hasta prompt (cualquiera)
        _ = self._read_until_any_prompt(overall_timeout=self.timeout)
        self._sync_prompt()

        self._dprint("Sesión iniciada correctamente contra", self.host, ":", self.port)

    def _send_command(self, command: str, overall_timeout: Optional[int] = None) -> str:
        if overall_timeout is None:
            overall_timeout = self.timeout

        # 1) asegurar CLI sincronizada
        self._sync_prompt()

        # 2) enviar comando
        self.tn.write(command.encode("ascii", errors="ignore") + b"\r\n")

        # 3) leer hasta prompt (cualquiera)
        raw = self._read_until_any_prompt(overall_timeout=overall_timeout)

        # Debug raw
        if self.debug:
            raw_lines = [l for l in raw.splitlines()]
            self._dprint(f"CMD: {command}")
            self._dprint(f"RAW lines={len(raw_lines)} chars={len(raw)}")
            if raw_lines:
                self._dprint("RAW FIRST:", repr(raw_lines[0]))
                self._dprint("RAW LAST: ", repr(raw_lines[-1]))

        # 4) quitar prompt final
        raw = self._strip_trailing_prompt_lines(raw).strip("\n")

        # 5) quitar eco del comando si aparece como primera línea
        lines = raw.splitlines()
        if lines and lines[0].strip() == command:
            lines.pop(0)
        text = "\n".join(lines).strip("\n")

        if self.debug and not text:
            self._dprint("EMPTY TEXT after cleanup.")

        return text

    def _validate_aid(self, aid: str) -> None:
        if not self.AID_RE.match(aid):
            raise ValueError(f"AID inválido: '{aid}'.")

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def get_all_onts(self) -> List[Dict[str, Any]]:
        raw = self._send_command("show remote ont", overall_timeout=max(self.timeout, 120))
        return self._parse_table(raw, row_prefix="ont-")

    def get_unregistered_onts(self) -> List[Dict[str, Any]]:
        raw = self._send_command("show remote ont unreg", overall_timeout=max(self.timeout, 30))
        return self._parse_table(raw, row_prefix=None)

    def get_ont_details(self, aid: str) -> Dict[str, Any]:
        self._validate_aid(aid)
        raw = self._send_command(f"show remote ont {aid}", overall_timeout=max(self.timeout, 30))

        details: Dict[str, Any] = {}
        for line in raw.splitlines():
            if ":" not in line:
                continue
            cleaned = line.lstrip(" |").strip()
            if ":" not in cleaned:
                continue
            key, val = cleaned.split(":", 1)
            details[key.strip()] = val.strip()
        return details

    def get_ont_status_history(self, aid: str) -> List[Dict[str, str]]:
        self._validate_aid(aid)
        raw = self._send_command(f"show remote ont {aid} status-history", overall_timeout=max(self.timeout, 30))
        return self._parse_status_history(raw)

    def get_ont_config(self, aid: str) -> Dict[str, Any]:
        self._validate_aid(aid)
        raw = self._send_command(f"show remote ont {aid} config", overall_timeout=max(self.timeout, 60))
        lines = raw.splitlines()

        result: Dict[str, Any] = {"ont": {}, "uni": {}}
        block: Optional[str] = None

        for line in lines:
            if self.SEP_RE.match(line.strip()):
                continue

            stripped = line.strip()
            if stripped.startswith(aid):
                block = "ont"
                continue
            if stripped.startswith("uniport-"):
                block = "uni"
                continue
            if not block:
                continue

            content = line.lstrip(" |").strip()
            if not content:
                continue

            tokens = content.split()
            if block == "ont":
                key = tokens[0].lower()
                if key in ["sn", "password", "full-bridge", "description", "plan-version", "alarm-profile", "anti-mac-spoofing"]:
                    if len(tokens) >= 2:
                        result["ont"][key.replace("-", "_")] = " ".join(tokens[1:])
                elif key == "bwgroup":
                    if len(tokens) >= 2:
                        result["ont"]["bwgroup"] = tokens[1]
                    for i, t in enumerate(tokens):
                        if t == "usbwprofname" and i + 1 < len(tokens):
                            result["ont"]["usbwprofname"] = tokens[i + 1]
                        if t == "dsbwprofname" and i + 1 < len(tokens):
                            result["ont"]["dsbwprofname"] = tokens[i + 1]
                        if t == "allocid" and i + 1 < len(tokens):
                            result["ont"]["allocid"] = tokens[i + 1]
            else:
                if len(tokens) >= 2 and tokens[0] == "no" and tokens[1] == "inactive":
                    result["uni"]["active"] = True
                elif len(tokens) >= 2 and tokens[0] == "no" and tokens[1] == "pmenable":
                    result["uni"]["pmenable"] = False
                elif len(tokens) >= 3 and tokens[0] == "queue" and tokens[1] == "tc":
                    entry: Dict[str, Any] = {"tc": int(tokens[2])}
                    for i, t in enumerate(tokens):
                        if t == "priority" and i + 1 < len(tokens):
                            entry["priority"] = int(tokens[i + 1])
                        if t == "weight" and i + 1 < len(tokens):
                            entry["weight"] = int(tokens[i + 1])
                        if t == "usbwprofname" and i + 1 < len(tokens):
                            entry["usbwprofname"] = tokens[i + 1]
                        if t == "dsbwprofname" and i + 1 < len(tokens):
                            entry["dsbwprofname"] = tokens[i + 1]
                        if t == "dsoption" and i + 1 < len(tokens):
                            entry["dsoption"] = tokens[i + 1]
                        if t == "bwsharegroupid" and i + 1 < len(tokens):
                            entry["bwsharegroupid"] = tokens[i + 1]
                    result["uni"].setdefault("queues", []).append(entry)
                elif tokens and tokens[0] == "vlan" and len(tokens) >= 2:
                    vlan_entry: Dict[str, Any] = {"vlan": tokens[1]}
                    for i, t in enumerate(tokens):
                        if t == "network" and i + 1 < len(tokens):
                            vlan_entry["network"] = tokens[i + 1]
                        if t == "gemport" and i + 1 < len(tokens):
                            vlan_entry["gemport"] = tokens[i + 1]
                        if t == "ingprof" and i + 1 < len(tokens):
                            vlan_entry["ingprof"] = tokens[i + 1]
                        if t == "aesencrypt" and i + 1 < len(tokens):
                            vlan_entry["aesencrypt"] = tokens[i + 1]
                    result["uni"].setdefault("vlans", []).append(vlan_entry)

        return result

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------
    def _find_table_header_and_sep(self, lines: List[str]) -> Optional[Dict[str, int]]:
        for i in range(len(lines) - 1):
            if "|" in lines[i] and self.SEP_RE.match(lines[i + 1].strip()):
                return {"header": i, "sep": i + 1}
        return None

    def _parse_table(self, raw: str, row_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        meta = self._find_table_header_and_sep(lines)
        if not meta:
            return []

        headers = [h.strip() for h in lines[meta["header"]].split("|")]
        data: List[Dict[str, Any]] = []

        for line in lines[meta["sep"] + 1 :]:
            s = line.strip()
            if s.startswith("Total:"):
                break
            if self.SEP_RE.match(s):
                continue
            if row_prefix and not s.startswith(row_prefix):
                continue

            cols = [c.strip() for c in line.split("|")]
            if len(cols) < len(headers):
                cols += [""] * (len(headers) - len(cols))
            elif len(cols) > len(headers):
                cols = cols[: len(headers)]
            data.append(dict(zip(headers, cols)))

        return data

    def _parse_status_history(self, raw: str) -> List[Dict[str, str]]:
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        meta = self._find_table_header_and_sep(lines)
        if not meta:
            return []

        history: List[Dict[str, str]] = []
        for line in lines[meta["sep"] + 1 :]:
            s = line.strip()
            if self.SEP_RE.match(s):
                continue
            parts = line.split("|")
            right = parts[-1].strip()
            tokens = right.split()
            if len(tokens) < 3:
                continue
            history.append({"status": tokens[1], "tt": " ".join(tokens[2:])})
        return history

    def to_json(self, data: Any) -> str:
        return json.dumps(data, indent=2, ensure_ascii=False)

    def close(self) -> None:
        try:
            self.tn.write(b"exit\r\n")
        except Exception:
            pass
        self.tn.close()
