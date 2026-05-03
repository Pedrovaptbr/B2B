from rest_framework import serializers
from .models import Campanha, Lead, WhatsappInstance, PerfilUsuario
from django.contrib.auth.models import User

class PerfilUsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerfilUsuario
        fields = ['creditos_disponiveis', 'total_extraido']

class UserSerializer(serializers.ModelSerializer):
    perfil = PerfilUsuarioSerializer(read_only=True)
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'perfil']

class WhatsappInstanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhatsappInstance
        fields = ['instance_name', 'status', 'qr_code_base64', 'updated_at']

class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = ['id', 'nome', 'endereco', 'telefone', 'whatsapp', 'site', 'status']

class CampanhaSerializer(serializers.ModelSerializer):
    leads = LeadSerializer(many=True, read_only=True)

    class Meta:
        model = Campanha
        fields = ['id', 'nome', 'data_criacao', 'leads']
