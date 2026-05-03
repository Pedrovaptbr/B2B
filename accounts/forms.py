from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User

class CustomUserCreationForm(UserCreationForm):
    """
    Um formulário de criação de usuário que força o nome de usuário a ser salvo em minúsculas.
    """
    def clean_username(self):
        username = self.cleaned_data.get("username")
        return username.lower()

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)

class CustomAuthenticationForm(AuthenticationForm):
    """
    Um formulário de autenticação que converte o nome de usuário para minúsculas antes de validar.
    """
    def clean_username(self):
        username = self.cleaned_data.get("username")
        return username.lower()
