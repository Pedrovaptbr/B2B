import requests  # noqa
from django.conf import settings
import time
import uuid
import base64
import mimetypes
import os
import re
import random
import logging

log = logging.getLogger(__name__)
# Ativa DEBUG só neste módulo — não polui o logger raiz do Django
if settings.DEBUG:
    log.setLevel(logging.DEBUG)

_SPINTAX_RE = re.compile(r'\{([^{}]+)\}')


def randomizar_mensagem(texto):
    """
    Escolhe aleatoriamente uma das variações escritas pelo usuário no formato
    {opção 1|opção 2|opção 3}, para que mensagens repetidas ao longo de uma
    campanha não saiam idênticas. Texto sem esse padrão é retornado como está.
    """
    if not texto:
        return texto
    return _SPINTAX_RE.sub(lambda m: random.choice(m.group(1).split('|')).strip(), texto)


def escolher_hashtag_final(texto_opcoes):
    """
    Escolhe aleatoriamente uma das opções de hashtag cadastradas pelo usuário
    (uma por linha) para adicionar ao final da mensagem. Retorna string vazia
    se não houver nenhuma opção cadastrada.
    """
    if not texto_opcoes:
        return ''
    opcoes = [linha.strip() for linha in texto_opcoes.splitlines() if linha.strip()]
    if not opcoes:
        return ''
    return random.choice(opcoes)


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

        # 400: captura o corpo para expor o motivo real (ex: número não existe no WhatsApp)
        if response.status_code == 400:
            try:
                body = response.json()
                # Evolution API v1.6+ retorna {"message": "...", "error": "..."}
                motivo = body.get("message") or body.get("error") or response.text
            except Exception:
                motivo = response.text
            log.warning(f"Evolution API 400 em {endpoint}: {motivo}")
            return {"success": False, "error": motivo, "status_code": 400}

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

def get_instance_qrcode(instance_name):
    """Busca o QR code de uma instância existente na Evolution API."""
    try:
        _, global_api_key = _get_evolution_api_config()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    headers = {"apikey": global_api_key}
    result = _evolution_request("get", f"/instance/connect/{instance_name}", headers)

    if not result.get("success"):
        return {"success": False, "error": result.get("error", "API_ERROR")}

    data = result.get("data", {})
    qr_code_full = data.get("base64")
    qr_code_clean = qr_code_full.split("base64,")[-1] if qr_code_full and "base64," in qr_code_full else qr_code_full
    return {"success": bool(qr_code_clean), "qr_code": qr_code_clean}


def send_whatsapp_message(instance_name, instance_token, number, text):
    """Envia uma mensagem de texto via WhatsApp usando o TOKEN DA INSTÂNCIA."""
    headers = {"apikey": instance_token, "Content-Type": "application/json"}
    payload = {"number": number, "textMessage": {"text": text}}
    return _evolution_request("post", f"/message/sendText/{instance_name}", headers, json=payload)

def send_whatsapp_media(instance_name, instance_token, number, file_path,
                        file_name=None, caption="", mediatype=None):
    """
    Envia um arquivo (ex: catálogo PDF, imagem JPG/PNG) via WhatsApp usando o
    TOKEN DA INSTÂNCIA. O arquivo é lido do disco e enviado em base64 para a
    Evolution API (v1.5.x). Se mediatype não for informado, é detectado pelo
    tipo do arquivo: imagens chegam como foto, vídeos como vídeo e o restante
    (PDF, DOC, XLS...) como documento.
    """
    if not os.path.exists(file_path):
        log.error(f"Anexo não encontrado: {file_path}")
        return {"success": False, "error": "Arquivo de anexo não encontrado."}

    file_name = file_name or os.path.basename(file_path)
    mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"

    # Detecta o tipo de mídia: imagem → foto inline; vídeo → vídeo; resto → documento
    if mediatype is None:
        if mime_type.startswith("image/"):
            mediatype = "image"
        elif mime_type.startswith("video/"):
            mediatype = "video"
        else:
            mediatype = "document"

    try:
        with open(file_path, "rb") as f:
            media_b64 = base64.b64encode(f.read()).decode("utf-8")
    except OSError as e:
        log.error(f"Erro ao ler anexo {file_path}: {e}")
        return {"success": False, "error": "Não foi possível ler o arquivo de anexo."}

    headers = {"apikey": instance_token, "Content-Type": "application/json"}
    payload = {
        "number": number,
        "mediaMessage": {
            "mediatype": mediatype,
            "fileName": file_name,
            "mimetype": mime_type,
            "caption": caption or "",
            "media": media_b64,
        },
    }
    return _evolution_request("post", f"/message/sendMedia/{instance_name}", headers, json=payload)

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

