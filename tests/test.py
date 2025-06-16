import json
from jmq_olt_zyxel.OLT1408A import APIOLT1408A

HOST = "152.170.74.208"
PORT = 2300
USER = "admin"
PASS = "1234"
PROMPT = "OLT1408A#"

if __name__ == "__main__":
    client = APIOLT1408A(host=HOST, port=PORT, username=USER, password=PASS, prompt=PROMPT)
    try:
        # 1) Todas las ONTs registradas
        all_onts = client.get_all_onts()
        print("--- Todas las ONTs registradas ---")
        print(client.to_json(all_onts))

        # 2) ONTs no registradas
        unreg = client.get_unregistered_onts()
        print("--- ONTs no registradas ---")
        print(client.to_json(unreg))

        if all_onts:
            aid = all_onts[0]["AID"]
            # 3) Detalles de la primera ONT
            details = client.get_ont_details(aid)
            print(f"--- Detalles de la ONT {aid} ---")
            print(client.to_json(details))

            # 4) Historial de estado de la ONT
            history = client.get_ont_status_history(aid)
            print(f"--- Historial de estado de la ONT {aid} ---")
            print(client.to_json(history))

            # 5) Configuración de la ONT
            config = client.get_ont_config(aid)
            print(f"--- Configuración de la ONT {aid} ---")
            print(client.to_json(config))
        else:
            print("No hay ONTs registradas para probar detalles, historial ni configuración.")

    finally:
        client.close()
