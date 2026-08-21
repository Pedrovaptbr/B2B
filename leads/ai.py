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


# O único placeholder que o disparo de fato substitui é "[nome]" (ver
# services.substituir_nome). Mesmo instruído a não inventar telefone/link/
# preço, o modelo às vezes contorna a regra inventando um placeholder pro
# dado que falta (ex: "[número]") — que ninguém troca, e vaza literal pra
# mensagem enviada ao lead. Removemos qualquer colchete que não seja [nome].
_PADRAO_PLACEHOLDER_INVALIDO = re.compile(r'\[(?!nome\])[^\[\]]*\]', re.IGNORECASE)


# O app nunca quer despedida em lugar nenhum da mensagem (nem no fim, nem
# como opção de variação de uma saudação de abertura). Instruir o modelo
# "nunca gere despedida aqui" não é suficiente — observado na prática que
# ele às vezes devolve "Tchau" como opção de abertura mesmo assim. Filtramos
# qualquer candidato que comece com palavra de despedida, como rede de
# segurança adicional à instrução do prompt.
_PALAVRA_DESPEDIDA_INICIO = re.compile(
    r'^\s*(tchau\w*|até\s+logo|até\s+mais|até\s+breve|falou|flw|adeus)', re.IGNORECASE
)


def _remover_despedidas(linhas):
    """Descarta candidatos de variação que são despedida, não saudação (ver nota acima)."""
    return [l for l in linhas if not _PALAVRA_DESPEDIDA_INICIO.match(l)]


def _remover_placeholder_invalido(texto):
    """Remove placeholders entre colchetes inventados pela IA, exceto [nome] (ver nota acima)."""
    if not texto:
        return texto
    texto = _PADRAO_PLACEHOLDER_INVALIDO.sub('', texto)
    texto = re.sub(r'[ \t]+', ' ', texto)
    texto = re.sub(r'\s+([,.!?])', r'\1', texto)
    texto = re.sub(r'([,.!?]){2,}', r'\1', texto)
    return texto.strip()


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
    return _remover_placeholder_invalido(_remover_assinatura(texto))


def _prompt_variacoes():
    from .models import ConfiguracaoIA
    return ConfiguracaoIA.atual().prompt_variacoes


# Saudação de abertura é um conjunto pequeno e fechado — não faz sentido (e
# não é confiável) pedir pra IA "criar" isso livremente, já rendeu palavra
# inventada ("Olhaquiça") e despedida disfarçada de saudação ("Tchauzinho").
# Horário (Bom dia/Boa tarde/Boa noite) fica de fora de propósito: o disparo
# é espalhado ao longo do dia, então uma saudação presa a horário pode
# chegar errada pro lead.
SAUDACOES_FIXAS = ['Olá', 'Oi', 'E aí', 'Fala', 'Opa']

_SYS_CLASSIFICADOR_SAUDACAO = (
    "Você classifica se um trecho de texto é uma SAUDAÇÃO DE ABERTURA de "
    "mensagem de WhatsApp — como 'Olá', 'Oi', 'Bom dia', 'E aí', 'Fala', "
    "'Salve', ou qualquer variação/gíria/erro de digitação equivalente, "
    "mesmo com pontuação junto (ex: 'Oi,'). NÃO é saudação de abertura: "
    "despedida ('Tchau'), nome de pessoa, frase de venda, ou qualquer outra "
    "coisa. Responda com EXATAMENTE uma palavra: 'sim' ou 'não'."
)


def eh_saudacao_abertura(trecho):
    """
    Pergunta pra IA (classificação simples, não geração livre) se `trecho`
    é uma saudação de abertura. Mais confiável que manter uma lista fixa de
    palavras reconhecidas tentando prever toda variação/pontuação possível.
    Em caso de falha da IA, retorna False (cai no caminho normal de geração).
    """
    try:
        resposta = _chamar_ollama(
            f'Trecho: "{trecho}"', _SYS_CLASSIFICADOR_SAUDACAO, max_tokens=5, temperature=0.0
        )
    except IAError:
        return False
    return resposta.strip().lower().lstrip(' "\'').startswith('sim')


def gerar_variacoes_bloco(trecho_original, contexto_mensagem='', n=4, contexto_depois=''):
    """
    Gera até `n` variações curtas de `trecho_original` (o conteúdo de um bloco
    spintax {op1|op2|...}), preservando placeholders como [nome].
    `contexto_mensagem` é o texto ANTES do trecho e `contexto_depois` é o texto
    DEPOIS — ambos opcionais, só para o modelo ver o que vem dos dois lados e
    gerar opções que combinem gramaticalmente com a frase inteira (sem isso,
    ele só via o "antes" e podia gerar uma opção com preposição/tempo verbal
    que não encaixa com o que vem depois do bloco). Nenhum dos dois é reescrito.
    Se `trecho_original` for classificado como saudação de abertura, retorna
    a lista fixa SAUDACOES_FIXAS em vez de gerar livremente (ver nota acima
    da função eh_saudacao_abertura).
    Retorna list[str] com até n itens.
    """
    if eh_saudacao_abertura(trecho_original):
        return list(SAUDACOES_FIXAS)

    prompt = (
        (f'Texto ANTES do trecho (contexto, não reescrever): "{contexto_mensagem}"\n' if contexto_mensagem else '')
        + (f'Texto DEPOIS do trecho (contexto, não reescrever): "{contexto_depois}"\n' if contexto_depois else '')
        + ('\n' if contexto_mensagem or contexto_depois else '')
        + f'Trecho original a variar: "{trecho_original}"\n\n'
        + f"Gere {n} variações desse trecho, uma por linha. Cada variação deve encaixar "
        + "gramaticalmente tanto com o texto ANTES quanto com o texto DEPOIS. "
        + "IMPORTANTE: cada variação deve ter aproximadamente o mesmo tamanho e escopo do "
        + "trecho original — se o trecho original é uma palavra ou frase curta, a variação "
        + "também é; NÃO vire o trecho numa frase completa nova nem adicione ponto final "
        + "próprio, porque ela vai ficar inserida NO MEIO da frase, entre o texto ANTES e o "
        + "texto DEPOIS."
    )
    texto = _chamar_ollama(prompt, _prompt_variacoes(), max_tokens=300, temperature=0.8)
    linhas = [
        _remover_placeholder_invalido(l).strip(' "—-')
        for l in texto.splitlines() if l.strip()
    ]
    linhas = _remover_despedidas([l for l in linhas if l])
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
    linhas = [
        _remover_placeholder_invalido(_remover_assinatura(l)).strip(' "—-')
        for l in texto.splitlines() if l.strip()
    ]
    linhas = _remover_despedidas([l for l in linhas if l])
    return linhas[:n] if linhas else [mensagem]
