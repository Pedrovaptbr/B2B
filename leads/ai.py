import logging
import re

import requests
from django.conf import settings

log = logging.getLogger(__name__)


class IAError(Exception):
    """Erro amigável para exibir na UI (Ollama indisponível, resposta vazia etc)."""


def _chamar_ollama(prompt, system, max_tokens=400, temperature=0.9):
    url = f"{settings.OLLAMA_URL}/api/generate"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": temperature},
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


# Modelos pequenos (ex: qwen2.5:1.5b) tendem a "fechar carta" mesmo quando
# instruídos a não fazer isso — encerram com despedida/assinatura formal
# ("Atenciosamente", "[Seu Nome]"), o que soa nada natural numa mensagem de
# WhatsApp e chama atenção como spam. Como confiar 100% no modelo seguir a
# instrução não é realista, removemos esse tipo de linha como rede de segurança.
_PADRAO_ASSINATURA = re.compile(
    r'(?im)^\s*(atenciosamente|att\.?|cordialmente|abra[cç]os?|um\s+abra[cç]o|'
    r'grato[a]?|obrigad[oa]|[àa]\s+disposi[cç][ãa]o)\s*[,.!]?\s*$'
    r'|^\s*\[?\s*seu\s+nome\s*\]?\s*[,.!]?\s*$'
)


def _remover_assinatura(texto):
    """Remove despedida/assinatura formal do final do texto gerado (ver nota acima)."""
    linhas = texto.splitlines()
    while linhas and (not linhas[-1].strip() or _PADRAO_ASSINATURA.match(linhas[-1])):
        linhas.pop()
    return '\n'.join(linhas).strip()


def _prompt_mensagem_base():
    from .models import ConfiguracaoIA
    return ConfiguracaoIA.atual().prompt_mensagem_base


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
    texto = _chamar_ollama(prompt, _prompt_mensagem_base(), max_tokens=300, temperature=0.65)
    return _remover_assinatura(texto)


def _prompt_variacoes():
    from .models import ConfiguracaoIA
    return ConfiguracaoIA.atual().prompt_variacoes


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
    texto = _chamar_ollama(prompt, _prompt_variacoes(), max_tokens=300, temperature=0.8)
    linhas = [l.strip(' "—-') for l in texto.splitlines() if l.strip()]
    return linhas[:n] if linhas else [trecho_original]


def gerar_variacoes_mensagem(mensagem, contexto_negocio='', n=4):
    """
    Gera até `n` variações completas de `mensagem` (a mensagem padrão inteira,
    não um trecho isolado), preservando placeholders como [nome].

    Usada como proteção automática anti-bloqueio: quando o usuário não
    escreveu spintax manual ({op1|op2}) na campanha, o disparo chama esta
    função uma vez (não por lead) para garantir que os leads não recebam
    todos o texto idêntico. Não consome a cota mensal de IA do usuário —
    é segurança da plataforma, não uma geração de conteúdo escolhida por ele.
    """
    prompt = (
        (f'Contexto do negócio: "{contexto_negocio}"\n\n' if contexto_negocio else '')
        + f'Mensagem original a variar: "{mensagem}"\n\n'
        + f"Gere {n} variações completas dessa mensagem, uma por linha."
    )
    texto = _chamar_ollama(prompt, _prompt_variacoes(), max_tokens=500, temperature=0.8)
    linhas = [_remover_assinatura(l).strip(' "—-') for l in texto.splitlines() if l.strip()]
    linhas = [l for l in linhas if l]
    return linhas[:n] if linhas else [mensagem]
