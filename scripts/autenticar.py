import requests
import json

# Credenciais
EVOLUTION_API_URL = "http://localhost:8081"
EVOLUTION_API_KEY = "b2bkey"
INSTANCE_NAME = "admin_1"


def verificar_whatsapp(numero):
    """
    Verifica se um número existe no WhatsApp usando a Evolution API.
    O número deve estar no formato internacional (ex: 5511999999999)
    """
    url = f"{EVOLUTION_API_URL}/chat/whatsappNumbers/{INSTANCE_NAME}"

    # Prepara o corpo da requisição (pode ser uma lista de números)
    payload = {
        "numbers": [numero]
    }

    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_API_KEY
    }

    try:
        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 201 or response.status_code == 200:
            dados = response.json()
            # A Evolution retorna uma lista. Pegamos o primeiro resultado.
            resultado = dados[0]

            if resultado.get("exists"):
                print(f"✅ O número {numero} POSSUI WhatsApp.")
                return True
            else:
                print(f"❌ O número {numero} NÃO possui WhatsApp.")
                return False
        else:
            print(f"⚠️ Erro na API: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"💥 Erro de conexão: {e}")
        return None


# --- TESTE PRÁTICO ---
numero_teste = "5548999003582"
tem_whats = verificar_whatsapp(numero_teste)