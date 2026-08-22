from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.db.models import F
from django.urls import reverse
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import re
import csv
import time
import random
import threading
import logging
import requests
from .models import Campanha, Lead, HistoricoBusca, TemplateMensagem, ConfiguracaoDisparo
from accounts.models import PerfilUsuario, WhatsappInstance
from . import services
from . import ai

logger = logging.getLogger(__name__)


# ─── Campanhas ────────────────────────────────────────────────────────────────

@login_required
def campaign_list_view(request):
    if request.method == 'POST':
        nome = request.POST.get('nome_campanha', '').strip()
        if nome:
            try:
                Campanha.objects.create(user=request.user, nome=nome)
                messages.success(request, f'Campanha "{nome}" criada com sucesso!')
            except IntegrityError:
                messages.error(request, f'Você já possui uma campanha com o nome "{nome}".')
        else:
            messages.error(request, 'O nome da campanha não pode estar vazio.')
        return redirect('leads:campaign_list')

    campanhas = Campanha.objects.filter(user=request.user)
    return render(request, 'leads/campaign_list.html', {'campanhas': campanhas})


@login_required
def campaign_edit_view(request, pk):
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)
    if request.method == 'POST':
        nome = request.POST.get('nome_campanha', '').strip()
        mensagem = request.POST.get('mensagem_padrao', '').strip()
        spintax_ok, spintax_erro = services.validar_spintax(mensagem)
        if nome and not spintax_ok:
            messages.error(request, spintax_erro)
        elif nome:
            try:
                campanha.nome = nome
                campanha.mensagem_padrao = mensagem or None

                hashtag_opcoes = [h.strip() for h in request.POST.getlist('hashtag_opcao') if h.strip()]
                campanha.hashtags_finais = '\n'.join(hashtag_opcoes) or None

                # Remover anexo existente, se solicitado
                if request.POST.get('remover_anexo') == '1' and campanha.anexo:
                    campanha.anexo.delete(save=False)
                    campanha.anexo = None

                # Novo anexo enviado
                novo_anexo = request.FILES.get('anexo')
                if novo_anexo:
                    if campanha.anexo:
                        campanha.anexo.delete(save=False)
                    campanha.anexo = novo_anexo

                campanha.save()
                messages.success(request, 'Campanha atualizada com sucesso!')
                return redirect('leads:campanha_detalhes', pk=campanha.pk)
            except IntegrityError:
                messages.error(request, f'Você já possui uma campanha com o nome "{nome}".')
        else:
            messages.error(request, 'O nome da campanha não pode estar vazio.')

    # Templates: todos do usuário, marcando quais estão associados a esta campanha
    todos_templates = TemplateMensagem.objects.filter(user=request.user).prefetch_related('campanhas')
    associados_ids  = set(campanha.templates.values_list('pk', flat=True))

    return render(request, 'leads/campaign_edit.html', {
        'campanha':        campanha,
        'todos_templates': todos_templates,
        'associados_ids':  associados_ids,
        'ia_restantes':    request.user.perfil.ia_geracoes_restantes(),
    })


@login_required
def campaign_delete_view(request, pk):
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)
    if request.method == 'POST':
        nome = campanha.nome
        campanha.delete()
        messages.success(request, f'Campanha "{nome}" apagada com sucesso.')
        return redirect('leads:campaign_list')
    return render(request, 'leads/campaign_delete.html', {'campanha': campanha})


# ─── Detalhes da Campanha ─────────────────────────────────────────────────────

@login_required
def campanha_detalhes_view(request, pk):
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)
    leads = campanha.leads.all().order_by('-id')
    instancia = WhatsappInstance.objects.filter(user=request.user).first()
    return render(request, 'leads/campanha_detalhes.html', {
        'campanha': campanha,
        'leads': leads,
        'instancia': instancia,
    })


# ─── Busca de Leads ───────────────────────────────────────────────────────────

def _get_estados():
    try:
        response = requests.get(
            'https://servicodados.ibge.gov.br/api/v1/localidades/estados?orderBy=nome',
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f'Erro ao buscar estados do IBGE: {e}')
        return []


