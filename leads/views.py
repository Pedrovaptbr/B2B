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
from .models import Campanha, Lead, HistoricoBusca
from accounts.models import PerfilUsuario, WhatsappInstance
from . import services

# Configura o logger para exibir mensagens de debug
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

# --- Views de Campanhas (CRUD) ---

@login_required
def campaign_list_view(request):
    if request.method == 'POST':
        nome_campanha = request.POST.get('nome_campanha')
        if nome_campanha:
            try:
                Campanha.objects.create(user=request.user, nome=nome_campanha)
                messages.success(request, f"Campanha '{nome_campanha}' criada.")
            except IntegrityError:
                messages.error(request, f"Você já tem uma campanha com o nome '{nome_campanha}'.")
        else:
            messages.error(request, "O nome da campanha não pode ser vazio.")
        return redirect('leads:campaign_list')
    
    campanhas = Campanha.objects.filter(user=request.user)
    return render(request, 'leads/campaign_list.html', {'campanhas': campanhas})

@login_required
def campaign_edit_view(request, pk):
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)
    if request.method == 'POST':
        novo_nome = request.POST.get('nome_campanha')
        mensagem_padrao = request.POST.get('mensagem_padrao')

        if novo_nome:
            try:
                campanha.nome = novo_nome
                campanha.mensagem_padrao = mensagem_padrao
                campanha.save()
                messages.success(request, "Campanha atualizada com sucesso.")
                return redirect('leads:campanha_detalhes', pk=campanha.pk)
            except IntegrityError:
                messages.error(request, f"Você já tem uma campanha com o nome '{novo_nome}'.")
        else:
            messages.error(request, "O nome da campanha não pode ser vazio.")
    
    return render(request, 'leads/campaign_edit.html', {'campanha': campanha})

@login_required
def campaign_delete_view(request, pk):
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)
    if request.method == 'POST':
        nome_campanha = campanha.nome
        campanha.delete()
        messages.success(request, f"Campanha '{nome_campanha}' apagada.")
        return redirect('leads:campaign_list')
    return render(request, 'leads/campaign_delete.html', {'campanha': campanha})

# --- Views de Leads ---

@login_required
def campanha_detalhes_view(request, pk):
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)
    leads = campanha.leads.all().order_by('-id')
    return render(request, 'leads/campanha_detalhes.html', {'campanha': campanha, 'leads': leads})

@login_required
def campanha_buscar_leads_view(request, pk):
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)
    
    try:
        response_estados = requests.get('https://servicodados.ibge.gov.br/api/v1/localidades/estados?orderBy=nome')
        estados = response_estados.json()
    except requests.RequestException:
        estados = []
        messages.error(request, "Não foi possível carregar os estados do Brasil.")

    context = {'campanha': campanha, 'estados': estados}
    
    tipo_empresa = request.GET.get('tipo_empresa')
    cidade = request.GET.get('cidade')
    estado = request.GET.get('estado')

    if tipo_empresa and cidade and estado:
        HistoricoBusca.objects.update_or_create(
            user=request.user, tipo_empresa=tipo_empresa, cidade=cidade, estado=estado,
            defaults={'data_busca': timezone.now()}
        )

        query = f"{tipo_empresa} em {cidade}, {estado}"
        search_data = services.get_google_text_search(query)
        
        if search_data.get('status') == 'OK':
            resultados_processados = []
            place_ids_na_campanha = set(campanha.leads.values_list('place_id', flat=True))
            leads_ja_extraidos = {lead.place_id: lead for lead in Lead.objects.filter(proprietarios=request.user)}

            for result in search_data.get('results', []):
                place_id = result.get('place_id')
                result['ja_esta_na_campanha'] = place_id in place_ids_na_campanha
                
                lead_existente = leads_ja_extraidos.get(place_id)
                if lead_existente:
                    result['ja_foi_extraido'] = True
                    result['tem_whatsapp'] = bool(lead_existente.whatsapp)
                else:
                    result['ja_foi_extraido'] = False
                    result['tem_whatsapp'] = None

                resultados_processados.append(result)
            context['search_results'] = resultados_processados
        else:
            messages.error(request, f"Erro ao buscar no Google: {search_data.get('status')}")
    
    historico_buscas = HistoricoBusca.objects.filter(user=request.user)[:5]
    context['historico_buscas'] = historico_buscas

    return render(request, 'leads/campanha_buscar.html', context)

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
            messages.error(request, "Créditos insuficientes para extrair novo lead.")
            if criado: lead.delete()
            return redirect(redirect_url)
        
        if criado or 'Lead Provisório' in lead.nome:
            details = services.get_google_place_details(place_id)
            if not details:
                messages.error(request, "Não foi possível obter detalhes do Google.")
                if criado: lead.delete()
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
            
            try:
                instance = request.user.whatsapp_instance
                if whatsapp_limpo and instance.status == 'CONNECTED':
                    check_results = services.verify_whatsapp_numbers(instance.instance_name, [whatsapp_limpo])
                    number_check = check_results.get(whatsapp_limpo, {})
                    lead.status = 'Telefone Inexistente' if not number_check.get("exists") else 'Qualificado'
                else:
                    lead.status = 'Qualificado'
            except WhatsappInstance.DoesNotExist:
                lead.status = 'Qualificado'
            
            lead.save()

        perfil.creditos_disponiveis -= 1
        perfil.total_extraido += 1
        perfil.save()
        lead.proprietarios.add(request.user)
        messages.success(request, f"Novo lead '{lead.nome}' extraído e adicionado à campanha!")

    else:
        messages.info(request, f"Lead '{lead.nome}' importado do seu cofre para a campanha (grátis).")

    campanha.leads.add(lead)
    return redirect(redirect_url)

