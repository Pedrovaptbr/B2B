import requests

# Suas configurações
EVOLUTION_API_URL = "http://localhost:8081"
EVOLUTION_API_KEY = "b2bkey"


def check_evolution_connection(instance_name):
    """
    Verifica se a instância do WhatsApp está conectada (open).
    """
    url = f"{EVOLUTION_API_URL}/instance/connectionState/{instance_name}"
    headers = {
        "apikey": EVOLUTION_API_KEY
    }

    try:
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            # A API retorna o estado dentro de ['instance']['state']
            state = data.get("instance", {}).get("state")

            if state == "open":
                return True, "Conectado"
            return False, state
        else:
            return False, f"Erro API: {response.status_code}"

    except requests.exceptions.ConnectionError:
        return False, "API Offline (Servidor local não encontrado)"
    except Exception as e:
        return False, str(e)


# --- TESTE ---
instancia = "admin_1"
online, status = check_evolution_connection(instancia)

if online:
    print(f"✅ WhatsApp pronto. Status: {status}")
else:
    print(f"❌ Falha: {status}")