@login_required
def campanha_buscar_leads_view(request, pk):
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)
    estados = _get_estados()
    historico_buscas = HistoricoBusca.objects.filter(user=request.user)[:5]

    context = {
        'campanha': campanha,
        'estados': estados,
        'historico_buscas': historico_buscas,
        'search_results': [],
    }

    tipo_empresa = request.GET.get('tipo_empresa', '').strip()
    # Aceita uma ou várias cidades (dentro do mesmo estado), sem duplicatas.
    cidades = list(dict.fromkeys(
        c.strip() for c in request.GET.getlist('cidade') if c.strip()
    ))
    estado = request.GET.get('estado', '').strip()
    context['cidades_selecionadas'] = cidades

    if tipo_empresa and cidades and estado:
        raw_results = []
        seen_place_ids = set()
        erro_busca = None

        for cidade in cidades:
            query = f'{tipo_empresa} em {cidade}, {estado}, Brasil'
            google_data = services.get_google_text_search(query)
            status = google_data.get('status')

            if status == 'OK':
                HistoricoBusca.objects.update_or_create(
                    user=request.user,
                    tipo_empresa=tipo_empresa,
                    cidade=cidade,
                    estado=estado,
                )
                for place in google_data.get('results', []):
                    place_id = place.get('place_id')
                    if not place_id or place_id in seen_place_ids:
                        continue
                    seen_place_ids.add(place_id)
                    place['cidade_busca'] = cidade
                    raw_results.append(place)
            elif status == 'ZERO_RESULTS':
                continue
            else:
                erro_busca = google_data.get('error_message', 'Erro desconhecido na busca.')

        ids_na_campanha = set(campanha.leads.values_list('place_id', flat=True))
        ids_extraidos = set(request.user.leads_adquiridos.values_list('place_id', flat=True))
        leads_extraidos = {
            l.place_id: l for l in Lead.objects.filter(place_id__in=ids_extraidos)
        }

        for place in raw_results:
            place_id = place.get('place_id')
            lead_existente = leads_extraidos.get(place_id)
            place['ja_esta_na_campanha'] = place_id in ids_na_campanha
            place['ja_foi_extraido'] = place_id in ids_extraidos
            place['tem_whatsapp'] = bool(lead_existente and lead_existente.whatsapp)

        context['search_results'] = raw_results

        if erro_busca and not raw_results:
            messages.error(request, f'Erro na busca: {erro_busca}')

    return render(request, 'leads/campanha_buscar.html', context)


@login_required
def get_cidades_por_estado(request, uf_id):
    try:
        response = requests.get(
            f'https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf_id}/municipios?orderBy=nome',
            timeout=10,
        )
        response.raise_for_status()
        cidades = [{'id': c['id'], 'nome': c['nome']} for c in response.json()]
        return JsonResponse(cidades, safe=False)
    except requests.exceptions.RequestException as e:
        logger.error(f'Erro ao buscar cidades do IBGE: {e}')
        return JsonResponse([], safe=False)


# ─── Extração de Lead ─────────────────────────────────────────────────────────

def _adicionar_lead_a_campanha(user, perfil, campanha, place_id):
    """Extrai (ou importa) um único lead para a campanha. Extração é gratuita
    — o custo em créditos passou a ser no disparo (por envio), não aqui.

    Não emite mensagens nem redireciona — apenas executa a operação e devolve
    ``(status, lead)`` para o chamador tratar.

    status ∈ {'ja_na_campanha', 'importado', 'extraido', 'erro_google'}
    """
    lead, criado = Lead.objects.get_or_create(
        place_id=place_id,
        defaults={'nome': f'Lead Provisório - {place_id}'}
    )

    if lead in campanha.leads.all():
        return 'ja_na_campanha', lead

    usuario_ja_e_proprietario = lead.proprietarios.filter(pk=user.pk).exists()

    if usuario_ja_e_proprietario:
        campanha.leads.add(lead)
        return 'importado', lead

    if criado or 'Lead Provisório' in lead.nome:
        details = services.get_google_place_details(place_id)
        if not details:
            if criado:
                lead.delete()
            return 'erro_google', lead

        telefone_formatado = details.get('formatted_phone_number')
        numero_internacional = details.get('international_phone_number')
        whatsapp_limpo = ""

        if numero_internacional:
            whatsapp_limpo = re.sub(r'\D', '', numero_internacional)
        elif telefone_formatado:
            numero_apenas_digitos = re.sub(r'\D', '', telefone_formatado)
            if numero_apenas_digitos.startswith('55'):
                whatsapp_limpo = numero_apenas_digitos
            else:
                whatsapp_limpo = '55' + numero_apenas_digitos

        lead.nome = details.get('name', 'Nome Indisponível')
        lead.endereco = details.get('formatted_address')
        lead.telefone = telefone_formatado
        lead.whatsapp = whatsapp_limpo
        lead.site = details.get('website')
        lead.rating = details.get('rating', 0)
        lead.status = 'Qualificado'
        lead.save()

    perfil.total_extraido += 1
    perfil.save()
    lead.proprietarios.add(user)
    campanha.leads.add(lead)
    return 'extraido', lead


@login_required
@transaction.atomic
def extract_lead_view(request, campanha_id, place_id):
    campanha = get_object_or_404(Campanha, id=campanha_id, user=request.user)
    perfil = PerfilUsuario.objects.select_for_update().get(user=request.user)
    redirect_url = f"{reverse('leads:campanha_buscar', kwargs={'pk': campanha.id})}?{request.GET.urlencode()}"

    status, lead = _adicionar_lead_a_campanha(request.user, perfil, campanha, place_id)

    if status == 'ja_na_campanha':
        messages.warning(request, f"Lead '{lead.nome}' já está nesta campanha.")
    elif status == 'erro_google':
        messages.error(request, "Não foi possível obter detalhes do Google.")
    elif status == 'extraido':
        messages.success(request, f"Novo lead '{lead.nome}' extraído!")
    elif status == 'importado':
        messages.info(request, f"Lead '{lead.nome}' importado do seu cofre para a campanha.")

    return redirect(redirect_url)


