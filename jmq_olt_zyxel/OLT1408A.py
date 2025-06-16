import telnetlib
import re
import json
from typing import List, Dict, Any


class APIOLT1408A:
    """
    Cliente API para interactuar con una OLT Zyxel 1408A vía Telnet.
    """
    def __init__(self, host: str, port: int, username: str, password: str,
                 prompt: str = 'OLT1408A#', timeout: int = 5):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.prompt = prompt.encode('ascii')
        self.timeout = timeout
        self.tn = telnetlib.Telnet()
        self._open_session()

    def _open_session(self):
        self.tn.open(self.host, self.port, timeout=self.timeout)
        self.tn.read_until(b'User name:', timeout=self.timeout)
        self.tn.write(self.username.encode('ascii') + b'\n')
        self.tn.read_until(b'Password:', timeout=self.timeout)
        self.tn.write(self.password.encode('ascii') + b'\n')
        self.tn.read_until(self.prompt, timeout=self.timeout)
        print("[DEBUG] Sesión iniciada correctamente.")

    def _send_command(self, command: str) -> str:
        self.tn.write(command.encode('ascii') + b'\n')
        output = self.tn.read_until(self.prompt, timeout=self.timeout).decode('ascii', errors='ignore')
        lines = output.splitlines()
        if lines and lines[0].strip() == command:
            lines.pop(0)
        if lines and lines[-1].strip().endswith(self.prompt.decode('ascii')):
            lines.pop()
        return "\n".join(lines)

    def get_all_onts(self) -> List[Dict[str, Any]]:
        raw = self._send_command("show remote ont")
        return self._parse_table(raw, key_prefix="ont-")

    def get_unregistered_onts(self) -> List[Dict[str, Any]]:
        raw = self._send_command("show remote ont unreg")
        return self._parse_table(raw, key_prefix=None)

    def get_ont_details(self, aid: str) -> Dict[str, Any]:
        raw = self._send_command(f"show remote ont {aid}")
        lines = raw.splitlines()
        details: Dict[str, Any] = {}
        for line in lines:
            if ':' not in line:
                continue
            cleaned = line.lstrip(' |').strip()
            if ':' not in cleaned:
                continue
            key, val = cleaned.split(':', 1)
            details[key.strip()] = val.strip()
        return details

    def get_ont_status_history(self, aid: str) -> List[Dict[str, str]]:
        raw = self._send_command(f"show remote ont {aid} status-history")
        lines = raw.splitlines()
        history: List[Dict[str, str]] = []
        seps = [i for i,l in enumerate(lines) if re.match(r'^\s*-+\+-+', l)]
        if len(seps) < 2:
            return history
        start = seps[1] + 1
        for line in lines[start:]:
            if re.match(r'^\s*-+\+-+', line):
                break
            cleaned = line.lstrip(' |').strip()
            if not cleaned:
                continue
            parts = cleaned.split('|')
            # la parte de la derecha tiene índice, status y tiempo
            tokens = parts[-1].strip().split()
            if len(tokens) < 3:
                continue
            status = tokens[1]
            time_str = ' '.join(tokens[2:])
            history.append({"status": status, "tt": time_str})
        return history

    def get_ont_config(self, aid: str) -> Dict[str, Any]:
        raw = self._send_command(f"show remote ont {aid} config")
        lines = raw.splitlines()
        result: Dict[str, Any] = {"ont": {}, "uni": {}}
        block = None
        for line in lines:
            if re.match(r'^\s*-+\+-+', line):
                continue
            stripped = line.strip()
            if stripped.startswith(aid):
                block = 'ont'
                continue
            if stripped.startswith('uniport-'):
                block = 'uni'
                continue
            if not block:
                continue
            content = line.lstrip(' |').strip()
            if not content:
                continue
            tokens = content.split()
            if block == 'ont':
                key = tokens[0].lower()
                if key in ['sn','password','full-bridge','template-description','alarm-profile','anti-mac-spoofing']:
                    result['ont'][key.replace('-', '_')] = tokens[1]
                elif key == 'bwgroup':
                    result['ont']['bwgroup'] = tokens[1]
                    # perfiles y allocid
                    for i,t in enumerate(tokens):
                        if t == 'usbwprofname':
                            result['ont']['usbwprofname'] = tokens[i+1]
                        if t == 'dsbwprofname':
                            result['ont']['dsbwprofname'] = tokens[i+1]
                        if t == 'allocid':
                            result['ont']['allocid'] = tokens[i+1]
            else:
                if tokens[0] == 'no' and tokens[1] == 'inactive':
                    result['uni']['active'] = True
                elif tokens[0] == 'no' and tokens[1] == 'pmenable':
                    result['uni']['pmenable'] = False
                elif tokens[0] == 'queue' and tokens[1] == 'tc':
                    entry = {'tc': int(tokens[2])}
                    for i,t in enumerate(tokens):
                        if t == 'priority': entry['priority'] = int(tokens[i+1])
                        if t == 'weight': entry['weight'] = int(tokens[i+1])
                        if t == 'usbwprofname': entry['usbwprofname'] = tokens[i+1]
                        if t == 'dsbwprofname': entry['dsbwprofname'] = tokens[i+1]
                        if t == 'dsoption': entry['dsoption'] = tokens[i+1]
                        if t == 'bwsharegroupid': entry['bwsharegroupid'] = tokens[i+1]
                    result['uni'].setdefault('queues', []).append(entry)
                elif tokens[0] == 'vlan':
                    result['uni']['vlan'] = tokens[1]
                elif tokens[0] == 'gemport':
                    result['uni']['gemport'] = tokens[1]
                elif tokens[0] == 'ingprof':
                    result['uni']['ingprof'] = tokens[1]
                elif tokens[0] == 'aesencrypt':
                    result['uni']['aesencrypt'] = tokens[1]
        return result

    def _parse_table(self, raw: str, key_prefix: str = "ont-") -> List[Dict[str, Any]]:
        lines = raw.splitlines()
        seps = [i for i,l in enumerate(lines) if re.match(r'^\s*-+\+-+', l)]
        if len(seps) < 2:
            return []
        header_idx = seps[0] + 1
        headers = [h.strip() for h in lines[header_idx].split('|')]
        data_start = seps[1] + 1
        data: List[Dict[str, Any]] = []
        for line in lines[data_start:]:
            if not line.strip() or line.strip().startswith('Total:'):
                break
            row = line.strip()
            if key_prefix and not row.startswith(key_prefix):
                continue
            cols = [c.strip() for c in row.split('|')]
            if len(cols) != len(headers):
                continue
            data.append(dict(zip(headers, cols)))
        return data

    def to_json(self, data: Any) -> str:
        return json.dumps(data, indent=2)

    def close(self) -> None:
        try:
            self.tn.write(b"exit\n")
        except Exception:
            pass
        self.tn.close()
