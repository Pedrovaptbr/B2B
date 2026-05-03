from django.contrib.auth.models import User
from rest_framework import authentication, exceptions
from django.conf import settings

class ApiKeyAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get('apikey')
        correct_key = settings.EVOLUTION_API_KEY

        if not api_key or api_key != correct_key:
            return None

        # Para simplificar, associamos a chave de API ao primeiro superusuário.
        # Em um sistema multi-usuário real, cada usuário teria sua própria chave.
        try:
            user = User.objects.filter(is_superuser=True).first()
            if not user:
                raise User.DoesNotExist
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('Nenhum usuário administrador configurado no backend.')

        return (user, None)
