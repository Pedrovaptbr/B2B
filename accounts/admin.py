from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.html import format_html
from .models import PerfilUsuario, WhatsappInstance

# --- Inlines para a Página do User ---

class PerfilUsuarioInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False
    verbose_name_plural = 'Perfil de Créditos'
    fields = ('creditos_disponiveis',)
    readonly_fields = ('total_extraido',)

class WhatsappInstanceInline(admin.StackedInline):
    model = WhatsappInstance
    can_delete = False
    verbose_name_plural = 'Instância do WhatsApp'
    readonly_fields = ('instance_name', 'status')
    fields = ('instance_name', 'status')

# --- A "Super View" do Usuário ---

# 1. Definimos a classe customizada sem o decorador
class CustomUserAdmin(BaseUserAdmin):
    inlines = (PerfilUsuarioInline, WhatsappInstanceInline)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_creditos')
    
    readonly_fields = ('date_joined', 'last_login', 'view_leads_link', 'view_historico_link')

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Informações Pessoais', {'fields': ('first_name', 'last_name', 'email')}),
        ('Dados da Aplicação', {'fields': ('view_leads_link', 'view_historico_link')}),
        ('Permissões', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Datas Importantes', {'fields': ('date_joined', 'last_login')}),
    )

    @admin.display(description='Créditos')
    def get_creditos(self, obj):
        # Adicionado um 'try' para evitar erros se o perfil ainda não existir
        try:
            return obj.perfil.creditos_disponiveis
        except PerfilUsuario.DoesNotExist:
            return 0

    @admin.display(description='Leads Adquiridos')
    def view_leads_link(self, obj):
        count = obj.leads_adquiridos.count()
        url = (
            reverse("admin:leads_lead_changelist")
            + f"?proprietarios__id__exact={obj.id}"
        )
        return format_html('<a href="{}">Ver {} Leads</a>', url, count)

    @admin.display(description='Histórico de Buscas')
    def view_historico_link(self, obj):
        count = obj.historico_buscas.count()
        url = (
            reverse("admin:leads_historicobusca_changelist")
            + f"?user__id__exact={obj.id}"
        )
        return format_html('<a href="{}">Ver {} Buscas</a>', url, count)

# 2. Desregistramos o UserAdmin padrão
admin.site.unregister(User)
# 3. Registramos o nosso UserAdmin customizado
admin.site.register(User, CustomUserAdmin)


@admin.register(WhatsappInstance)
class WhatsappInstanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'instance_name', 'status')
    list_filter = ('status',)
    search_fields = ('user__username', 'instance_name')
    readonly_fields = ('user', 'instance_name', 'instance_token', 'qr_code_base64')
