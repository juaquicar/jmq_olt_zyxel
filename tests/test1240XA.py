# -*- coding: utf-8 -*-
"""
tests/test1240XA.py

Test manual (smoke test) para la API de OLT/MSC1240XA.
Ejecuta (vía métodos de la API):
  - show interface remote ont filter 1
  - show interface remote ont unreg
  - show interface remote ont {aid} status
  - show interface remote ont {aid} status-history
  - show interface remote ont {aid} config
"""

from jmq_olt_zyxel.OLT1240XA import APIOLT1240XA

HOST = "X.X.X.X"
PORT = 23
USER = "admin"
PASS = "****"
PROMPT_BASE = "MSC1240XA#"

# AID de prueba (en 1240XA NO lleva prefijo "ont-": ejemplo real "2-16-40")
AID_TEST = "2-16-40"

if __name__ == "__main__":
    client = APIOLT1240XA(
        host=HOST,
        port=PORT,
        username=USER,
        password=PASS,
        prompt=PROMPT_BASE,
        timeout=30,
        debug=False,
    )

    try:
        # 1) Todas las ONTs registradas (filter 1)
        all_onts = client.get_all_onts("1")
        print("--- Todas las ONTs registradas (filter 1) ---")
        print(client.to_json(all_onts))

        # 2) ONTs no registradas (UnReg)
        unreg = client.get_unregistered_onts()
        print("--- ONTs no registradas (UnReg) ---")
        print(client.to_json(unreg))

        # Intentamos elegir un AID válido para detalles/historial/config:
        # Preferimos AID_TEST; si está vacío, intentamos inferir del listado.
        aid = AID_TEST

        if not aid and all_onts:
            if isinstance(all_onts[0], dict):
                aid = all_onts[0].get("AID") or all_onts[0].get("Aid") or all_onts[0].get("aid")
                if not aid:
                    first_key = next(iter(all_onts[0].keys()), None)
                    if first_key:
                        aid = all_onts[0].get(first_key)

        if aid:
            # 3) Detalles de la ONT (status)
            details = client.get_ont_details(aid)
            print(f"--- get_ont_details - Detalles de la ONT {aid} (status) ---")
            print(client.to_json(details))

            # 4) Historial de estado de la ONT
            history = client.get_ont_status_history(aid)
            print(f"--- get_ont_status_history - Historial de estado de la ONT {aid} ---")
            print(client.to_json(history))

            # 5) Configuración de la ONT
            config = client.get_ont_config(aid)
            print(f"--- get_ont_config - Configuración de la ONT {aid} ---")
            print(client.to_json(config))
        else:
            print("No hay ONTs registradas (o no se pudo inferir AID) para probar detalles/historial/config.")

    finally:
        client.close()
