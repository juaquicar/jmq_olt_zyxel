# -*- coding: utf-8 -*-
"""
OLT1240XA.py

Cliente API para interactuar con una OLT Zyxel MSC/OLT 1240XA vía Telnet.

Modelo objetivo (según tu salida real):
- Login prompt:  "MSC1240XA login:"
- Password:      "Password:"
- Prompt CLI:    "MSC1240XA#"

Mapeo de comandos (compatibilidad con la API tipo OLT2406):
- show remote ont                         -> show interface remote ont filter 1
- show remote ont unreg                   -> show interface remote ont unreg
- show remote ont {aid}                   -> show interface remote ont {aid} status
- show remote ont {aid} status-history    -> show interface remote ont {aid} status-history
- show remote ont {aid} config            -> show interface remote ont {aid} config

Notas importantes del 1240XA observado:
- En "filter 1" la tabla suele venir con 2 filas por AID: "Config" y "Actual".
  Esta implementación consolida por AID priorizando datos de la fila "Actual" cuando existan.
- AID típico: "2-16-40" (sin prefijo "ont-"). En status-history aparece "ont-2-16-40"
  en la primera columna; se soportan ambos formatos.
- Parsing tolerante: las columnas pueden venir “rotas” por el ancho de la terminal;
  se intenta reconstruir por segmentos con "|" y por patrones ("Config"/"Actual").

Mejora solicitada:
- Enriquecer get_all_onts(filter=1) con el campo "ONT Rx" a partir de:
    show interface gpon 1-* ddmi status
  Este comando lista líneas tipo:
    ont-1-1-1              -24.44
    ont-1-10-28     ++       -7.06
  Se parsea a un mapa { "ont-<aid>": "<rx>" } y se añade a cada registro por AID.

Mantiene interfaz pública similar a APIOLT2406:
- get_all_onts, get_unregistered_onts, get_ont_details, get_ont_status_history, get_ont_config, to_json, close

Incluye debug opcional + manejo ANSI/VT100 (igual enfoque que OLT2406):
- Auto-respuesta a ESC[6n con ESC[1;1R
- Detección robusta de prompt al final del buffer (puede venir sin \n)
- Dumps opcionales y volcado RAW
"""

import telnetlib
import re
import json
import time
import sys
from typing import List, Dict, Any, Optional