@login_required
@transaction.atomic
def bulk_extract_leads_view(request, campanha_id):
    campanha = get_object_or_404(Campanha, id=campanha_id, user=request.user)
    perfil = PerfilUsuario.objects.select_for_update().get(user=request.user)

    next_qs = request.POST.get('next_qs', '')
    redirect_url = reverse('leads:campanha_buscar', kwargs={'pk': campanha.id})
    if next_qs:
        redirect_url = f"{redirect_url}?{next_qs}"

    if request.method != 'POST':
        return redirect(redirect_url)

    # Preserva a ordem e remove place_ids duplicados vindos do formulário.
    place_ids = list(dict.fromkeys(request.POST.getlist('place_ids')))
    if not place_ids:
        messages.warning(request, "Nenhuma lead selecionada.")
        return redirect(redirect_url)

    contagem = {'extraido': 0, 'importado': 0, 'ja_na_campanha': 0, 'erro_google': 0}
    for place_id in place_ids:
        status, _ = _adicionar_lead_a_campanha(request.user, perfil, campanha, place_id)
        contagem[status] += 1

    partes = []
    if contagem['extraido']:
        partes.append(f"{contagem['extraido']} extraída(s)")
    if contagem['importado']:
        partes.append(f"{contagem['importado']} importada(s)")
    if partes:
        messages.success(request, f"{' e '.join(partes)} para a campanha.")

    if contagem['erro_google']:
        messages.warning(request, f"{contagem['erro_google']} lead(s) falharam ao obter detalhes do Google.")
    if not partes and not contagem['erro_google']:
        messages.info(request, "As leads selecionadas já estavam na campanha.")

    return redirect(redirect_url)


# ─── Validação de Contatos ────────────────────────────────────────────────────

@login_required
def validar_contatos_view(request, pk):
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)

    try:
        instancia = request.user.whatsapp_instance
        estado_api = services.get_instance_connection_state(instancia.instance_name)
        if estado_api.upper() not in ['CONNECTED', 'OPEN']:
            messages.error(request, 'Sua instância WhatsApp não está conectada. Conecte-a primeiro.')
            return redirect('leads:campanha_detalhes', pk=pk)
        if instancia.status != 'CONNECTED':
            instancia.status = 'CONNECTED'
            instancia.save()
    except WhatsappInstance.DoesNotExist:
        messages.error(request, 'Você não possui uma instância WhatsApp configurada.')
        return redirect('leads:campanha_detalhes', pk=pk)

    leads_para_validar = campanha.leads.filter(
        status='Qualificado', whatsapp__isnull=False
    ).exclude(whatsapp='')

    if not leads_para_validar.exists():
        messages.info(request, "Nenhum lead com status 'Qualificado' para validar.")
        return redirect('leads:campanha_detalhes', pk=pk)

    numeros = [lead.whatsapp for lead in leads_para_validar]
    resultados = services.verify_whatsapp_numbers(instancia.instance_name, numeros)

    verificados, invalidos = 0, 0
    with transaction.atomic():
        for lead in leads_para_validar:
            resultado = resultados.get(lead.whatsapp, {})
            if resultado.get('exists'):
                lead.status = 'Verificado'
                verificados += 1
            else:
                lead.status = 'Telefone Inexistente'
                invalidos += 1
            lead.save()

    messages.success(request, f'Validação concluída! {verificados} verificados, {invalidos} inválidos.')
    return redirect('leads:campanha_detalhes', pk=pk)


# ─── Disparo de Campanha ──────────────────────────────────────────────────────

# Intervalo entre o envio para um lead e o próximo: uma pausa "humana" de
# base somada a um tempo proporcional ao tamanho da mensagem (como se
# estivesse sendo digitada), ambos randomizados. O objetivo não é enviar
# rápido — é parecer uma pessoa enviando manualmente, para reduzir o risco
# de bloqueio do número pelo WhatsApp. Quanto tempo a campanha toda demora
# não importa.
DELAY_BASE_MIN_SEGUNDOS = 90      # 1,5 min
DELAY_BASE_MAX_SEGUNDOS = 280     # ~4,7 min
SEGUNDOS_POR_CARACTERE_MIN = 0.12
SEGUNDOS_POR_CARACTERE_MAX = 0.25
DELAY_MAX_SEGUNDOS = 600          # teto de segurança (10 min) mesmo p/ mensagens longas

# Com menos que isso, a "variação" de hashtag não varia nada de verdade —
# com só 1 opção cadastrada, toda mensagem sairia com a mesma hashtag
# sempre, reproduzindo o padrão repetitivo que a exigência existe pra evitar.
HASHTAGS_MINIMAS = 3


def _calcular_delay_natural(mensagem):
    """
    Soma uma pausa de base (aleatória) a um tempo proporcional ao tamanho
    da mensagem (também aleatório, simulando digitação), limitado a um
    teto para o intervalo não deixar de parecer natural em mensagens muito
    longas.
    """
    base = random.uniform(DELAY_BASE_MIN_SEGUNDOS, DELAY_BASE_MAX_SEGUNDOS)
    tempo_digitacao = len(mensagem or '') * random.uniform(
        SEGUNDOS_POR_CARACTERE_MIN, SEGUNDOS_POR_CARACTERE_MAX
    )
    return min(base + tempo_digitacao, DELAY_MAX_SEGUNDOS)


