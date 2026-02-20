from django.urls import path, include
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('', include('django.contrib.auth.urls')),
    
    path('whatsapp/', views.whatsapp_instance_view, name='whatsapp_instance'),
    path('whatsapp/status/', views.whatsapp_status_api_view, name='whatsapp_status_api'), # Nova rota
    path('whatsapp/test-send/', views.test_send_view, name='test_send'),
]
