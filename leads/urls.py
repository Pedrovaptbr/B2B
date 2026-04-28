from django.urls import path
from . import views

app_name = 'leads'

urlpatterns = [
    path('', views.campaign_list_view, name='campaign_list'),
    
    # Gerenciamento de Leads do Usuário
    path('meu-banco/', views.meu_banco_view, name='meu_banco'),

    # Gerenciamento de Campanhas
    path('campanha/editar/<int:pk>/', views.campaign_edit_view, name='campaign_edit'),
    path('campanha/apagar/<int:pk>/', views.campaign_delete_view, name='campaign_delete'),
    
    # Detalhes e Ações da Campanha
    path('campanha/<int:pk>/', views.campanha_detalhes_view, name='campanha_detalhes'),
    path('campanha/<int:pk>/buscar/', views.campanha_buscar_leads_view, name='campanha_buscar'),
    path('campanha/<int:pk>/validar/', views.validar_contatos_view, name='validar_contatos'),
    path('campanha/<int:pk>/exportar/', views.export_csv_view, name='export_csv'),
    path('campanha/<int:pk>/bulk-delete-leads/', views.bulk_delete_leads_view, name='bulk_delete_leads'),

    # Ações de Lead
    path('campanha/<int:campanha_id>/extract/<str:place_id>/', views.extract_lead_view, name='extract_lead'),
    path('campanha/<int:campanha_id>/disparar/', views.disparar_campanha_view, name='disparar_campanha'),

    # Conversa WhatsApp por Lead
    path('lead/<int:lead_id>/conversa/', views.conversa_lead_view, name='conversa_lead'),
    path('lead/<int:lead_id>/responder/', views.api_send_message_view, name='api_responder_lead'),

    # Templates de Mensagem
    path('campanha/<int:campanha_id>/template/criar/', views.template_criar_view, name='template_criar'),
    path('campanha/<int:campanha_id>/template/<int:template_id>/deletar/', views.template_deletar_view, name='template_deletar'),
    path('campanha/<int:campanha_id>/template/<int:template_id>/toggle/', views.template_toggle_campanha_view, name='template_toggle'),
    path('campanha/<int:campanha_id>/template/salvar-msg-padrao/', views.template_salvar_msg_padrao_view, name='template_salvar_msg_padrao'),

    # API Interna
    path('api/cidades/<int:uf_id>/', views.get_cidades_por_estado, name='api_get_cidades'),
    path('api/templates/', views.api_templates_view, name='api_templates'),
]
