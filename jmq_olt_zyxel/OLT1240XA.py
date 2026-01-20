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
- En "filter X" la tabla suele venir con 2 filas por AID: "Config" y "Actual".
  Esta implementación consolida por AID priorizando datos de la fila "Actual" cuando existan.
- AID típico: "5-1-1" / "2-16-40" (sin prefijo "ont-").

Mejora:
- Enriquecer get_all_onts(filter=X) con el campo "ONT Rx" a partir de:
    show interface gpon <slot>-* ddmi status

  Donde típicamente:
    - filter=1 -> AIDs tipo "1-..." -> gpon 1-*
    - filter=5 -> AIDs tipo "5-..." -> gpon 5-*

  Esta implementación:
    - Infere automáticamente los slots a consultar leyendo el primer segmento del AID (antes del primer '-').
    - Ejecuta ddmi status por cada slot encontrado y crea un mapa {"ont-<aid>": "<rx>"}.
    - Añade "ONT Rx" a cada registro (si hay match).
"""

import telnetlib
import re
import json
import time
import sys
from typing import List, Dict, Any, Optional, Tuple, Set


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

    # DDMI helpers: capturar ont-id al inicio y el último float al final (tolerante a "++", "-", etc.)
    _DDMI_ONT_ID_RE = re.compile(r"^\s*(?P<ont>ont-\d+(?:-\d+){2,})\b", re.IGNORECASE)
    _DDMI_LAST_FLOAT_RE = re.compile(r"(?P<rx>[+-]?\d+(?:\.\d+)?)\s*$")

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        prompt: str = "MSC1240XA#",
        timeout: int = 30,
        login_user_prompt: bytes = b"MSC1240XA login:",
        login_pass_prompt: bytes = b"Password:",
        debug: bool = False,
        debug_telnet_dump: bool = False,
        debug_telnet_raw_file: Optional[str] = "/tmp/olt1240xa_telnet_raw.log",
        eol: bytes = b"\r\n",
        ddmi_timeout: int = 120,  # ddmi status puede tardar bastante
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
                    self._d(f"_read_until_prompt({context}): bytes={len(buf)} saw_progress={saw_progress}")

                if self._prompt_end_re.search(buf.rstrip(b"\r\n")):
                    if require_progress and not saw_progress:
                        continue
                    return buf
            else:
                time.sleep(0.05)

        self._d(f"_read_until_prompt({context}): TIMEOUT (bytes={len(buf)})")
        if buf:
            self._dump_telnet(f"{context}-TIMEOUT-BUF", buf)
        return buf

    def _resync_cli(self) -> None:
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

        self._resync_cli()
        _ = self._drain_input(drain_for=0.2)

        self._d(f"CMD => {command!r} timeout={timeout}")
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
    def _infer_slots_from_onts(self, onts: List[Dict[str, Any]], filter_value: str) -> List[int]:
        """
        Inferir slots a partir de AIDs "S-P-O..." -> S.
        Si no puede, fallback a filter_value si es numérico.
        """
        slots: Set[int] = set()
        for rec in onts:
            aid = str(rec.get("AID", "")).strip()
            if not aid or "-" not in aid:
                continue
            s0 = aid.split("-", 1)[0]
            if s0.isdigit():
                slots.add(int(s0))

        if not slots and str(filter_value).strip().isdigit():
            slots.add(int(str(filter_value).strip()))

        return sorted(slots)

    def _get_ddmi_rx_map_for_slot(self, slot: int) -> Dict[str, str]:
        """
        Ejecuta:
          show interface gpon <slot>-* ddmi status
        y devuelve { "ont-<aid>": "<rx>" } para ese slot.
        """
        cmd = f"show interface gpon {slot}-* ddmi status"
        self._d(f"_get_ddmi_rx_map_for_slot: {cmd!r} (timeout={self.ddmi_timeout})")
        raw = self._send_command(cmd, timeout=self.ddmi_timeout)

        rx_map: Dict[str, str] = {}
        for line in raw.splitlines():
            s = line.rstrip("\r")
            m_id = self._DDMI_ONT_ID_RE.match(s)
            if not m_id:
                continue
            ont = m_id.group("ont").strip()
            m_rx = self._DDMI_LAST_FLOAT_RE.search(s.strip())
            if not m_rx:
                continue
            rx = m_rx.group("rx").strip()
            rx_map[ont] = rx

        self._d(f"_get_ddmi_rx_map_for_slot({slot}): {len(rx_map)} ONTs parseadas.")
        return rx_map

    def _get_ddmi_rx_map_for_slots(self, slots: List[int]) -> Dict[str, str]:
        merged: Dict[str, str] = {}
        for slot in slots:
            try:
                merged.update(self._get_ddmi_rx_map_for_slot(slot))
            except Exception as e:
                self._d(f"DDMI slot={slot}: error => {e!r}")
        self._d(f"_get_ddmi_rx_map_for_slots: total {len(merged)} ONTs en mapa Rx.")
        return merged

    # -----------------------------
    # API pública
    # -----------------------------
    def get_all_onts(self, filter: str, *, enrich_rx: bool = True) -> List[Dict[str, Any]]:
        """
        show interface remote ont filter <filter>

        Enrich Rx:
          - infiere slot(s) desde los AIDs (p.ej. 1-..., 5-...)
          - ejecuta ddmi status por slot: show interface gpon <slot>-* ddmi status
          - añade "ONT Rx"
        """
        raw = self._send_command(f"show interface remote ont filter {filter}")
        onts = self._parse_all_onts_filter(raw)

        if enrich_rx and onts:
            slots = self._infer_slots_from_onts(onts, filter_value=filter)
            self._d(f"Enrich Rx: slots inferidos => {slots}")
            rx_map = self._get_ddmi_rx_map_for_slots(slots)

            # aplicar enrichment sin “romper” si no hay match
            for rec in onts:
                aid = str(rec.get("AID", "")).strip()
                if not aid:
                    rec.setdefault("ONT Rx", "")
                    continue
                key = f"ont-{aid}"
                if key in rx_map and rx_map[key] != "":
                    rec["ONT Rx"] = rx_map[key]
                else:
                    rec.setdefault("ONT Rx", "")

        return onts

    def get_unregistered_onts(self) -> List[Dict[str, Any]]:
        raw = self._send_command("show interface remote ont unreg")
        return self._parse_unreg_onts(raw)

    def get_ont_details(self, aid: str) -> Dict[str, Any]:
        aid_norm = self._normalize_aid(aid)
        raw = self._send_command(f"show interface remote ont {aid_norm} status")
        return self._parse_kv_colon_blocks(raw)

    def get_ont_status_history(self, aid: str) -> List[Dict[str, Any]]:
        aid_norm = self._normalize_aid(aid)
        raw = self._send_command(f"show interface remote ont {aid_norm} status-history")
        return self._parse_status_history(raw)

    def get_ont_config(self, aid: str) -> Dict[str, Any]:
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
        Formato:
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
        Parser simple para bloques con "Key : Value".
        Tolera prefijos con "|" y separadores.
        """
        details: Dict[str, Any] = {}
        for line in raw.splitlines():
            s = line.strip()
            if not s:
                continue
            if self.SEP_RE.match(s):
                continue

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
        Ejemplo:
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

            tokens = right.split()
            if len(tokens) < 4:
                continue

            status = tokens[1]
            time_str = " ".join(tokens[2:])
            history.append({"status": status, "tt": time_str})

        return history

    def _parse_image_active_version(self, s: str) -> Tuple[str, str, str]:
        """
        Segmento típico: "<image> [V] [V] <version>"
        """
        ss = " ".join(s.split())
        if not ss:
            return "", "", ""

        toks = ss.split()
        if not toks:
            return "", "", ""

        image = toks[0] if toks[0].isdigit() else ""
        rest = toks[1:] if image else toks[:]

        active = ""
        while rest and rest[0].upper() == "V":
            active = "V"
            rest = rest[1:]

        version = ""
        if rest:
            cand = rest[0]
            if re.fullmatch(r"V[0-9A-Za-z._-]{3,}", cand):
                version = cand

        return image, active, version

    def _parse_remote_ont_filter_row(self, line: str, *, last_aid: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Parsea una línea de tabla:
          AID | Type SN Password Status | Image Active Version | Vendor/Model

        La línea "continuación" de Actual suele venir con AID vacío (hereda last_aid).
        """
        parts = [p.strip() for p in line.split("|")]
        while len(parts) < 4:
            parts.append("")

        aid = parts[0].strip()
        mid = parts[1].strip()
        imgver = parts[2].strip()
        vend_model = parts[3].strip()

        if not aid:
            if not last_aid:
                return None
            aid = last_aid

        if not self.AID_RE.match(aid):
            return None

        mid_norm = " ".join(mid.split())
        if not mid_norm:
            return None

        tokens = mid_norm.split()
        if not tokens:
            return None

        if tokens[0] not in ("Config", "Actual"):
            return None

        row_type = tokens[0]
        tokens = tokens[1:]

        # buscar SN
        sn_idx = None
        for i, tok in enumerate(tokens):
            if re.fullmatch(r"[0-9A-Fa-f]{8,32}", tok):
                sn_idx = i
                break

        if sn_idx is None:
            sn = ""
            password = ""
            status = tokens[-1] if tokens else ""
        else:
            sn = tokens[sn_idx]
            password = tokens[sn_idx + 1] if sn_idx + 1 < len(tokens) else ""
            status = tokens[sn_idx + 2] if sn_idx + 2 < len(tokens) else ""

        image, active, version = self._parse_image_active_version(imgver)

        payload: Dict[str, Any] = {
            "Type": row_type,
            "SN": sn,
            "Password": password,
            "Status": status,
        }
        if image:
            payload["Image"] = image
        if active:
            payload["Active"] = active
        if version:
            payload["Version"] = version

        if vend_model:
            if re.fullmatch(r"[A-Z]{3,8}", vend_model):
                payload["Vendor"] = vend_model
            else:
                payload["Model"] = vend_model

        return {"AID": aid, "_row_type": row_type, "_row_payload": payload}

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

    def _parse_all_onts_filter(self, raw: str) -> List[Dict[str, Any]]:
        """
        Parser robusto para:
          show interface remote ont filter <n>

        Soporta:
        - 2 líneas por AID (Config/Actual) con AID vacío en la segunda línea.
        - Múltiples bloques con cabecera repetida.
        - Columnas segmentadas por pipes (|).
        """
        lines = [l.rstrip("\r") for l in raw.splitlines()]
        by_aid: Dict[str, Dict[str, Any]] = {}

        last_aid: Optional[str] = None
        header_mode = False

        for line in lines:
            s = line.rstrip()
            if not s.strip():
                continue

            if self.SEP_RE.match(s.strip()):
                continue

            if s.strip().startswith("slot ") and " has " in s and " ont" in s:
                header_mode = False
                last_aid = None
                continue

            if "AID" in s and "Vendor/Model" in s:
                header_mode = True
                last_aid = None
                continue

            if not header_mode:
                continue

            if "|" not in s:
                continue

            parsed = self._parse_remote_ont_filter_row(s, last_aid=last_aid)
            if not parsed:
                continue

            aid = parsed["AID"]
            last_aid = aid

            row_type = parsed.get("_row_type")
            row_payload = parsed.get("_row_payload", {})

            rec = by_aid.setdefault(aid, {"AID": aid})
            rec.setdefault("_rows", {})
            if row_type and row_payload:
                rec["_rows"][row_type] = row_payload

            chosen = rec["_rows"].get("Actual") or rec["_rows"].get("Config") or {}
            self._apply_chosen_row_to_record(rec, chosen)

        out: List[Dict[str, Any]] = []
        for _, rec in by_aid.items():
            rec.pop("_rows", None)
            out.append(rec)

        out.sort(key=lambda x: x.get("AID", ""))
        return out

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