@login_required
def validar_contatos_view(request, pk):
    log.debug("--- INICIANDO VIEW 'validar_contatos_view' ---")
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)
    
    try:
        instance = request.user.whatsapp_instance
        connection_state = services.get_instance_connection_state(instance.instance_name)
        log.debug(f"Status da conexão da instância '{instance.instance_name}': {connection_state}")

        if connection_state.upper() not in ['CONNECTED', 'OPEN']:
            messages.error(request, f"Sua instância do WhatsApp precisa estar conectada para validar. Status atual: {connection_state}")
            log.warning("Validação interrompida: Instância não está conectada.")
            return redirect('accounts:whatsapp_instance')
    except WhatsappInstance.DoesNotExist:
        messages.error(request, "Configure sua instância do WhatsApp primeiro.")
        log.error("Validação interrompida: Instância do WhatsApp não encontrada para o usuário.")
        return redirect('accounts:whatsapp_instance')

    leads_para_validar = campanha.leads.filter(status='Qualificado')
    log.debug(f"Encontrados {leads_para_validar.count()} leads com status 'Qualificado'.")
    if not leads_para_validar.exists():
        messages.info(request, "Nenhum lead com status 'Qualificado' para validar nesta campanha.")
        return redirect('leads:campanha_detalhes', pk=pk)

    numeros_para_validar = [lead.whatsapp for lead in leads_para_validar if lead.whatsapp]
    if not numeros_para_validar:
        messages.info(request, "Nenhum lead com número de WhatsApp para validar.")
        return redirect('leads:campanha_detalhes', pk=pk)

    resultados_validacao = services.verify_whatsapp_numbers(instance.instance_name, numeros_para_validar)
    log.debug(f"Resultados recebidos da função de serviço: {resultados_validacao}")
    
    verificados, invalidos = 0, 0
    with transaction.atomic():
        for lead in leads_para_validar:
            if lead.whatsapp in resultados_validacao:
                resultado = resultados_validacao[lead.whatsapp]
                log.debug(f"Processando lead '{lead.nome}' ({lead.whatsapp}). Resultado da API: {resultado}")
                if resultado.get('exists'):
                    lead.status = 'Verificado'
                    lead.save()
                    verificados += 1
                    log.debug(f"  -> Marcado como VERIFICADO.")
                else:
                    lead.status = 'Telefone Inexistente'
                    lead.save()
                    invalidos += 1
                    log.debug(f"  -> Marcado como INEXISTENTE. Razão: {resultado.get('reason')}")
            elif not lead.whatsapp:
                lead.status = 'Telefone Inexistente'
                lead.save()
                invalidos += 1
                log.debug(f"Processando lead '{lead.nome}'. Marcado como INEXISTENTE (sem WhatsApp).")
            
    log.debug(f"Validação finalizada. Verificados: {verificados}, Inválidos: {invalidos}")
    messages.success(request, f"Validação concluída! {verificados} contatos verificados e {invalidos} inválidos foram encontrados.")
    log.debug("--- FIM DA VIEW 'validar_contatos_view' ---")
    return redirect('leads:campanha_detalhes', pk=pk)