def _disparar_em_background(campanha_id, instancia_id, lead_ids, variacoes_mensagem=None):
    """
    Executa o envio das mensagens em uma thread separada, com delay
    randomizado entre cada lead e respeitando o limite diário de envios
    da instância. Roda fora do ciclo de request/response.
    """
    from django.db import connections

    try:
        campanha = Campanha.objects.get(pk=campanha_id)
        instancia = WhatsappInstance.objects.get(pk=instancia_id)
        perfil = PerfilUsuario.objects.get(user=campanha.user)

        leads_selecionados = list(campanha.leads.filter(
            id__in=lead_ids, whatsapp__isnull=False
        ).exclude(whatsapp=''))

        anexo_path = campanha.anexo.path if campanha.anexo else None
        anexo_nome = campanha.anexo_nome if campanha.anexo else None

        for i, lead in enumerate(leads_selecionados):
            instancia.refresh_from_db(fields=['cancelar_disparo'])
            if instancia.cancelar_disparo:
                logger.info(
                    f'Disparo da campanha {campanha_id} cancelado pelo usuário — '
                    f'{len(leads_selecionados) - i} lead(s) restante(s) não enviados.'
                )
                break

            if instancia.envios_restantes_hoje() <= 0:
                logger.warning(
                    f'Limite diário de envios atingido para {instancia.instance_name}. '
                    f'Disparo interrompido — {len(leads_selecionados) - i} lead(s) restante(s).'
                )
                break

            perfil.refresh_from_db(fields=['creditos_disponiveis'])
            if perfil.creditos_disponiveis <= 0:
                logger.warning(
                    f'Créditos esgotados para {campanha.user.username}. '
                    f'Disparo interrompido — {len(leads_selecionados) - i} lead(s) restante(s).'
                )
                break

            resultado = None
            mensagem = ''

            if campanha.mensagem_padrao:
                mensagem_base = random.choice(variacoes_mensagem) if variacoes_mensagem else campanha.mensagem_padrao
                mensagem = services.substituir_nome(services.randomizar_mensagem(mensagem_base), lead.nome)
                hashtag = services.escolher_hashtag_final(campanha.hashtags_finais)
                if hashtag:
                    mensagem = f'{mensagem}\n\n{hashtag}'
                resultado = services.send_whatsapp_message(
                    instancia.instance_name,
                    instancia.instance_token,
                    lead.whatsapp,
                    mensagem,
                )

            if anexo_path:
                if resultado is not None and not resultado.get('success'):
                    pass
                else:
                    if resultado is not None:
                        time.sleep(1)
                    resultado_anexo = services.send_whatsapp_media(
                        instancia.instance_name,
                        instancia.instance_token,
                        lead.whatsapp,
                        anexo_path,
                        file_name=anexo_nome,
                    )
                    resultado = resultado_anexo

            if resultado and resultado.get('success'):
                lead.status = 'Contatado'
                lead.save()
            else:
                erro = (resultado or {}).get('error', '')
                logger.error(f'Erro ao enviar para {lead.whatsapp}: {erro}')
                if resultado and resultado.get('status_code') == 400:
                    lead.status = 'Telefone Inexistente'
                    lead.save()

            instancia.registrar_envio()
            # Update atômico direto no banco (F()) em vez de perfil.save():
            # essa thread roda em paralelo ao resto do app, e um F() evita
            # sobrescrever uma compra de crédito que tenha acontecido nesse
            # meio-tempo (webhook do Stripe, por exemplo).
            PerfilUsuario.objects.filter(pk=perfil.pk).update(
                creditos_disponiveis=F('creditos_disponiveis') - 1
            )

            # Delay natural antes do próximo lead (não após o último)
            if i < len(leads_selecionados) - 1:
                time.sleep(_calcular_delay_natural(mensagem))
    except Exception:
        logger.exception(f'Erro inesperado no disparo em background da campanha {campanha_id}')
    finally:
        WhatsappInstance.objects.filter(pk=instancia_id).update(
            enviando_campanha=False, disparo_iniciado_em=None, cancelar_disparo=False
        )
        connections.close_all()


