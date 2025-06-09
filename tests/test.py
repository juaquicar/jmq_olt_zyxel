from jmq_olt_zyxel.OLT1408A import APIOLT1408A

if __name__ == "__main__":
    # Parámetros de conexión
    HOST = "152.170.74.208"
    PORT = 2300
    USER = "admin"
    PASS = "1234"
    PROMPT = "OLT1408A#"

    # 1) Instanciamos el cliente
    client = APIOLT1408A(host=HOST, port=PORT, username=USER, password=PASS, prompt=PROMPT)

    try:
        # 2) Obtenemos todas las ONTs
        all_onts = client.get_all_onts()
        print("Resumen de ONTs (en JSON):")
        print(client.to_json(all_onts))

        # 3) Para cada ONT, podemos ver más detalles. Por ejemplo, la primera:
        if all_onts:
            first_aid = all_onts[0]["AID"]
            details = client.get_ont_details(first_aid)
            print(f"\nDetalles completos de la ONT {first_aid}:")
            print(client.to_json(details))

    finally:
        # 4) Cerramos la conexión
        client.close()