@login_required
def export_csv_view(request, pk):
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)
    response = HttpResponse(content_type='text/csv', headers={'Content-Disposition': f'attachment; filename="campanha_{campanha.nome}.csv"'})
    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response)
    writer.writerow(['Nome', 'Telefone', 'WhatsApp', 'Site', 'Endereço', 'Status', 'Avaliação'])
    for lead in campanha.leads.all():
        writer.writerow([lead.nome, lead.telefone, lead.whatsapp, lead.site, lead.endereco, lead.get_status_display(), lead.rating])
    return response

@login_required
def disparar_campanha_view(request, campanha_id):
    if settings.DEBUG:
        logging.warning("--- Iniciando a view de disparo ---")

    campanha = get_object_or_404(Campanha, pk=campanha_id, user=request.user)
    
    if request.method != 'POST':
        if settings.DEBUG: logging.warning("Método não é POST. Redirecionando.")
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    try:
        instance = request.user.whatsapp_instance
        connection_state = services.get_instance_connection_state(instance.instance_name)
        if settings.DEBUG: logging.warning(f"Status da conexão: {connection_state}")
        if connection_state.upper() not in ['CONNECTED', 'OPEN']:
            messages.error(request, f"Sua instância do WhatsApp precisa estar conectada. Status: {connection_state}")
            return redirect('accounts:whatsapp_instance')
    except WhatsappInstance.DoesNotExist:
        messages.error(request, "Configure sua instância do WhatsApp primeiro.")
        return redirect('accounts:whatsapp_instance')

    if not campanha.mensagem_padrao:
        if settings.DEBUG: logging.warning("Campanha sem mensagem padrão. Redirecionando.")
        messages.error(request, "Não há mensagem padrão configurada para esta campanha.")
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    lead_ids = request.POST.getlist('lead_ids')
    if settings.DEBUG: logging.warning(f"IDs dos leads recebidos: {lead_ids}")
    if not lead_ids:
        messages.warning(request, "Nenhum lead foi selecionado para o disparo.")
        return redirect('leads:campanha_detalhes', pk=campanha_id)

    leads_para_disparar = campanha.leads.filter(id__in=lead_ids)
    
    sucessos = 0
    falhas = 0

    for lead in leads_para_disparar:
        if settings.DEBUG: logging.warning(f"Processando lead: {lead.nome} ({lead.whatsapp})")
        if not lead.whatsapp:
            if settings.DEBUG: logging.warning("Lead sem WhatsApp. Pulando.")
            falhas += 1
            continue

        mensagem_personalizada = campanha.mensagem_padrao.replace('[nome]', lead.nome)
        
        resultado_envio = services.send_whatsapp_message(
            instance.instance_name, 
            instance.instance_token, 
            lead.whatsapp, 
            mensagem_personalizada
        )

        if settings.DEBUG: logging.warning(f"Resultado do envio para {lead.nome}: {resultado_envio}")

        if resultado_envio.get('success'):
            lead.status = 'Contatado'
            lead.save()
            sucessos += 1
        else:
            falhas += 1

        time.sleep(1)

    if settings.DEBUG: logging.warning(f"Disparo finalizado. Sucessos: {sucessos}, Falhas: {falhas}")
    messages.success(request, f"Disparo concluído! {sucessos} mensagens enviadas com sucesso e {falhas} falharam.")
    return redirect('leads:campanha_detalhes', pk=campanha_id)


@login_required
def bulk_delete_leads_view(request, pk):
    campanha = get_object_or_404(Campanha, pk=pk, user=request.user)
    if request.method == 'POST':
        lead_ids = request.POST.getlist('lead_ids')
        if lead_ids:
            leads_para_apagar = campanha.leads.filter(id__in=lead_ids)
            count = leads_para_apagar.count()
            campanha.leads.remove(*leads_para_apagar)
            messages.success(request, f"{count} lead(s) foram removidos da campanha.")
        else:
            messages.warning(request, "Nenhum lead foi selecionado.")
    
    return redirect('leads:campanha_detalhes', pk=pk)

# --- API Views ---

def get_cidades_por_estado(request, uf_id):
    try:
        response = requests.get(f'https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf_id}/municipios')
        cidades = response.json()
        return JsonResponse(cidades, safe=False)
    except requests.RequestException:
        return JsonResponse([], safe=False)
