from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import re
import logging
import stripe
from .models import WhatsappInstance, PerfilUsuario
from leads import services
from .forms import CustomUserCreationForm, CustomAuthenticationForm

stripe.api_key = settings.STRIPE_SECRET_KEY

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
def planos_view(request):
    return render(request, 'accounts/planos.html')

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
def whatsapp_chats_api_view(request):
    """
    AJAX — retorna os leads do banco do usuário que têm WhatsApp,
    agrupados por campanha, para montar o inbox "só com leads".
    """
    from leads.models import Lead, Campanha
    from django.db.models import Prefetch

    # Pré-carrega só as campanhas do usuário — evita N+1
    campanhas_do_usuario = Campanha.objects.filter(user=request.user)

    leads_qs = (
        Lead.objects
        .filter(proprietarios=request.user)
        .exclude(whatsapp__isnull=True)
        .exclude(whatsapp='')
        .prefetch_related(Prefetch('campanhas', queryset=campanhas_do_usuario))
        .order_by('nome')
    )

    chats = []
    for lead in leads_qs:
        # Usa o prefetch — sem query adicional por lead
        campanhas_nomes = [c.nome for c in lead.campanhas.all()]
        chats.append({
            'jid':       lead.whatsapp,          # número limpo (usado para buscar msgs)
            'lead_id':   lead.pk,
            'name':      lead.nome,
            'status':    lead.get_status_display(),
            'campanhas': ', '.join(campanhas_nomes) if campanhas_nomes else '—',
            'datetime':  '',
            'unread':    0,
        })

    return JsonResponse({'chats': chats})


@login_required
def whatsapp_messages_api_view(request):
    """AJAX — retorna mensagens de uma conversa dado o JID (ou número)."""
    jid = request.GET.get('jid', '').strip()
    if not jid:
        return JsonResponse({'error': 'JID não informado.'}, status=400)

    try:
        instance = request.user.whatsapp_instance
    except WhatsappInstance.DoesNotExist:
        return JsonResponse({'error': 'Instância não encontrada.'}, status=400)

    # Aceita tanto JID completo quanto número limpo
    numero = jid.replace('@s.whatsapp.net', '').replace('@lid', '')
    mensagens = services.fetch_whatsapp_messages(instance.instance_name, numero)

    from datetime import datetime
    for msg in mensagens:
        try:
            msg['datetime'] = datetime.fromtimestamp(msg['timestamp']).strftime('%d/%m %H:%M')
        except Exception:
            msg['datetime'] = ''

    return JsonResponse({'messages': mensagens})


