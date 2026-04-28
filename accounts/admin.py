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
    verbose_name_plural = 'Perfil do Usuário'
    readonly_fields = ('total_leads_adquiridos',)
    fields = ('total_leads_adquiridos',)

class WhatsappInstanceInline(admin.StackedInline):
    model = WhatsappInstance
    can_delete = False
    verbose_name_plural = 'Instância do WhatsApp'
    readonly_fields = ('instance_name', 'status')
    fields = ('instance_name', 'status')

# --- A "Super View" do Usuário ---

class CustomUserAdmin(BaseUserAdmin):
    inlines = (PerfilUsuarioInline, WhatsappInstanceInline)
    list_display = ('username', 'email', 'is_staff')
    
    readonly_fields = ('date_joined', 'last_login', 'view_leads_link', 'view_historico_link')

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Informações Pessoais', {'fields': ('first_name', 'last_name', 'email')}),
        ('Dados da Aplicação', {'fields': ('view_leads_link', 'view_historico_link')}),
        ('Permissões', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Datas Importantes', {'fields': ('date_joined', 'last_login')}),
    )

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

# Desregistra e registra o UserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

@admin.register(WhatsappInstance)
class WhatsappInstanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'instance_name', 'status')
    list_filter = ('status',)
    search_fields = ('user__username', 'instance_name')
    readonly_fields = ('user', 'instance_name', 'instance_token', 'qr_code_base64')
