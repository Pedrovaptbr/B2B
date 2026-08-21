from django.contrib import admin
from .models import Campanha, Lead, HistoricoBusca, ConfiguracaoDisparo

@admin.register(ConfiguracaoDisparo)
class ConfiguracaoDisparoAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'bloqueado', 'atualizado_em')
    fields = ('bloqueado', 'mensagem_bloqueio')
    readonly_fields = ('atualizado_em',)

    def has_add_permission(self, request):
        # Singleton: só existe um registro (pk=1), criado sob demanda.
        return not ConfiguracaoDisparo.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Pula a lista e vai direto pro form de edição da instância única.
        obj = ConfiguracaoDisparo.atual()
        from django.shortcuts import redirect
        return redirect('admin:leads_configuracaodisparo_change', obj.pk)


@admin.register(Campanha)
class CampanhaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'user', 'data_criacao')
    list_filter = ('user',)
    search_fields = ('nome',)
    autocomplete_fields = ['user']
    filter_horizontal = ('leads',)

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('nome', 'whatsapp', 'status', 'get_proprietarios')
    list_filter = ('status',)
    search_fields = ('nome', 'whatsapp', 'place_id')
    readonly_fields = ('place_id', 'nome', 'endereco', 'telefone', 'whatsapp', 'site', 'rating', 'get_proprietarios_list')
    filter_horizontal = ('proprietarios',)
    
    fieldsets = (
        ('Informações do Lead', {'fields': ('nome', 'endereco', 'telefone', 'whatsapp', 'site', 'rating', 'status')}),
        ('Proprietários', {'fields': ('proprietarios',)}),
    )

    @admin.display(description='Proprietários')
    def get_proprietarios(self, obj):
        return ", ".join([p.username for p in obj.proprietarios.all()[:3]]) + ('...' if obj.proprietarios.count() > 3 else '')

    @admin.display(description='Lista de Proprietários')
    def get_proprietarios_list(self, obj):
        return ", ".join([p.username for p in obj.proprietarios.all()])


@admin.register(HistoricoBusca)
class HistoricoBuscaAdmin(admin.ModelAdmin):
    list_display = ('user', 'tipo_empresa', 'cidade', 'estado', 'data_busca')
    list_filter = ('user', 'estado')
    search_fields = ('user__username', 'tipo_empresa', 'cidade')
    date_hierarchy = 'data_busca'
