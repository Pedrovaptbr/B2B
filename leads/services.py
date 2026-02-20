import requests
from django.conf import settings
import time
import uuid

# --- Funções da Evolution API ---

def _get_evolution_api_config():
    """Função interna para pegar as credenciais da API do .env."""
    api_url = settings.EVOLUTION_API_URL
    api_key = settings.EVOLUTION_API_KEY
    if not api_url or not api_key:
        raise ValueError("Credenciais da Evolution API não configuradas no .env")
    return api_url, api_key

def _evolution_request(method, endpoint, headers, **kwargs):
    """Função interna para centralizar os requests para a Evolution API."""
    try:
        api_url, _ = _get_evolution_api_config()
        response = requests.request(method, f"{api_url}{endpoint}", headers=headers, timeout=15, **kwargs)
        if response.status_code == 404:
            return {"success": False, "error": "NOT_FOUND"}
        if response.status_code in [401, 403]:
            return {"success": False, "error": f"AUTH_ERROR: {response.status_code} - {response.text}"}
        response.raise_for_status()
        if response.content:
            return {"success": True, "data": response.json()}
        return {"success": True, "data": {}}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}
    except requests.exceptions.JSONDecodeError:
        return {"success": True, "data": {}}

def create_evolution_instance(instance_name):
    """Cria uma nova instância na Evolution API."""
    try:
        api_url, global_api_key = _get_evolution_api_config()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    headers = {"apikey": global_api_key, "Content-Type": "application/json"}
    
    _evolution_request("delete", f"/instance/logout/{instance_name}", headers)
    _evolution_request("delete", f"/instance/delete/{instance_name}", headers)
    time.sleep(1)

    new_token = str(uuid.uuid4())
    payload = {"instanceName": instance_name, "token": new_token, "qrcode": True, "webhook": ""}
    
    result = _evolution_request("post", "/instance/create", headers, json=payload)
    if not result.get("success"): return result
    
    data = result.get("data", {})
    qr_code_full = data.get('qrcode', {}).get('base64')
    qr_code_clean = qr_code_full.split('base64,')[-1] if qr_code_full and 'base64,' in qr_code_full else qr_code_full
    
    return {"success": True, "token": new_token, "qr_code": qr_code_clean}

def get_instance_qrcode(instance_name):
    """Busca o QR Code de uma instância existente usando a CHAVE GLOBAL."""
    try:
        _, global_api_key = _get_evolution_api_config()
    except ValueError as e:
        return {"success": False, "error": str(e)}
    
    headers = {"apikey": global_api_key}
    result = _evolution_request("get", f"/instance/connect/{instance_name}", headers)
    if not result.get("success"): return result
    
    data = result.get("data", {})
    qr_code_full = data.get('qrcode', {}).get('base64')
    qr_code_clean = qr_code_full.split('base64,')[-1] if qr_code_full and 'base64,' in qr_code_full else qr_code_full
    return {"success": True, "qr_code": qr_code_clean}

def get_instance_connection_state(instance_name):
    """Verifica o status da conexão de uma instância usando a CHAVE GLOBAL."""
    try:
        _, global_api_key = _get_evolution_api_config()
    except ValueError as e:
        return f"CONFIG_ERROR: {e}"

    headers = {"apikey": global_api_key}
    result = _evolution_request("get", f"/instance/connectionState/{instance_name}", headers)
    
    if not result.get("success"):
        return result.get("error", "API_ERROR")
    
    # CORREÇÃO: Acessando o caminho correto do JSON
    api_data = result.get("data", {})
    state = api_data.get("instance", {}).get("state", "DISCONNECTED")
    return state

def send_whatsapp_message(instance_name, instance_token, number, text):
    """Envia uma mensagem de texto via WhatsApp usando o TOKEN DA INSTÂNCIA."""
    headers = {"apikey": instance_token, "Content-Type": "application/json"}
    payload = {"number": number, "textMessage": {"text": text}}
    return _evolution_request("post", f"/message/sendText/{instance_name}", headers, json=payload)

def check_whatsapp_contact(instance_name, instance_token, number):
    """Verifica se um número de telefone existe no WhatsApp usando o TOKEN DA INSTÂNCIA."""
    headers = {"apikey": instance_token}
    payload = {"numbers": [number]}
    result = _evolution_request("post", f"/contact/on-whatsapp/{instance_name}", headers, json=payload)
    if not result.get("success"):
        return {"exists": False, "error": result.get("error")}
    contact_info = result.get("data", [])[0] if result.get("data") else {}
    return {"exists": contact_info.get("exists", False), "jid": contact_info.get("jid")}

# --- Funções da Google Places API ---
def get_google_text_search(query):
    api_key = settings.GOOGLE_API_KEY
    if not api_key: return {'status': 'REQUEST_DENIED'}
    params = {'query': query, 'key': api_key, 'language': 'pt-BR'}
    try:
        response = requests.get("https://maps.googleapis.com/maps/api/place/textsearch/json", params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return {'status': 'API_ERROR'}

def get_google_place_details(place_id):
    api_key = settings.GOOGLE_API_KEY
    if not api_key: return None
    params = {'place_id': place_id, 'key': api_key, 'fields': 'name,international_phone_number,formatted_phone_number,website,rating,formatted_address,user_ratings_total,types', 'language': 'pt-BR'}
    try:
        response = requests.get("https://maps.googleapis.com/maps/api/place/details/json", params=params)
        response.raise_for_status()
        return response.json().get('result')
    except requests.exceptions.RequestException:
        return None