@login_required
def disparar_campanha_view(request, campanha_id):
    campanha = get_object_or_404(Campanha, pk=campanha_id, user=request.user)

    if request.method != 'POST':
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    config_disparo = ConfiguracaoDisparo.atual()
    if config_disparo.bloqueado:
        messages.error(request, config_disparo.mensagem_bloqueio)
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    if not campanha.mensagem_padrao and not campanha.anexo:
        messages.error(request, 'Configure uma mensagem padrão ou um anexo antes de disparar a campanha.')
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    # Rede de segurança: mensagem com spintax malformada (chave aninhada ou
    # desbalanceada) não é reconhecida por randomizar_mensagem() e vazaria
    # como "{"/"}"/"|" literais na mensagem enviada ao lead. campaign_edit_view
    # já bloqueia isso ao salvar, mas confere de novo aqui por segurança.
    spintax_ok, spintax_erro = services.validar_spintax(campanha.mensagem_padrao)
    if not spintax_ok:
        messages.error(request, spintax_erro)
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    # Hashtag também é obrigatória quando há mensagem de texto (só não se
    # aplica pra campanha só-de-anexo, já que hashtag é anexada ao texto e
    # nunca é usada se não houver mensagem_padrao) — mesma lógica da
    # variação de mensagem: não depender do usuário lembrar de configurar.
    # Exige um mínimo de opções (não só "não vazio"): com 1 ou 2 hashtags a
    # repetição ainda é alta demais pra funcionar como variação de verdade.
    if campanha.mensagem_padrao and len(campanha.hashtags_finais_lista) < HASHTAGS_MINIMAS:
        messages.error(
            request,
            f'Configure pelo menos {HASHTAGS_MINIMAS} opções de hashtag antes de disparar a '
            'campanha — com poucas opções a mensagem repete demais, o que é exatamente o '
            'padrão que a variação existe pra evitar.'
        )
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    try:
        instancia = request.user.whatsapp_instance
        estado_api = services.get_instance_connection_state(instancia.instance_name)
        if estado_api.upper() not in ['CONNECTED', 'OPEN']:
            messages.error(request, 'Sua instância WhatsApp não está conectada.')
            return redirect('leads:campanha_detalhes', pk=campanha_id)
    except WhatsappInstance.DoesNotExist:
        messages.error(request, 'Você não possui uma instância WhatsApp configurada.')
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    # Autorrecuperação: se o disparo ficou "travado" por muito mais tempo do
    # que o pior caso plausível (ex: processo derrubado por deploy/crash no
    # meio de uma campanha, deixando enviando_campanha=True para sempre),
    # destrava sozinho em vez de exigir edição manual no /admin.
    if instancia.enviando_campanha and instancia.disparo_iniciado_em:
        limite_tempo = timedelta(seconds=instancia.limite_diario_envios * DELAY_MAX_SEGUNDOS * 1.5)
        if timezone.now() - instancia.disparo_iniciado_em > limite_tempo:
            logger.warning(
                f'Disparo da instância {instancia.instance_name} travado desde '
                f'{instancia.disparo_iniciado_em} — destravando automaticamente.'
            )
            WhatsappInstance.objects.filter(pk=instancia.pk).update(
                enviando_campanha=False, disparo_iniciado_em=None
            )
            instancia.enviando_campanha = False

    if instancia.envios_restantes_hoje() <= 0:
        messages.error(request, f'Limite diário de {instancia.limite_diario_envios} envios já atingido. Tente novamente amanhã.')
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    lead_ids = request.POST.getlist('lead_ids')
    if not lead_ids:
        messages.error(request, 'Nenhum lead selecionado.')
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    qtd_leads = campanha.leads.filter(
        id__in=lead_ids, whatsapp__isnull=False
    ).exclude(whatsapp='').count()

    if not qtd_leads:
        messages.error(request, 'Nenhum dos leads selecionados possui WhatsApp válido.')
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    # Cobrança é por envio, não por extração — 1 crédito por lead que
    # efetivamente recebe mensagem. Só bloqueia aqui se já estiver zerado;
    # se acabar no meio do disparo, o loop em background para sozinho
    # (mesmo padrão do limite diário de envios).
    if request.user.perfil.creditos_disponiveis <= 0:
        messages.error(
            request,
            'Você não tem créditos disponíveis. Adicione créditos para poder disparar mensagens.'
        )
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    # Proteção automática anti-bloqueio: se a mensagem não tem spintax manual
    # ({op1|op2}), todo lead receberia o texto idêntico — gera variações via
    # IA uma vez aqui (não por lead) para que o disparo nunca saia com a
    # mesma mensagem para todos. Não consome a cota mensal de IA do usuário.
    variacoes_mensagem = []
    if campanha.mensagem_padrao and not services.mensagem_tem_variacao(campanha.mensagem_padrao):
        try:
            contexto_negocio = getattr(request.user.perfil, 'contexto_negocio', '') or ''
            geradas = ai.gerar_variacoes_mensagem(
                campanha.mensagem_padrao, contexto_negocio=contexto_negocio, n=4
            )
            variacoes_mensagem = list(dict.fromkeys([campanha.mensagem_padrao] + geradas))
        except ai.IAError:
            messages.error(
                request,
                'Não foi possível gerar variações automáticas da mensagem (proteção anti-bloqueio). '
                'Tente novamente em instantes.'
            )
            return redirect('leads:campanha_detalhes', pk=campanha_id)

    # Trava atômica: só inicia o disparo se formos nós a mudar
    # enviando_campanha de False para True nesta mesma instrução SQL. Evita
    # que um duplo clique ou duas abas simultâneas iniciem duas threads de
    # disparo para a mesma instância.
    travado = WhatsappInstance.objects.filter(
        pk=instancia.pk, enviando_campanha=False
    ).update(enviando_campanha=True, disparo_iniciado_em=timezone.now())

    if not travado:
        messages.error(request, 'Já existe um disparo em andamento para sua instância. Aguarde terminar antes de iniciar outro.')
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    thread = threading.Thread(
        target=_disparar_em_background,
        args=(campanha.pk, instancia.pk, lead_ids, variacoes_mensagem),
        daemon=True,
    )
    thread.start()

    messages.success(
        request,
        f'Disparo iniciado para {qtd_leads} lead(s)! As mensagens serão enviadas aos poucos '
        f'(1 a 5 minutos entre cada uma) para reduzir o risco de bloqueio do número. '
        f'Atualize esta página para acompanhar o status de cada lead.'
    )
    return redirect('leads:campanha_detalhes', pk=campanha_id)


