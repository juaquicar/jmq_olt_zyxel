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
PROMPT = "OLT2406# "


if __name__ == "__main__":
    client = APIOLT2406(
        host=HOST,
        port=PORT,
        username=USER,
        password=PASS,
        prompt_base=PROMPT,
        debug=True,  # pon False si no quieres logs
    )
    try:
        # 1) Todas las ONTs registradas
        all_onts = client.get_all_onts()
        print("--- Todas las ONTs registradas (OLT2406) ---")
        print(client.to_json(all_onts))

        # 2) ONTs no registradas
        unreg = client.get_unregistered_onts()
        print("--- ONTs no registradas (OLT2406) ---")
        print(client.to_json(unreg))

        # 3) Elegimos AID para pruebas avanzadas:
        #    - Preferimos el primer registro de all_onts con clave "AID"
        #    - Si no existe, intentamos con claves típicas alternativas
        aid = None
        if all_onts:
            for k in ("AID", "Aid", "aid", "ONT", "Ont", "ont"):
                if k in all_onts[0] and all_onts[0][k]:
                    aid = all_onts[0][k]
                    break

        if aid:
            # 3) Detalles de la primera ONT
            details = client.get_ont_details(aid)
            print(f"--- Detalles de la ONT {aid} (OLT2406) ---")
            print(client.to_json(details))

            # 4) Historial de estado de la ONT
            history = client.get_ont_status_history(aid)
            print(f"--- Historial de estado de la ONT {aid} (OLT2406) ---")
            print(client.to_json(history))

            # 5) Configuración de la ONT
            config = client.get_ont_config(aid)
            print(f"--- Configuración de la ONT {aid} (OLT2406) ---")
            print(client.to_json(config))
        else:
            print("No hay ONTs registradas (o no se encontró columna AID) para probar detalles/historial/config.")

    finally:
        client.close()
