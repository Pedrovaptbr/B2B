import requests
import json

# Suas credenciais
base_url = "http://localhost:8081"
instance_name = "admin_1"
api_key = "b2bkey"

url = f"{base_url}/message/sendText/{instance_name}"

headers = {
    "Content-Type": "application/json",
    "apikey": api_key
}

# O NOVO FORMATO QUE A API PEDE:
payload = {
    "number": "5548991824812",
    "text": "oi"
}


payload_v2 = {
    "number": "5548991824812",
    "options": {
        "delay": 1200,
        "presence": "composing"
    },
    "textMessage": {
        "text": "a msg acima foi mandada pelo evolution api, se vc estiver vendo isso é pq vc foi hackeado pelo maior e melhor hacker do pais todo."
    }
}

try:
    response = requests.post(url, headers=headers, json=payload_v2)

    print(f"Status: {response.status_code}")
    print(response.json())
except Exception as e:
    print(f"Erro: {e}")