@login_required
def cancelar_disparo_view(request, campanha_id):
    get_object_or_404(Campanha, pk=campanha_id, user=request.user)

    if request.method != 'POST':
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    try:
        instancia = request.user.whatsapp_instance
    except WhatsappInstance.DoesNotExist:
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    # Só sinaliza cancelamento se houver disparo de fato em andamento — a
    # thread em background lê essa flag antes de cada lead e para sozinha.
    sinalizado = WhatsappInstance.objects.filter(
        pk=instancia.pk, enviando_campanha=True
    ).update(cancelar_disparo=True)

    if sinalizado:
        messages.success(
            request,
            'Cancelamento solicitado — o disparo vai parar em instantes (após o envio em andamento).'
        )
    else:
        messages.info(request, 'Não há nenhum disparo em andamento para cancelar.')

    return redirect('leads:campanha_detalhes', pk=campanha_id)


# ─── Bulk Delete Leads ────────────────────────────────────────────────────────

@login_required
def bulk_delete_leads_view(request, pk):
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)

    if request.method != 'POST':
        return redirect('leads:campanha_detalhes', pk=pk)

    lead_ids = request.POST.getlist('lead_ids')
    if lead_ids:
        campanha.leads.remove(*campanha.leads.filter(id__in=lead_ids))
        messages.success(request, f'{len(lead_ids)} lead(s) removido(s) da campanha.')
    else:
        messages.warning(request, 'Nenhum lead selecionado.')

    return redirect('leads:campanha_detalhes', pk=pk)


# ─── Exportar CSV ─────────────────────────────────────────────────────────────

@login_required
def export_csv_view(request, pk):
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{campanha.nome}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Nome', 'Telefone', 'WhatsApp', 'Site', 'Endereço', 'Status', 'Avaliação'])

    for lead in campanha.leads.all():
        writer.writerow([
            lead.nome,
            lead.telefone or '',
            lead.whatsapp or '',
            lead.site or '',
            lead.endereco or '',
            lead.get_status_display(),
            lead.rating or '',
        ])

    return response


# ─── Conversa WhatsApp por Lead ───────────────────────────────────────────────

@login_required
def conversa_lead_view(request, lead_id):
    """Exibe o histórico de conversa WhatsApp com um lead."""
    lead = get_object_or_404(
        Lead,
        id=lead_id,
        proprietarios=request.user
    )

    if not lead.whatsapp:
        messages.error(request, f'O lead "{lead.nome}" não possui número de WhatsApp cadastrado.')
        return redirect('leads:campaign_list')

    try:
        instancia = request.user.whatsapp_instance
    except Exception:
        messages.error(request, 'Você não possui uma instância WhatsApp configurada.')
        return redirect('leads:campaign_list')

    mensagens = services.fetch_whatsapp_messages(instancia.instance_name, lead.whatsapp)

    # Formata os timestamps para exibição
    from datetime import datetime
    for msg in mensagens:
        try:
            msg['datetime'] = datetime.fromtimestamp(msg['timestamp']).strftime('%d/%m %H:%M')
        except Exception:
            msg['datetime'] = ''

    context = {
        'lead': lead,
        'mensagens': mensagens,
        'instancia': instancia,
    }
    return render(request, 'leads/conversa_lead.html', context)