def fetch_whatsapp_chats(instance_name, limit=30):
    """
    Busca a lista de conversas recentes da instância via Evolution API.
    Retorna lista de dicts: [{jid, name, last_message, timestamp, unread}]
    """
    try:
        _, global_api_key = _get_evolution_api_config()
    except ValueError as e:
        log.error(f"Erro ao obter config da API: {e}")
        return []

    headers = {"apikey": global_api_key, "Content-Type": "application/json"}
    payload = {"where": {}, "limit": limit}

    result = _evolution_request(
        "post",
        f"/chat/findChats/{instance_name}",
        headers,
        json=payload
    )

    if not result.get("success"):
        log.error(f"Erro ao buscar chats: {result.get('error')}")
        return []

    raw = result.get("data", [])

    # Normaliza: pode ser lista direta ou dict com records
    if isinstance(raw, list):
        records = raw
    elif isinstance(raw, dict):
        records = raw.get("records", raw.get("chats", []))
    else:
        records = []

    chats = []
    for chat in records:
        # JID pode estar em "id" (string) ou "id.remote" (dict)
        jid = ""
        id_field = chat.get("id", "")
        if isinstance(id_field, dict):
            jid = id_field.get("remote", id_field.get("_serialized", ""))
        else:
            jid = str(id_field)

        # Ignora grupos e broadcasts
        if "@g.us" in jid or "@broadcast" in jid or not jid:
            continue

        name = chat.get("name") or chat.get("pushName") or jid.split("@")[0]
        timestamp = chat.get("timestamp") or chat.get("lastMessageTime", 0)

        last_msg_raw = chat.get("lastMessage", {})
        if isinstance(last_msg_raw, dict):
            msg_body = last_msg_raw.get("message", {})
            last_text = (
                msg_body.get("conversation")
                or msg_body.get("extendedTextMessage", {}).get("text")
                or "📎 Mídia"
            )
        else:
            last_text = ""

        unread = chat.get("unreadCount", 0)

        chats.append({
            "jid": jid,
            "name": name,
            "last_message": last_text,
            "timestamp": int(timestamp) if timestamp else 0,
            "unread": int(unread) if unread else 0,
        })

    # Ordena por mais recente
    chats.sort(key=lambda c: c["timestamp"], reverse=True)
    return chats


def fetch_whatsapp_messages(instance_name, whatsapp_number, limit=50):
    """
    Busca o histórico de mensagens de uma conversa WhatsApp via Evolution API v1.6.x.
    Retorna lista de dicts: [{from_me, text, timestamp}, ...]
    """
    try:
        _, global_api_key = _get_evolution_api_config()
    except ValueError as e:
        log.error(f"Erro ao obter config da API: {e}")
        return []

    numero_limpo = ''.join(filter(str.isdigit, whatsapp_number))
    jid = f"{numero_limpo}@s.whatsapp.net"

    headers = {"apikey": global_api_key, "Content-Type": "application/json"}

    # Evolution API v1.6.x usa remoteJid direto no where (não aninhado em key)
    payload = {
        "where": {
            "remoteJid": jid
        },
        "limit": limit
    }

    log.debug(f"fetch_whatsapp_messages → instância={instance_name} jid={jid} payload={payload}")

    result = _evolution_request(
        "post",
        f"/chat/findMessages/{instance_name}",
        headers,
        json=payload
    )

    log.debug(f"fetch_whatsapp_messages ← success={result.get('success')} data_type={type(result.get('data')).__name__}")

    if not result.get("success"):
        log.error(f"Erro ao buscar mensagens: {result.get('error')}")
        return []

    raw = result.get("data", {})
    log.debug(f"fetch_whatsapp_messages raw keys={list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__}")

    # Normaliza todos os formatos de resposta possíveis da API
    if isinstance(raw, list):
        records = raw
    elif isinstance(raw, dict):
        if "messages" in raw:
            inner = raw["messages"]
            records = inner.get("records", []) if isinstance(inner, dict) else (inner if isinstance(inner, list) else [])
        elif "records" in raw:
            records = raw["records"]
        else:
            # Último recurso: pega o primeiro campo que for lista
            records = next((v for v in raw.values() if isinstance(v, list)), [])
    else:
        records = []

    log.debug(f"fetch_whatsapp_messages → {len(records)} registros brutos encontrados")

    mensagens = []
    for msg in records:
        key = msg.get("key", {})
        from_me = bool(key.get("fromMe", False))

        message_body = msg.get("message", {}) or {}
        text = (
            message_body.get("conversation")
            or (message_body.get("extendedTextMessage") or {}).get("text")
            or (message_body.get("imageMessage") or {}).get("caption")
            or "[Mídia]"
        )

        timestamp = msg.get("messageTimestamp", 0)

        # Filtro: só mensagens deste JID (inclui @lid como fallback)
        remote_jid = key.get("remoteJid", "")
        if numero_limpo not in remote_jid and jid not in remote_jid:
            log.debug(f"Mensagem ignorada: remoteJid={remote_jid} não bate com {numero_limpo}")
            continue

        mensagens.append({
            "from_me": from_me,
            "text": text,
            "timestamp": int(timestamp),
        })

    # Ordena cronologicamente (mais antigas primeiro)
    mensagens.sort(key=lambda m: m["timestamp"])
    return mensagens


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
