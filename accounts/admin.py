from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.html import format_html

from .models import PerfilUsuario, WhatsappInstance


# ── Inline do Perfil (editável: créditos e plano) ────────────────────────────
class PerfilUsuarioInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False
    verbose_name_plural = 'Perfil — Créditos & Plano'
    readonly_fields = (
        'total_leads_adquiridos',
        'total_extraido',
        'stripe_customer_id',
        'stripe_subscription_id',
    )
    fields = (
        'creditos_disponiveis',     # editável
        'plano_ativo',              # editável
        'total_extraido',
        'total_leads_adquiridos',
        'stripe_customer_id',
        'stripe_subscription_id',
    )


class WhatsappInstanceInline(admin.StackedInline):
    model = WhatsappInstance
    can_delete = False
    verbose_name_plural = 'Instância do WhatsApp'
    readonly_fields = ('instance_name', 'status')
    fields = ('instance_name', 'status')


# ── Custom User Admin ────────────────────────────────────────────────────────
class CustomUserAdmin(BaseUserAdmin):
    inlines = (PerfilUsuarioInline, WhatsappInstanceInline)
    list_display = (
        'username', 'email',
        'get_creditos', 'get_plano',
        'get_leads_adquiridos',
        'is_staff', 'date_joined',
    )
    list_filter = BaseUserAdmin.list_filter + ('perfil__plano_ativo',)
    search_fields = ('username', 'email', 'first_name', 'last_name')

    actions = (
        'adicionar_10_creditos',
        'adicionar_50_creditos',
        'adicionar_100_creditos',
        'remover_10_creditos',
        'zerar_creditos',
        'ativar_plano',
        'cancelar_plano',
    )

    readonly_fields = ('date_joined', 'last_login', 'view_leads_link', 'view_historico_link')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Informações Pessoais', {'fields': ('first_name', 'last_name', 'email')}),
        ('Dados da Aplicação', {'fields': ('view_leads_link', 'view_historico_link')}),
        ('Permissões', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Datas Importantes', {'fields': ('date_joined', 'last_login')}),
    )

    # ── Colunas extras no list_display ───────────────────────────────────────
    @admin.display(description='Créditos', ordering='perfil__creditos_disponiveis')
    def get_creditos(self, obj):
        try:
            return obj.perfil.creditos_disponiveis
        except PerfilUsuario.DoesNotExist:
            return '—'

    @admin.display(description='Plano Pro', boolean=True, ordering='perfil__plano_ativo')
    def get_plano(self, obj):
        try:
            return obj.perfil.plano_ativo
        except PerfilUsuario.DoesNotExist:
            return False

    @admin.display(description='Leads')
    def get_leads_adquiridos(self, obj):
        return obj.leads_adquiridos.count()

    # ── Links na página do usuário ───────────────────────────────────────────
    @admin.display(description='Leads Adquiridos')
    def view_leads_link(self, obj):
        count = obj.leads_adquiridos.count()
        url = reverse("admin:leads_lead_changelist") + f"?proprietarios__id__exact={obj.id}"
        return format_html('<a href="{}">Ver {} Leads</a>', url, count)

    @admin.display(description='Histórico de Buscas')
    def view_historico_link(self, obj):
        count = obj.historico_buscas.count()
        url = reverse("admin:leads_historicobusca_changelist") + f"?user__id__exact={obj.id}"
        return format_html('<a href="{}">Ver {} Buscas</a>', url, count)

    # ── Helper que aplica delta de créditos em lote ──────────────────────────
    def _ajustar_creditos(self, request, queryset, delta):
        count = 0
        for user in queryset:
            perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
            perfil.creditos_disponiveis = max(0, perfil.creditos_disponiveis + delta)
            perfil.save()
            count += 1
        verbo = 'adicionados a' if delta > 0 else 'removidos de'
        self.message_user(
            request,
            f"{abs(delta)} créditos {verbo} {count} usuário(s).",
            messages.SUCCESS if delta > 0 else messages.WARNING,
        )

    # ── Ações em lote ────────────────────────────────────────────────────────
    @admin.action(description='+10 créditos')
    def adicionar_10_creditos(self, request, queryset):
        self._ajustar_creditos(request, queryset, 10)

    @admin.action(description='+50 créditos')
    def adicionar_50_creditos(self, request, queryset):
        self._ajustar_creditos(request, queryset, 50)

    @admin.action(description='+100 créditos')
    def adicionar_100_creditos(self, request, queryset):
        self._ajustar_creditos(request, queryset, 100)

    @admin.action(description='-10 créditos')
    def remover_10_creditos(self, request, queryset):
        self._ajustar_creditos(request, queryset, -10)

    @admin.action(description='Zerar créditos')
    def zerar_creditos(self, request, queryset):
        count = 0
        for user in queryset:
            perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
            perfil.creditos_disponiveis = 0
            perfil.save()
            count += 1
        self.message_user(request, f"Créditos zerados em {count} usuário(s).", messages.WARNING)

    @admin.action(description='Ativar Plano Pro')
    def ativar_plano(self, request, queryset):
        count = 0
        for user in queryset:
            perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
            perfil.plano_ativo = True
            perfil.save()
            count += 1
        self.message_user(request, f"Plano Pro ativado para {count} usuário(s).", messages.SUCCESS)

    @admin.action(description='Cancelar Plano Pro')
    def cancelar_plano(self, request, queryset):
        count = 0
        for user in queryset:
            perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
            perfil.plano_ativo = False
            perfil.save()
            count += 1
        self.message_user(request, f"Plano Pro cancelado para {count} usuário(s).", messages.WARNING)


# Desregistra e registra o UserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(WhatsappInstance)
class WhatsappInstanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'instance_name', 'status')
    list_filter = ('status',)
    search_fields = ('user__username', 'instance_name')
    readonly_fields = ('user', 'instance_name', 'instance_token', 'qr_code_base64')