@login_required
def api_send_message_view(request, lead_id):
    """Recebe JSON via AJAX, envia mensagem WhatsApp e retorna {success, error}."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método não permitido.'}, status=405)

    lead = get_object_or_404(Lead, id=lead_id, proprietarios=request.user)

    if not lead.whatsapp:
        return JsonResponse({'success': False, 'error': 'Lead sem número de WhatsApp.'}, status=400)

    try:
        instancia = request.user.whatsapp_instance
    except Exception:
        return JsonResponse({'success': False, 'error': 'Instância WhatsApp não encontrada.'}, status=400)

    import json as _json
    try:
        body = _json.loads(request.body)
        texto = body.get('texto', '').strip()
    except (ValueError, KeyError):
        return JsonResponse({'success': False, 'error': 'Payload inválido.'}, status=400)

    if not texto:
        return JsonResponse({'success': False, 'error': 'Mensagem vazia.'}, status=400)

    resultado = services.send_whatsapp_message(
        instancia.instance_name,
        instancia.instance_token,
        lead.whatsapp,
        texto,
    )

    if resultado.get('success'):
        return JsonResponse({'success': True})
    else:
        return JsonResponse({'success': False, 'error': resultado.get('error', 'Erro ao enviar.')}, status=500)


# ─── Templates de Mensagem ────────────────────────────────────────────────────

@login_required
def template_criar_view(request, campanha_id=None):
    """Cria um template e opcionalmente já associa a uma campanha."""
    if request.method != 'POST':
        return redirect('leads:campaign_list')

    nome  = request.POST.get('nome', '').strip()
    texto = request.POST.get('texto', '').strip()

    if not nome or not texto:
        messages.error(request, 'Nome e texto do template são obrigatórios.')
        if campanha_id:
            return redirect('leads:campaign_edit', pk=campanha_id)
        return redirect('leads:campaign_list')

    try:
        template, criado = TemplateMensagem.objects.get_or_create(
            user=request.user,
            nome=nome,
            defaults={'texto': texto},
        )
        if not criado:
            template.texto = texto
            template.save()
            messages.info(request, f'Template "{nome}" atualizado.')
        else:
            messages.success(request, f'Template "{nome}" criado com sucesso!')

        if campanha_id:
            campanha = get_object_or_404(Campanha, pk=campanha_id, user=request.user)
            template.campanhas.add(campanha)

    except Exception as e:
        messages.error(request, f'Erro ao salvar template: {e}')

    if campanha_id:
        return redirect('leads:campaign_edit', pk=campanha_id)
    return redirect('leads:campaign_list')


@login_required
def template_deletar_view(request, template_id, campanha_id=None):
    """Deleta um template do usuário."""
    if request.method != 'POST':
        return redirect('leads:campaign_list')

    template = get_object_or_404(TemplateMensagem, pk=template_id, user=request.user)
    nome = template.nome
    template.delete()
    messages.success(request, f'Template "{nome}" removido.')

    if campanha_id:
        return redirect('leads:campaign_edit', pk=campanha_id)
    return redirect('leads:campaign_list')


@login_required
def template_toggle_campanha_view(request, template_id, campanha_id):
    """Associa ou desassocia um template de uma campanha (toggle)."""
    if request.method != 'POST':
        return redirect('leads:campaign_edit', pk=campanha_id)

    template = get_object_or_404(TemplateMensagem, pk=template_id, user=request.user)
    campanha = get_object_or_404(Campanha, pk=campanha_id, user=request.user)

    if template.campanhas.filter(pk=campanha_id).exists():
        template.campanhas.remove(campanha)
        messages.info(request, f'Template "{template.nome}" removido da campanha.')
    else:
        template.campanhas.add(campanha)
        messages.success(request, f'Template "{template.nome}" associado à campanha.')

    return redirect('leads:campaign_edit', pk=campanha_id)


@login_required
def template_salvar_msg_padrao_view(request, campanha_id):
    """Salva a mensagem padrão da campanha como um template e associa."""
    if request.method != 'POST':
        return redirect('leads:campaign_edit', pk=campanha_id)

    campanha = get_object_or_404(Campanha, pk=campanha_id, user=request.user)

    if not campanha.mensagem_padrao:
        messages.error(request, 'Esta campanha não tem mensagem padrão configurada.')
        return redirect('leads:campaign_edit', pk=campanha_id)

    nome = request.POST.get('nome', '').strip() or f'Template — {campanha.nome}'

    try:
        template, criado = TemplateMensagem.objects.get_or_create(
            user=request.user,
            nome=nome,
            defaults={'texto': campanha.mensagem_padrao},
        )
        if not criado:
            template.texto = campanha.mensagem_padrao
            template.save()
        template.campanhas.add(campanha)
        messages.success(request, f'Mensagem padrão salva como template "{nome}".')
    except Exception as e:
        messages.error(request, f'Erro: {e}')

    return redirect('leads:campaign_edit', pk=campanha_id)


@login_required
def api_templates_view(request):
    """
    AJAX — retorna templates do usuário.
    ?campanha_id=X  →  templates associados à campanha X aparecem primeiro (marcados).
    ?lead_id=Y      →  filtra pelos templates das campanhas do lead Y.
    Sem parâmetros  →  todos os templates do usuário.
    """
    campanha_id = request.GET.get('campanha_id')
    lead_id     = request.GET.get('lead_id')

    todos = TemplateMensagem.objects.filter(user=request.user).prefetch_related('campanhas')

    # Se vier lead_id, pega as campanhas desse lead que pertencem ao usuário
    if lead_id:
        try:
            lead = Lead.objects.get(pk=lead_id, proprietarios=request.user)
            campanhas_ids = lead.campanhas.filter(user=request.user).values_list('pk', flat=True)
            # Templates dessas campanhas + globais (sem campanha)
            todos = todos.filter(
                campanhas__pk__in=campanhas_ids
            ).distinct() | todos.filter(campanhas__isnull=True)
        except Lead.DoesNotExist:
            pass

    resultado = []
    associados_ids = set()

    if campanha_id:
        try:
            campanha = Campanha.objects.get(pk=campanha_id, user=request.user)
            associados_ids = set(campanha.templates.values_list('pk', flat=True))
        except Campanha.DoesNotExist:
            pass

    for t in todos:
        resultado.append({
            'id':          t.pk,
            'nome':        t.nome,
            'texto':       t.texto,
            'associado':   t.pk in associados_ids,
        })

    # Associados primeiro, depois por nome
    resultado.sort(key=lambda x: (not x['associado'], x['nome'].lower()))
    return JsonResponse({'templates': resultado})


# ─── IA — Geração/Variação de Mensagens ───────────────────────────────────────

@login_required
def api_ia_gerar_mensagem_view(request):
    """AJAX — gera a mensagem padrão inteira a partir do contexto_negocio do usuário + um objetivo."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'method'}, status=405)

    perfil = request.user.perfil
    if not perfil.contexto_negocio:
        return JsonResponse({
            'success': False, 'error': 'sem_contexto',
            'message': 'Cadastre o contexto do seu negócio antes de usar a IA.',
            'redirect': reverse('accounts:perfil'),
        })
    if not perfil.pode_usar_ia():
        return JsonResponse({
            'success': False, 'error': 'quota',
            'message': f'Você já usou suas {settings.LIMITE_IA_GERACOES_MES} gerações de IA este mês.',
        })

    import json as _json
    try:
        body = _json.loads(request.body)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'payload'}, status=400)

    objetivo = (body.get('objetivo') or '').strip()
    if not objetivo:
        return JsonResponse({
            'success': False, 'error': 'objetivo_vazio',
            'message': 'Descreva o objetivo da mensagem.',
        })

    try:
        mensagem = ai.gerar_mensagem_base(perfil.contexto_negocio, objetivo)
    except ai.IAError as e:
        return JsonResponse({'success': False, 'error': 'ia_falhou', 'message': str(e)})

    perfil.consumir_ia()
    return JsonResponse({'success': True, 'mensagem': mensagem, 'restantes': perfil.ia_geracoes_restantes()})


