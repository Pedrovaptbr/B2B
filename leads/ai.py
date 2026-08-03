import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)


class IAError(Exception):
    """Erro amigável para exibir na UI (Ollama indisponível, resposta vazia etc)."""


def _chamar_ollama(prompt, system, max_tokens=400):
    url = f"{settings.OLLAMA_URL}/api/generate"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0.9},
    }
    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        log.error(f"Erro ao chamar Ollama: {e}")
        raise IAError('Não foi possível gerar o texto agora. Tente novamente em instantes.')

    texto = (resp.json().get('response') or '').strip()
    if not texto:
        raise IAError('A IA não retornou nenhum texto. Tente novamente.')
    return texto


_SYS_MENSAGEM_BASE = (
    "Você escreve mensagens curtas de prospecção B2B via WhatsApp em português do Brasil. "
    "Tom direto, natural, sem parecer spam, sem emojis em excesso, no máximo 3-4 frases. "
    "Use o placeholder literal [nome] onde o nome do lead deve entrar. "
    "Não inclua hashtags. Não invente números de telefone, preços ou links. "
    "Responda só com a mensagem, sem explicações."
)


def gerar_mensagem_base(contexto_negocio, objetivo):
    """
    Gera a mensagem padrão inteira (sem blocos {}), a partir do contexto do
    negócio do usuário e de um objetivo pontual da campanha.
    Retorna string única (a mensagem).
    """
    prompt = (
        f"Contexto do negócio que está enviando a mensagem: {contexto_negocio}\n"
        f"Objetivo desta mensagem: {objetivo}\n\n"
        "Escreva uma mensagem pronta para uso, usando [nome] onde o nome do lead entra."
    )
    return _chamar_ollama(prompt, _SYS_MENSAGEM_BASE, max_tokens=400)


_SYS_VARIACOES = (
    "Você gera variações curtas de uma frase em português do Brasil, para um sistema de "
    "spintax de WhatsApp. As variações devem ter o MESMO sentido e função da frase original, "
    "só mudando o texto/tom, para que as mensagens não pareçam repetidas. "
    "Preserve exatamente qualquer placeholder entre colchetes, como [nome], se aparecer no trecho. "
    "Responda só com as variações, uma por linha, sem numeração, sem aspas, sem explicações."
)


def gerar_variacoes_bloco(trecho_original, contexto_mensagem='', n=4):
    """
    Gera até `n` variações curtas de `trecho_original` (o conteúdo de um bloco
    spintax {op1|op2|...}), preservando placeholders como [nome].
    `contexto_mensagem` é opcional: texto ao redor do bloco, só para dar contexto
    ao modelo (não é reescrito).
    Retorna list[str] com até n itens.
    """
    prompt = (
        (f'Contexto (texto ao redor, não reescrever): "{contexto_mensagem}"\n\n' if contexto_mensagem else '')
        + f'Trecho original a variar: "{trecho_original}"\n\n'
        + f"Gere {n} variações desse trecho, uma por linha."
    )
    texto = _chamar_ollama(prompt, _SYS_VARIACOES, max_tokens=300)
    linhas = [l.strip(' "—-') for l in texto.splitlines() if l.strip()]
    return linhas[:n] if linhas else [trecho_original]
