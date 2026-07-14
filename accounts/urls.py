from django.urls import path, include
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('', include('django.contrib.auth.urls')),
    
    path('planos/', views.planos_view, name='planos'),
    path('whatsapp/', views.whatsapp_instance_view, name='whatsapp_instance'),
    path('whatsapp/status/', views.whatsapp_status_api_view, name='whatsapp_status_api'),
    path('whatsapp/test-send/', views.test_send_view, name='test_send'),

    # ── Stripe — assinatura ───────────────────────────────────────────────────
    path('checkout/',                views.stripe_checkout_view,         name='stripe_checkout'),
    path('checkout/sucesso/',        views.stripe_success_view,          name='stripe_success'),
    path('portal/',                  views.stripe_portal_view,           name='stripe_portal'),
    path('webhook/stripe/',          views.stripe_webhook_view,          name='stripe_webhook'),

    # ── Stripe — créditos avulsos ─────────────────────────────────────────────
    path('creditos/checkout/',       views.stripe_credits_checkout_view, name='credits_checkout'),
    path('creditos/sucesso/',        views.stripe_credits_success_view,  name='credits_success'),

    # ── Stripe — plano Enterprise (interno/staff) ───────────────────────────────
    path('admin/enterprise/',        views.enterprise_checkout_view,     name='enterprise_checkout'),

]
