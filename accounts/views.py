from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from django.conf import settings
import re
import logging
from .models import WhatsappInstance
from leads import services
from .forms import CustomUserCreationForm, CustomAuthenticationForm

def landing_page_view(request):
    if request.user.is_authenticated:
        return redirect('leads:campaign_list')
    return render(request, 'landing_page.html')

def register_view(request):
    if request.user.is_authenticated:
        return redirect('leads:campaign_list')
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registro bem-sucedido! Bem-vindo.")
            return redirect('leads:campaign_list')
    else:
        form = CustomUserCreationForm()
    return render(request, 'accounts/registration/register.html', {'form': form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect('leads:campaign_list')
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if not request.POST.get('remember_me', None):
                request.session.set_expiry(0)
            next_url = request.GET.get('next', reverse('leads:campaign_list'))
            return redirect(next_url)
    else:
        form = CustomAuthenticationForm()
    return render(request, 'accounts/registration/login.html', {'form': form})

@login_required
def whatsapp_instance_view(request):
    instance, _ = WhatsappInstance.objects.get_or_create(user=request.user, defaults={'instance_name': f"{request.user.username.lower()}_{request.user.id}"})

    if request.method == 'POST':
        instance.qr_code_base64 = None
        instance.save()
        
        result = services.create_evolution_instance(instance.instance_name)
        if settings.DEBUG:
            logging.warning(f"DEBUG: create_evolution_instance result: {result}")
        
        if result.get('success'):
            instance.instance_token = result.get('token')
            instance.qr_code_base64 = result.get('qr_code')
            instance.status = 'CONNECTING'
            instance.save()
            messages.info(request, "Instância resetada. Escaneie o novo QR Code.")
        else:
            messages.error(request, f"Erro na API ao resetar: {result.get('error')}")
        return redirect('accounts:whatsapp_instance')

    connection_state = services.get_instance_connection_state(instance.instance_name)

    if connection_state == "NOT_FOUND":
        messages.warning(request, "Instância não encontrada na API. Por favor, clique em 'Resetar Instância'.")
        instance.status = 'DISCONNECTED'
        instance.save()
    
    elif "ERROR" in connection_state:
        messages.error(request, f"Não foi possível verificar o status da conexão: {connection_state}")
    
    else:
        current_status = connection_state.upper()
        if instance.status != current_status:
            instance.status = current_status
            instance.save()
        
        if current_status not in ['CONNECTED', 'OPEN']:
            if not instance.qr_code_base64:
                result = services.get_instance_qrcode(instance.instance_name)
                if settings.DEBUG:
                    logging.warning(f"DEBUG: get_instance_qrcode result: {result}")
                
                if result.get('success') and result.get('qr_code'):
                    instance.qr_code_base64 = result.get('qr_code')
                    instance.status = 'CONNECTING'
                    instance.save()
        
        elif instance.qr_code_base64:
            instance.qr_code_base64 = None
            instance.save()

    return render(request, 'accounts/whatsapp_instance.html', {'instance': instance})

@login_required
def whatsapp_status_api_view(request):
    instance, _ = WhatsappInstance.objects.get_or_create(user=request.user)
    connection_state = services.get_instance_connection_state(instance.instance_name)
    return JsonResponse({'status': connection_state})

@login_required
def test_send_view(request):
    context = {}
    if request.method == 'POST':
        numero, mensagem = request.POST.get('numero'), request.POST.get('mensagem')
        if not all([numero, mensagem]):
            messages.error(request, "Número e mensagem são obrigatórios.")
        else:
            try:
                instance = request.user.whatsapp_instance
                numero_limpo = '55' + re.sub(r'\D', '', numero)
                resultado = services.send_whatsapp_message(instance.instance_name, instance.instance_token, numero_limpo, mensagem)
                
                context['resultado_envio'] = resultado
                context['numero_enviado'] = numero_limpo

            except WhatsappInstance.DoesNotExist:
                messages.error(request, "Você precisa configurar sua instância do WhatsApp primeiro.")
        
    return render(request, 'accounts/test_send.html', context)
