from django.urls import path
from . import views

app_name = 'leads'

urlpatterns = [
    path('', views.campaign_list_view, name='campaign_list'),
    path('campanha/editar/<int:pk>/', views.campaign_edit_view, name='campaign_edit'),
    path('campanha/apagar/<int:pk>/', views.campaign_delete_view, name='campaign_delete'),
    
    path('campanha/<int:pk>/', views.campanha_detalhes_view, name='campanha_detalhes'),
    path('campanha/<int:pk>/buscar/', views.campanha_buscar_leads_view, name='campanha_buscar'),
    path('campanha/<int:pk>/validar/', views.validar_contatos_view, name='validar_contatos'),
    path('campanha/<int:pk>/exportar/', views.export_csv_view, name='export_csv'),
    path('campanha/<int:pk>/bulk-delete-leads/', views.bulk_delete_leads_view, name='bulk_delete_leads'),

    path('campanha/<int:campanha_id>/extract/<str:place_id>/', views.extract_lead_view, name='extract_lead'),
    path('campanha/<int:campanha_id>/disparar/', views.disparar_campanha_view, name='disparar_campanha'),

    # API Interna
    path('api/cidades/<int:uf_id>/', views.get_cidades_por_estado, name='api_get_cidades'),
]