@login_required
def whatsapp_send_api_view(request):
    """AJAX — envia mensagem para um JID (número) via instância do usuário."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método não permitido.'}, status=405)

    try:
        instance = request.user.whatsapp_instance
    except WhatsappInstance.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Instância não encontrada.'}, status=400)

    import json as _json
    try:
        body = _json.loads(request.body)
        jid = body.get('jid', '').strip()
        texto = body.get('texto', '').strip()
    except (ValueError, KeyError):
        return JsonResponse({'success': False, 'error': 'Payload inválido.'}, status=400)

    if not jid or not texto:
        return JsonResponse({'success': False, 'error': 'JID e texto são obrigatórios.'}, status=400)

    # Usa o número limpo (sem @s.whatsapp.net) para o send_whatsapp_message
    numero = jid.replace('@s.whatsapp.net', '').replace('@lid', '')

    resultado = services.send_whatsapp_message(
        instance.instance_name,
        instance.instance_token,
        numero,
        texto,
    )

    if resultado.get('success'):
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': resultado.get('error', 'Erro ao enviar.')}, status=500)


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


# ══════════════════════════════════════════════════════════════════════════════
# STRIPE — Checkout / Webhook
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def stripe_checkout_view(request):
    """Cria uma Stripe Checkout Session e redireciona o usuário."""
    perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)

    # Reutiliza ou cria o customer no Stripe
    if not perfil.stripe_customer_id:
        customer = stripe.Customer.create(
            email=request.user.email,
            name=request.user.get_full_name() or request.user.username,
            metadata={'user_id': request.user.pk},
        )
        perfil.stripe_customer_id = customer.id
        perfil.save(update_fields=['stripe_customer_id'])
    
    base_url = settings.SITE_URL.rstrip('/')
    try:
        session = stripe.checkout.Session.create(
            customer=perfil.stripe_customer_id,
            mode='subscription',
            line_items=[{'price': settings.STRIPE_PRICE_ID, 'quantity': 1}],
            success_url=f"{base_url}/accounts/checkout/sucesso/?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/accounts/planos/",
            locale='pt-BR',
            metadata={'user_id': request.user.pk},
        )
        return redirect(session.url, permanent=False)
    except stripe.error.StripeError as e:
        messages.error(request, f"Erro ao iniciar pagamento: {e.user_message or str(e)}")
        return redirect('accounts:planos')


@login_required
def stripe_success_view(request):
    """Página de sucesso após pagamento. Ativa o plano imediatamente via session."""
    session_id = request.GET.get('session_id')
    if session_id:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            if session.payment_status == 'paid':
                perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)
                perfil.plano_ativo = True
                perfil.creditos_disponiveis = 100
                if session.subscription:
                    perfil.stripe_subscription_id = session.subscription
                perfil.save(update_fields=['plano_ativo', 'creditos_disponiveis', 'stripe_subscription_id'])
        except stripe.error.StripeError:
            pass
    return render(request, 'accounts/checkout_success.html')


@login_required
def stripe_portal_view(request):
    """Redireciona para o portal de gerenciamento de assinatura do Stripe."""
    perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)
    if not perfil.stripe_customer_id:
        messages.error(request, "Nenhuma assinatura encontrada.")
        return redirect('accounts:planos')
    
    base_url = settings.SITE_URL.rstrip('/')
    session = stripe.billing_portal.Session.create(
        customer=perfil.stripe_customer_id,
        return_url=f"{base_url}/accounts/planos/",
    )
    return redirect(session.url, permanent=False)


@csrf_exempt
@require_POST
def stripe_webhook_view(request):
    """Recebe eventos do Stripe via webhook e atualiza o banco."""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    ev_type = event['type']
    data = event['data']['object']

    # ── Assinatura criada / renovada / ativada ────────────────────────────────
    if ev_type in ('customer.subscription.created', 'customer.subscription.updated'):
        status = data.get('status')
        customer_id = data.get('customer')
        sub_id = data.get('id')
        ativo = status in ('active', 'trialing')
        PerfilUsuario.objects.filter(stripe_customer_id=customer_id).update(
            plano_ativo=ativo,
            stripe_subscription_id=sub_id,
        )

    # ── Assinatura cancelada / expirada ───────────────────────────────────────
    elif ev_type == 'customer.subscription.deleted':
        customer_id = data.get('customer')
        PerfilUsuario.objects.filter(stripe_customer_id=customer_id).update(
            plano_ativo=False,
            stripe_subscription_id=None,
        )

    # ── Pagamento de fatura bem-sucedido (renovação mensal) ───────────────────
    elif ev_type == 'invoice.payment_succeeded':
        customer_id = data.get('customer')
        PerfilUsuario.objects.filter(stripe_customer_id=customer_id).update(
            plano_ativo=True,
            creditos_disponiveis=100,
        )

    # ── Falha no pagamento ────────────────────────────────────────────────────
    elif ev_type == 'invoice.payment_failed':
        customer_id = data.get('customer')
        # Mantém ativo até o Stripe cancelar a assinatura (ele tenta mais vezes)
        logging.getLogger(__name__).warning(f"Stripe: pagamento falhou para customer {customer_id}")

    return HttpResponse(status=200)
