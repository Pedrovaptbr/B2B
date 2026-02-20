from django.contrib import admin
from .models import Campanha, Lead, HistoricoBusca

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
