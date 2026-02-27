import requests
from django.conf import settings
import time
import uuid
import logging

# Configura o logger para exibir mensagens de debug
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

# --- Funções da Evolution API ---

def _get_evolution_api_config():
    """Função interna para pegar as credenciais da API do settings."""
    api_url = getattr(settings, 'EVOLUTION_API_URL', None)
    api_key = getattr(settings, 'EVOLUTION_API_KEY', None)
    if not api_url or not api_key:
        raise ValueError("EVOLUTION_API_URL ou EVOLUTION_API_KEY não configuradas.")
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
        return {"success": True, "data": response.json() if response.content else {}}
    except requests.exceptions.RequestException as e:
        log.error(f"Erro de conexão com a Evolution API: {e}")
        return {"success": False, "error": str(e)}

def create_evolution_instance(instance_name):
    """Cria uma nova instância na Evolution API."""
    try:
        _, global_api_key = _get_evolution_api_config()
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

    api_data = result.get("data", {})
    return api_data.get("instance", {}).get("state", "DISCONNECTED")

def send_whatsapp_message(instance_name, instance_token, number, text):
    """Envia uma mensagem de texto via WhatsApp usando o TOKEN DA INSTÂNCIA."""
    headers = {"apikey": instance_token, "Content-Type": "application/json"}
    payload = {"number": number, "textMessage": {"text": text}}
    return _evolution_request("post", f"/message/sendText/{instance_name}", headers, json=payload)

def verify_whatsapp_numbers(instance_name: str, numbers: list[str]):
    """
    Verifica números de WhatsApp, contornando um bug da API que retorna JIDs corrompidos.
    Assume que a ordem da resposta é a mesma da requisição.
    """
    log.debug("--- INICIANDO VERIFICAÇÃO DE NÚMEROS (ESTRATÉGIA DE ORDEM) ---")
    results = {number: {'exists': False, 'reason': 'Unchecked'} for number in numbers}
    if not numbers:
        return results

    try:
        api_url, global_api_key = _get_evolution_api_config()
    except ValueError as e:
        log.error(f"Erro ao obter configuração da API: {e}")
        for number in numbers: results[number]['reason'] = str(e)
        return results

    url = f"{api_url}/chat/whatsappNumbers/{instance_name}"
    payload = {"numbers": numbers}
    headers = {"Content-Type": "application/json", "apikey": global_api_key}

    log.debug(f"Enviando para URL: {url}")
    log.debug(f"Payload (corpo): {payload}")

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        log.debug(f"API Respondeu com Status Code: {response.status_code}")
        log.debug(f"API Respondeu com Corpo (raw): {response.text}")

        if response.status_code in [200, 201]:
            api_results = response.json()
            log.debug(f"API Resposta (JSON processado): {api_results}")

            for original_number, api_result in zip(numbers, api_results):
                if original_number in results:
                    results[original_number]['exists'] = api_result.get('exists', False)
                    results[original_number]['reason'] = 'OK'
        else:
            error_reason = f"API Error: {response.status_code} - {response.text}"
            log.error(error_reason)
            for number in numbers: results[number]['reason'] = error_reason

    except requests.exceptions.RequestException as e:
        error_reason = f"Connection Error: {e}"
        log.error(error_reason)
        for number in numbers: results[number]['reason'] = error_reason
    
    log.debug(f"Resultado final da verificação: {results}")
    log.debug("--- FIM DA VERIFICAÇÃO DE NÚMEROS ---")
    return results

# --- Funções da Google Places API ---
def get_google_text_search(query):
    api_key = getattr(settings, 'GOOGLE_API_KEY', None)
    if not api_key:
        log.error("GOOGLE_API_KEY não encontrada nas configurações.")
        return {'results': [], 'status': 'REQUEST_DENIED', 'error_message': 'Chave da API do Google não configurada.'}
    params = {'query': query, 'key': api_key, 'language': 'pt-BR'}
    try:
        response = requests.get("https://maps.googleapis.com/maps/api/place/textsearch/json", params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        log.error(f"Erro de conexão com a Google API: {e}")
        return {'results': [], 'status': 'API_ERROR', 'error_message': f'Erro de conexão com a Google API: {e}'}

def get_google_place_details(place_id):
    api_key = getattr(settings, 'GOOGLE_API_KEY', None)
    if not api_key: return {}
    params = {'place_id': place_id, 'key': api_key,
              'fields': 'name,international_phone_number,formatted_phone_number,website,rating,formatted_address,user_ratings_total,types',
              'language': 'pt-BR'}
    try:
        response = requests.get("https://maps.googleapis.com/maps/api/place/details/json", params=params, timeout=10)
        response.raise_for_status()
        return response.json().get('result', {})
    except requests.exceptions.RequestException as e:
        log.error(f"Erro ao buscar detalhes do lugar ({place_id}): {e}")
        return {}