@login_required
def api_ia_gerar_variacoes_view(request):
    """AJAX — gera N opções para compor/complementar um bloco spintax {opção1|opção2|...}."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'method'}, status=405)

    perfil = request.user.perfil
    if not perfil.pode_usar_ia():
        return JsonResponse({
            'success': False, 'error': 'quota',
            'message': f'Você já usou suas {settings.LIMITE_IA_GERACOES_MES} gerações de IA este mês.',
        })

    import json as _json
    try:
        body = _json.loads(request.body)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'payload'}, status=400)

    trecho = (body.get('trecho') or '').strip()
    if not trecho:
        return JsonResponse({
            'success': False, 'error': 'trecho_vazio',
            'message': 'Selecione um trecho de texto para variar.',
        })
    contexto = (body.get('contexto') or '').strip()
    contexto_depois = (body.get('contexto_depois') or '').strip()
    try:
        n = int(body.get('n', 4))
    except (TypeError, ValueError):
        n = 4
    n = max(1, min(n, 8))

    try:
        opcoes = ai.gerar_variacoes_bloco(trecho, contexto, n, contexto_depois=contexto_depois)
    except ai.IAError as e:
        return JsonResponse({'success': False, 'error': 'ia_falhou', 'message': str(e)})

    perfil.consumir_ia()
    return JsonResponse({'success': True, 'opcoes': opcoes, 'restantes': perfil.ia_geracoes_restantes()})


# ─── Meu Banco de Leads ───────────────────────────────────────────────────────

@login_required
def meu_banco_view(request):
    if request.method == 'POST':
        action  = request.POST.get('action', 'remove_lead')
        lead_id = request.POST.get('lead_id')

        # ── Remover lead do banco ─────────────────────────────────────────────
        if action == 'remove_lead' and lead_id:
            lead = get_object_or_404(Lead, id=lead_id, proprietarios=request.user)
            lead.proprietarios.remove(request.user)
            messages.success(request, f'Lead "{lead.nome}" removido do banco.')

        # ── Adicionar lead a uma campanha ─────────────────────────────────────
        elif action == 'add_to_campaign' and lead_id:
            campanha_id = request.POST.get('campanha_id')
            lead     = get_object_or_404(Lead, id=lead_id, proprietarios=request.user)
            campanha = get_object_or_404(Campanha, id=campanha_id, user=request.user)
            campanha.leads.add(lead)
            messages.success(request, f'Lead adicionado à campanha "{campanha.nome}".')

        # ── Remover lead de uma campanha ──────────────────────────────────────
        elif action == 'remove_from_campaign' and lead_id:
            campanha_id = request.POST.get('campanha_id')
            lead     = get_object_or_404(Lead, id=lead_id, proprietarios=request.user)
            campanha = get_object_or_404(Campanha, id=campanha_id, user=request.user)
            campanha.leads.remove(lead)
            messages.success(request, f'Lead removido da campanha "{campanha.nome}".')

        # ── Adicionar lead manualmente ────────────────────────────────────────
        elif action == 'add_manual':
            import uuid
            nome      = request.POST.get('nome', '').strip()
            whatsapp  = request.POST.get('whatsapp', '').strip() or None
            telefone  = request.POST.get('telefone', '').strip() or None
            endereco  = request.POST.get('endereco', '').strip() or None
            site      = request.POST.get('site', '').strip() or None
            if nome:
                place_id = f"manual_{request.user.id}_{uuid.uuid4().hex[:12]}"
                lead = Lead.objects.create(
                    place_id=place_id,
                    nome=nome,
                    whatsapp=whatsapp,
                    telefone=telefone,
                    endereco=endereco,
                    site=site,
                    status='Qualificado',
                )
                lead.proprietarios.add(request.user)
                messages.success(request, f'Lead "{nome}" adicionado ao banco.')
            else:
                messages.error(request, 'Nome é obrigatório.')

        return redirect('leads:meu_banco')

    # ── GET ───────────────────────────────────────────────────────────────────
    campanhas = list(request.user.campanhas.all())
    raw_leads = request.user.leads_adquiridos.prefetch_related('campanhas').order_by('nome')

    leads_data = []
    for lead in raw_leads:
        associadas   = [c for c in lead.campanhas.all() if c.user == request.user]
        assoc_ids    = {c.id for c in associadas}
        disponiveis  = [c for c in campanhas if c.id not in assoc_ids]
        leads_data.append({
            'lead':         lead,
            'associadas':   associadas,
            'disponiveis':  disponiveis,
        })

    return render(request, 'leads/meu_banco.html', {
        'leads_data': leads_data,
        'campanhas':  campanhas,
        'total':      len(leads_data),
    })