class APIOLT1240XA:
    """
    Cliente API para interactuar con una OLT Zyxel MSC1240XA vía Telnet.
    """

    # AID típico: 2-16-40 (>= 3 segmentos)
    AID_RE = re.compile(r"^\d+(?:-\d+){2,}$")
    AID_RE_WITH_PREFIX = re.compile(r"^(?:ont-)?\d+(?:-\d+){2,}$")

    # Pon AID típico: pon-5-15
    PON_AID_RE = re.compile(r"^pon-\d+(?:-\d+){1,}$")

    # Separadores tipo: "-----+-----"
    SEP_RE = re.compile(r"^\s*-+\s*\+\s*-+.*$")

    # ANSI / VT100
    ANSI_RE = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")

    # UnReg row:
    #   UnReg 5A5955501648EB50 DEFAULT Active
    _UNREG_ROW_RE = re.compile(
        r"^(?P<type>\S+)\s+(?P<sn>[0-9A-Fa-f]{8,32})\s+(?P<password>\S+)\s+(?P<status>\S+)\s*$"
    )

    # DDMI row examples:
    #   " ont-1-1-1              -24.44"
    #   "ont-1-10-28     ++       -7.06"
    #   "ont-1-12-8       -      -32.22"
    _DDMI_ONT_RX_RE = re.compile(
        r"^\s*(?P<ont>ont-\d+(?:-\d+){2,})\s+(?:(?:\+\+|\+|--|-)\s+)?(?P<rx>[+-]?\d+(?:\.\d+)?)\s*$"
    )

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        prompt: str = "MSC1240XA#",
        timeout: int = 30,
        login_user_prompt: bytes = b"login:",
        login_pass_prompt: bytes = b"Password:",
        debug: bool = False,
        debug_telnet_dump: bool = False,
        debug_telnet_raw_file: Optional[str] = "/tmp/olt1240xa_telnet_raw.log",
        eol: bytes = b"\r\n",
        ddmi_timeout: int = 120,  # el ddmi status puede tardar bastante
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password

        self.prompt = prompt
        self.timeout = timeout
        self.ddmi_timeout = ddmi_timeout

        self.login_user_prompt = login_user_prompt
        self.login_pass_prompt = login_pass_prompt
        self.debug = debug
        self.debug_telnet_dump = debug_telnet_dump
        self.debug_telnet_raw_file = debug_telnet_raw_file
        self.eol = eol

        # Prompt detection robusto
        self._prompt_end_re = re.compile(re.escape(self.prompt).encode("ascii") + rb"\s*$")
        self._prompt_only_re = re.compile(rb"^\s*" + re.escape(self.prompt).encode("ascii") + rb"\s*$")

        self.tn = telnetlib.Telnet()

        self._d(
            "Init APIOLT1240XA "
            f"(host={self.host}, port={self.port}, timeout={self.timeout}, "
            f"ddmi_timeout={self.ddmi_timeout}, "
            f"prompt={self.prompt!r}, debug={self.debug}, "
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
        return self.ANSI_RE.sub(b"", raw)

    def _dump_telnet(self, context: str, raw: bytes) -> None:
        if not self.debug:
            return

        if self.debug_telnet_raw_file:
            try:
                with open(self.debug_telnet_raw_file, "ab") as f:
                    header = f"\n\n===== {self._ts()} {context} =====\n".encode("utf-8", errors="ignore")
                    f.write(header)
                    f.write(raw)
            except Exception as e:
                self._d(f"_dump_telnet: error escribiendo RAW a fichero => {e!r}")

        if not self.debug_telnet_dump:
            return

        # print(f"[{self._ts()}] [TELNET] --- {context} START ---")
        try:
            safe = self._strip_ansi(raw)
            txt = safe.decode("latin-1", errors="strict")
        except Exception:
            txt = raw.decode("utf-8", errors="replace")

        sys.stdout.write(txt)
        sys.stdout.flush()
        if not txt.endswith("\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
        # print(f"[{self._ts()}] [TELNET] --- {context} END ---")

    # -----------------------------
    # ANSI/VT100 autoresponse
    # -----------------------------
    def _ansi_autoreply(self, data: bytes) -> None:
        # Algunos equipos consultan posición del cursor con ESC[6n.
        # Si no respondes, la CLI puede quedarse a medias.
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
        self._dump_telnet("POST-LOGIN", buf)

        self._d("Post-login: forcing resync newline para obtener prompt...")
        self.tn.write(self.eol)
        buf2 = self._read_until_prompt(timeout=min(5, self.timeout), require_progress=False, context="POST-LOGIN-RESYNC")
        self._dump_telnet("POST-LOGIN-RESYNC", buf2)

        self._d("Sesión iniciada (si hay prompt visible en dumps).")

    def _drain_input(self, drain_for: float = 0.25) -> bytes:
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
        tmp = buf.strip(b"\r\n\t ")
        if not tmp:
            return False
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
                self._ansi_autoreply(chunk)
                buf += chunk

                if not saw_progress and self._has_real_progress(buf):
                    saw_progress = True

                now = time.time()
                if self.debug and (now - last_stat) >= 0.8:
                    last_stat = now
                    self._d(f"_read_until_prompt: bytes={len(buf)} saw_progress={saw_progress}")

                if self._prompt_end_re.search(buf.rstrip(b"\r\n")):
                    if require_progress and not saw_progress:
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
        self._d("_resync_cli: enviando EOL para resincronizar...")
        self.tn.write(self.eol)
        buf = self._read_until_prompt(timeout=min(5, self.timeout), require_progress=False, context="RESYNC")
        self._dump_telnet("RESYNC", buf)
        _ = self._drain_input(drain_for=0.15)

    def _send_command(self, command: str, *, timeout: Optional[int] = None) -> str:
        """
        Ejecuta comando y devuelve salida sin prompt final y sin eco del comando.
        Permite timeout específico (p.e. ddmi).
        """
        if timeout is None:
            timeout = self.timeout

        self._d(f"_send_command: preparando comando={command!r} timeout={timeout}")

        self._resync_cli()
        _ = self._drain_input(drain_for=0.2)

        self._d(f"CMD => {command}")
        self.tn.write(command.encode("ascii", errors="ignore") + self.eol)

        raw = self._read_until_prompt(timeout=timeout, require_progress=True, context=f"CMD:{command}")
        self._dump_telnet(f"CMD OUTPUT: {command}", raw)

        m = self._prompt_end_re.search(raw.rstrip(b"\r\n"))
        raw_wo_prompt = raw[: m.start()] if m else raw

        out = raw_wo_prompt.decode("latin-1", errors="ignore")

        # limpiar eco del comando y vacíos iniciales
        lines = out.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and lines[0].strip() == command.strip():
            lines.pop(0)

        return "\n".join(lines).strip("\n")

    # -----------------------------
    # DDMI helpers (ONT Rx)
    # -----------------------------
    def _get_ddmi_rx_map(self) -> Dict[str, str]:
        """
        Ejecuta 'show interface gpon 1-* ddmi status' y devuelve:
          { "ont-1-1-1": "-24.44", "ont-1-10-28": "-7.06", ... }
        """
        cmd = "show interface gpon 1-* ddmi status"
        self._d(f"_get_ddmi_rx_map: ejecutando {cmd!r} (timeout={self.ddmi_timeout})")
        raw = self._send_command(cmd, timeout=self.ddmi_timeout)

        rx_map: Dict[str, str] = {}
        for line in raw.splitlines():
            m = self._DDMI_ONT_RX_RE.match(line.rstrip())
            if not m:
                continue
            ont = m.group("ont").strip()
            rx = m.group("rx").strip()
            rx_map[ont] = rx

        self._d(f"_get_ddmi_rx_map: {len(rx_map)} ONTs con potencia Rx parseadas.")
        return rx_map

    # -----------------------------
    # API pública (mismos nombres)
    # -----------------------------
    def get_all_onts(self, filter: str, *, enrich_rx: bool = True) -> List[Dict[str, Any]]:
        """
        Equivalente a OLT2406.get_all_onts(1) pero en 1240XA:
          show interface remote ont filter 1

        La salida real suele traer 2 filas por AID: "Config" y "Actual".
        Se consolida por AID, priorizando datos de "Actual" cuando exista.

        enrich_rx=True:
          añade "ONT Rx" mediante ddmi status (una sola consulta global).
        """
        raw = self._send_command(f"show interface remote ont filter {filter}")
        onts = self._parse_all_onts_filter1(raw)

        if enrich_rx and onts:
            rx_map = self._get_ddmi_rx_map()
            for rec in onts:
                aid = str(rec.get("AID", "")).strip()
                if not aid:
                    rec.setdefault("ONT Rx", "")
                    continue
                key = f"ont-{aid}"
                rec["ONT Rx"] = rx_map.get(key, "")

        return onts[:5]

    def get_unregistered_onts(self) -> List[Dict[str, Any]]:
        raw = self._send_command("show interface remote ont unreg")
        return self._parse_unreg_onts(raw)

    def get_ont_details(self, aid: str) -> Dict[str, Any]:
        """
        show interface remote ont {aid} status
        Devuelve dict plano clave:valor (parseo por ":").
        """
        self._d(f"get_ont_details: start aid={aid!r}")
        aid_norm = self._normalize_aid(aid)
        raw = self._send_command(f"show interface remote ont {aid_norm} status")
        return self._parse_kv_colon_blocks(raw)

    def get_ont_status_history(self, aid: str) -> List[Dict[str, Any]]:
        """
        show interface remote ont {aid} status-history
        Devuelve lista [{status, tt}, ...]
        """
        aid_norm = self._normalize_aid(aid)
        raw = self._send_command(f"show interface remote ont {aid_norm} status-history")
        return self._parse_status_history(raw)

    def get_ont_config(self, aid: str) -> Dict[str, Any]:
        """
        show interface remote ont {aid} config
        Devuelve estructura:
          {"aid": "...", "ont": {...}, "uni": {...}}

        En 1240XA los sub-bloques suelen venir como:
          2-16-40        | ...
          2-16-40-2-1    | ...
        """
        aid_norm = self._normalize_aid(aid)
        raw = self._send_command(f"show interface remote ont {aid_norm} config")
        return self._parse_config_1240xa(aid_norm, raw)

    # -----------------------------
    # Parsing helpers
    # -----------------------------
    def _normalize_aid(self, aid: str) -> str:
        a = aid.strip()
        if a.startswith("ont-"):
            a = a[4:]
        return a

    def _parse_unreg_onts(self, raw: str) -> List[Dict[str, Any]]:
        """
        Formato real:
          Pon_AID | Type SN Password Status
          pon-x-y | UnReg <SN> DEFAULT Active
        """
        lines = [l.rstrip("\r") for l in raw.splitlines() if l.strip()]
        rows: List[Dict[str, Any]] = []

        for line in lines:
            s = line.rstrip()

            if self.SEP_RE.match(s.strip()):
                continue
            if s.strip().startswith("Pon_AID"):
                continue
            if "|" not in s:
                continue

            left, right = s.split("|", 1)
            pon_aid = left.strip()
            right = right.strip()

            if not pon_aid.startswith("pon-"):
                continue

            right_norm = " ".join(right.split())
            m = self._UNREG_ROW_RE.match(right_norm)
            if not m:
                rows.append({"Pon_AID": pon_aid, "raw": right})
                continue

            rows.append(
                {
                    "Pon_AID": pon_aid,
                    "Type": m.group("type"),
                    "SN": m.group("sn"),
                    "Password": m.group("password"),
                    "Status": m.group("status"),
                }
            )

        return rows

    def _parse_kv_colon_blocks(self, raw: str) -> Dict[str, Any]:
        """
        Parser simple para bloques con "Key : Value" (muy típico en status).
        Tolera prefijos con "|" y separadores.
        """
        details: Dict[str, Any] = {}
        for line in raw.splitlines():
            s = line.strip()
            if not s:
                continue
            if self.SEP_RE.match(s):
                continue

            # Quitar bordes de tabla
            s = s.lstrip("|").strip()
            if ":" not in s:
                continue

            key, val = s.split(":", 1)
            k = key.strip()
            v = val.strip()
            if k:
                details[k] = v

        return details

    def _parse_status_history(self, raw: str) -> List[Dict[str, Any]]:
        """
        Ejemplo real:
          AID | Status Time
          ont-2-16-40 | 1 IS 2026/ 1/14 16:16:27
        """
        lines = [l.rstrip("\r") for l in raw.splitlines() if l.strip()]
        history: List[Dict[str, Any]] = []

        for line in lines:
            s = line.strip()
            if self.SEP_RE.match(s):
                continue
            if s.startswith("AID") and "Status" in s and "Time" in s:
                continue
            if "|" not in s:
                continue

            _, right = s.split("|", 1)
            right = right.strip()
            if not right:
                continue

            # "1 IS 2026/ 1/14 16:16:27"
            tokens = right.split()
            if len(tokens) < 4:
                continue

            status = tokens[1]
            time_str = " ".join(tokens[2:])
            history.append({"status": status, "tt": time_str})

        return history

    def _parse_all_onts_filter1(self, raw: str) -> List[Dict[str, Any]]:
        lines = [l.rstrip("\r") for l in raw.splitlines() if l.strip()]
        by_aid: Dict[str, Dict[str, Any]] = {}

        header_seen = False
        for line in lines:
            s = line.rstrip()
            if self.SEP_RE.match(s.strip()):
                continue

            # Cabecera
            if ("AID" in s) and ("Vendor/Model" in s):
                header_seen = True
                continue
            if not header_seen:
                continue

            # Resumen final
            if s.strip().startswith("slot ") and " has " in s and " ont" in s:
                continue

            if "|" not in s:
                continue

            parts = [p.strip() for p in s.split("|")]
            if not parts:
                continue

            aid = parts[0].strip()
            if not aid or not self.AID_RE.match(aid):
                continue

            rest = " | ".join(parts[1:]).strip()
            rest_norm = " ".join(rest.split())

            row_type = None
            if rest_norm.startswith("Config ") or " Config " in f" {rest_norm} ":
                row_type = "Config"
            elif rest_norm.startswith("Actual ") or " Actual " in f" {rest_norm} ":
                row_type = "Actual"

            if row_type is None:
                if self.debug:
                    rec_dbg = by_aid.setdefault(aid, {"AID": aid})
                    rec_dbg.setdefault("_raw_rows", []).append(rest)
                continue

            parsed = self._parse_filter1_row_payload(rest_norm, row_type=row_type)
            if not parsed:
                if self.debug:
                    rec_dbg = by_aid.setdefault(aid, {"AID": aid})
                    rec_dbg.setdefault("_raw_rows", []).append(rest)
                continue

            rec = by_aid.setdefault(aid, {"AID": aid})
            rec.setdefault("_rows", {})
            rec["_rows"][row_type] = parsed

            chosen = rec["_rows"].get("Actual") or rec["_rows"].get("Config") or {}
            self._apply_chosen_row_to_record(rec, chosen)

        out: List[Dict[str, Any]] = []
        for _, rec in by_aid.items():
            rec.pop("_rows", None)
            if not self.debug:
                rec.pop("_raw_rows", None)
            out.append(rec)

        out.sort(key=lambda x: x.get("AID", ""))
        return out  # <- importante: devolver TODO (sin cortar a 5)

    def _parse_filter1_row_payload(self, rest_norm: str, row_type: str) -> Optional[Dict[str, Any]]:
        """
        Parseo heurístico de la parte derecha para una fila Config/Actual.

        Objetivo mínimo:
          Type, SN, Password, Status, Image, Active, Version, Vendor, Model
        """
        tokens = rest_norm.split()
        if len(tokens) < 5:
            return None

        if tokens[0] not in ("Config", "Actual"):
            # permitimos forzar
            pass

        t0 = tokens[0] if tokens[0] in ("Config", "Actual") else row_type

        # Buscar SN (hex 8..32)
        sn_idx = None
        for i, tok in enumerate(tokens):
            if re.fullmatch(r"[0-9A-Fa-f]{8,32}", tok):
                sn_idx = i
                break
        if sn_idx is None:
            return None

        typ = t0
        sn = tokens[sn_idx]
        password = tokens[sn_idx + 1] if sn_idx + 1 < len(tokens) else ""
        status = tokens[sn_idx + 2] if sn_idx + 2 < len(tokens) else ""

        image = ""
        active = ""
        version = ""
        vendor_model = ""

        tail = tokens[sn_idx + 3 :] if (sn_idx + 3) < len(tokens) else []

        if tail:
            if re.fullmatch(r"\d+", tail[0]):
                image = tail[0]
                tail = tail[1:]

        if tail:
            if tail[0].upper() == "V":
                active = "V"
                tail = tail[1:]
            if tail and tail[0].upper() == "V":
                if not active:
                    active = "V"
                tail = tail[1:]

        if tail:
            if tail[0].startswith("V"):
                version = tail[0]
                tail = tail[1:]

        if tail:
            vendor_model = " ".join(tail)

        parsed: Dict[str, Any] = {
            "Type": typ,
            "SN": sn,
            "Password": password,
            "Status": status,
        }
        if image:
            parsed["Image"] = image
        if active:
            parsed["Active"] = active
        if version:
            parsed["Version"] = version

        if vendor_model:
            if re.fullmatch(r"[A-Za-z]{3,6}", vendor_model) or vendor_model.upper().startswith("ZY"):
                parsed["Vendor"] = vendor_model
            else:
                parsed["Model"] = vendor_model

        return parsed

    def _apply_chosen_row_to_record(self, rec: Dict[str, Any], chosen: Dict[str, Any]) -> None:
        for k in ("SN", "Password", "Status"):
            if k in chosen and chosen[k] != "":
                rec[k] = chosen[k]

        if "Model" in chosen and chosen["Model"]:
            rec["Model"] = chosen["Model"]
        if "Vendor" in chosen and chosen["Vendor"]:
            rec["Vendor"] = chosen["Vendor"]

        if "Version" in chosen and chosen["Version"]:
            rec["FW Version"] = chosen["Version"]

        if "Type" in chosen and chosen["Type"]:
            rec["Type"] = chosen["Type"]

        if "Image" in chosen and chosen["Image"]:
            rec["Image"] = chosen["Image"]
        if "Active" in chosen and chosen["Active"]:
            rec["Active"] = chosen["Active"]

    def _parse_config_1240xa(self, aid: str, raw: str) -> Dict[str, Any]:
        lines = [l.rstrip("\r") for l in raw.splitlines() if l.strip()]
        result: Dict[str, Any] = {"aid": aid, "ont": {}, "uni": {}}

        current_block: Optional[str] = None
        current_uni: Optional[str] = None

        for line in lines:
            s = line.strip()
            if not s:
                continue
            if self.SEP_RE.match(s):
                continue
            if s.startswith("AID") and "Details" in s:
                continue

            if "|" in s:
                left, right = s.split("|", 1)
                left = left.strip()
                right = right.strip()

                if left == aid or left == f"ont-{aid}":
                    current_block = "ont"
                    current_uni = None
                    self._parse_config_line_into(result["ont"], right)
                    continue

                if left.startswith(aid + "-") or left.startswith(f"ont-{aid}-"):
                    current_block = "uni"
                    current_uni = left
                    result["uni"].setdefault(current_uni, {})
                    self._parse_config_line_into(result["uni"][current_uni], right)
                    continue

                if left == "" and current_block == "ont":
                    self._parse_config_line_into(result["ont"], right)
                    continue
                if left == "" and current_block == "uni" and current_uni:
                    self._parse_config_line_into(result["uni"][current_uni], right)
                    continue

            if current_block == "ont":
                self._parse_config_line_into(result["ont"], s)
            elif current_block == "uni" and current_uni:
                self._parse_config_line_into(result["uni"][current_uni], s)

        return result

    def _parse_config_line_into(self, target: Dict[str, Any], line: str) -> None:
        s = line.strip()
        if not s:
            return

        chunks = [c.strip() for c in s.split("|") if c.strip()]
        for chunk in chunks:
            self._parse_config_chunk_into(target, chunk)

    def _parse_config_chunk_into(self, target: Dict[str, Any], s: str) -> None:
        tokens = s.split()
        if not tokens:
            return

        if len(tokens) >= 2 and tokens[0] == "no":
            key = tokens[1].replace("-", "_").lower()
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

        if len(tokens) == 2:
            target[key0] = tokens[1]
            return

        target.setdefault("lines", []).append(s)

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
