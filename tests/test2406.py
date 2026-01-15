# -*- coding: utf-8 -*-
"""
tests/test2406.py

Test manual (smoke test) para la API de OLT2406.
Ejecuta:
  - show remote ont
  - show remote ont unreg
  - show remote ont {aid}
  - show remote ont {aid} status-history
  - show remote ont {aid} config
"""

from jmq_olt_zyxel.OLT2406 import APIOLT2406

HOST = "201.251.78.101"
PORT = 18103
USER = "admin"
PASS = "f2%C4+f1$d7("
PROMPT_BASE = "OLT2406#"

AID_TEST = "ont-3-1-1"

if __name__ == "__main__":
    client = APIOLT2406(
        host=HOST,
        port=PORT,
        username=USER,
        password=PASS,
        prompt_base=PROMPT_BASE,
        timeout=30,
        debug=False,
    )

    try:
        # 1) Todas las ONTs registradas
        all_onts = client.get_all_onts()
        print("--- Todas las ONTs registradas ---")
        print(client.to_json(all_onts))

        # 2) ONTs no registradas (UnReg)
        unreg = client.get_unregistered_onts()
        print("--- ONTs no registradas ---")
        print(client.to_json(unreg))

        # Intentamos elegir un AID válido para detalles/historial/config:
        # Preferimos de la lista "show remote ont" usando clave "AID" si existe.
        # aid = None
        # if all_onts:
        #     if isinstance(all_onts[0], dict):
        #         # Caso típico: headers incluyen "AID"
        #         aid = all_onts[0].get("AID") or all_onts[0].get("Aid") or all_onts[0].get("aid")
        #         # Si la tabla viene con una columna diferente, intenta primera key:
        #         if not aid:
        #            first_key = next(iter(all_onts[0].keys()), None)
        #            if first_key:
        #                aid = all_onts[0].get(first_key)
        aid = AID_TEST
        if aid:
            # 3) Detalles de la ONT
            details = client.get_ont_details(aid)
            print(f"--- get_ont_details - Detalles de la ONT {aid} ---")
            print(client.to_json(details))

            # 4) Historial de estado de la ONT
            history = client.get_ont_status_history(aid)
            print(f"--- get_ont_status_history - Historial de estado de la ONT {aid} ---")
            print(client.to_json(history))

            # 5) Configuración de la ONT
            config = client.get_ont_config(aid)
            print(f"--- get_ont_config -Configuración de la ONT {aid} ---")
            print(client.to_json(config))
        else:
            print("No hay ONTs registradas (o no se pudo inferir AID) para probar detalles/historial/config.")

    finally:
        client.close()