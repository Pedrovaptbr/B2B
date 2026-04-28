from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.urls import reverse
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.utils import timezone
import re
import csv
import time
import logging
import requests
from .models import Campanha, Lead, HistoricoBusca, TemplateMensagem
from accounts.models import PerfilUsuario, WhatsappInstance
from . import services

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
        if nome:
            try:
                campanha.nome = nome
                campanha.mensagem_padrao = mensagem or None
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
    return render(request, 'leads/campanha_detalhes.html', {'campanha': campanha, 'leads': leads})


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
    cidade = request.GET.get('cidade', '').strip()
    estado = request.GET.get('estado', '').strip()

    if tipo_empresa and cidade and estado:
        query = f'{tipo_empresa} em {cidade}, {estado}, Brasil'
        google_data = services.get_google_text_search(query)

        if google_data.get('status') == 'OK':
            HistoricoBusca.objects.update_or_create(
                user=request.user,
                tipo_empresa=tipo_empresa,
                cidade=cidade,
                estado=estado,
            )

            ids_na_campanha = set(campanha.leads.values_list('place_id', flat=True))
            ids_extraidos = set(request.user.leads_adquiridos.values_list('place_id', flat=True))
            leads_extraidos = {
                l.place_id: l for l in Lead.objects.filter(place_id__in=ids_extraidos)
            }

            results = []
            for place in google_data.get('results', []):
                place_id = place.get('place_id')
                lead_existente = leads_extraidos.get(place_id)
                place['ja_esta_na_campanha'] = place_id in ids_na_campanha
                place['ja_foi_extraido'] = place_id in ids_extraidos
                place['tem_whatsapp'] = bool(lead_existente and lead_existente.whatsapp)
                results.append(place)

            context['search_results'] = results
        else:
            error_msg = google_data.get('error_message', 'Erro desconhecido na busca.')
            messages.error(request, f'Erro na busca: {error_msg}')

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

@login_required
@transaction.atomic
def extract_lead_view(request, campanha_id, place_id):
    campanha = get_object_or_404(Campanha, id=campanha_id, user=request.user)
    perfil = PerfilUsuario.objects.select_for_update().get(user=request.user)
    redirect_url = f"{reverse('leads:campanha_buscar', kwargs={'pk': campanha.id})}?{request.GET.urlencode()}"

    lead, criado = Lead.objects.get_or_create(
        place_id=place_id,
        defaults={'nome': f'Lead Provisório - {place_id}'}
    )

    if lead in campanha.leads.all():
        messages.warning(request, f"Lead '{lead.nome}' já está nesta campanha.")
        return redirect(redirect_url)

    usuario_ja_e_proprietario = lead.proprietarios.filter(pk=request.user.pk).exists()

    if not usuario_ja_e_proprietario:
        if perfil.creditos_disponiveis <= 0:
            messages.error(request, "Créditos insuficientes. Assine um plano para continuar extraindo leads.")
            if criado:
                lead.delete()
            return redirect(redirect_url)

        if criado or 'Lead Provisório' in lead.nome:
            details = services.get_google_place_details(place_id)
            if not details:
                messages.error(request, "Não foi possível obter detalhes do Google.")
                if criado:
                    lead.delete()
                return redirect(redirect_url)

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

        perfil.creditos_disponiveis -= 1
        perfil.total_extraido += 1
        perfil.save()
        lead.proprietarios.add(request.user)
        messages.success(request, f"Novo lead '{lead.nome}' extraído! Créditos restantes: {perfil.creditos_disponiveis}")
    else:
        messages.info(request, f"Lead '{lead.nome}' importado do seu cofre para a campanha (grátis).")

    campanha.leads.add(lead)
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

@login_required
def disparar_campanha_view(request, campanha_id):
    campanha = get_object_or_404(Campanha, pk=campanha_id, user=request.user)

    if request.method != 'POST':
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    if not campanha.mensagem_padrao:
        messages.error(request, 'Configure uma mensagem padrão antes de disparar a campanha.')
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

    lead_ids = request.POST.getlist('lead_ids')
    if not lead_ids:
        messages.error(request, 'Nenhum lead selecionado.')
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    leads_selecionados = campanha.leads.filter(
        id__in=lead_ids, whatsapp__isnull=False
    ).exclude(whatsapp='')

    enviados, erros, inexistentes = 0, 0, 0
    for lead in leads_selecionados:
        mensagem = campanha.mensagem_padrao.replace('[nome]', lead.nome)
        resultado = services.send_whatsapp_message(
            instancia.instance_name,
            instancia.instance_token,
            lead.whatsapp,
            mensagem,
        )
        if resultado.get('success'):
            lead.status = 'Contatado'
            lead.save()
            enviados += 1
        else:
            erro = resultado.get('error', '')
            logger.error(f'Erro ao enviar para {lead.whatsapp}: {erro}')

            # 400 da Evolution API = número não existe no WhatsApp
            if resultado.get('status_code') == 400:
                lead.status = 'Telefone Inexistente'
                lead.save()
                inexistentes += 1
            else:
                erros += 1
        time.sleep(1)

    if enviados:
        messages.success(request, f'{enviados} mensagem(ns) enviada(s) com sucesso!')
    if inexistentes:
        messages.warning(request, f'{inexistentes} lead(s) marcado(s) como "Telefone Inexistente" — número não está no WhatsApp.')
    if erros:
        messages.warning(request, f'{erros} mensagem(ns) não puderam ser enviadas.')

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


# ─── Meu Banco de Leads ───────────────────────────────────────────────────────

@login_required
def meu_banco_view(request):
    if request.method == 'POST':
        lead_id = request.POST.get('lead_id')
        if lead_id:
            lead = get_object_or_404(Lead, id=lead_id, proprietarios=request.user)
            lead.proprietarios.remove(request.user)
            messages.success(request, f'Lead "{lead.nome}" removido do seu banco.')
        return redirect('leads:meu_banco')

    leads = request.user.leads_adquiridos.all()
    return render(request, 'leads/meu_banco.html', {'leads': leads})
