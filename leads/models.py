from django.db import models
from django.contrib.auth.models import User

class Campanha(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='campanhas')
    nome = models.CharField(max_length=200)
    data_criacao = models.DateTimeField(auto_now_add=True)
    leads = models.ManyToManyField('Lead', related_name='campanhas')
    mensagem_padrao = models.TextField(
        blank=True,
        null=True,
        help_text="Mensagem padrão para ser enviada aos leads desta campanha."
    )
    anexo = models.FileField(
        upload_to='anexos_campanhas/',
        blank=True,
        null=True,
        help_text="Arquivo (ex: catálogo em PDF) enviado junto com a mensagem."
    )

    @property
    def anexo_nome(self):
        """Nome do arquivo do anexo, sem o caminho."""
        if not self.anexo:
            return None
        import os
        return os.path.basename(self.anexo.name)

    class Meta:
        unique_together = ('user', 'nome')
        ordering = ['-data_criacao']
    def __str__(self): return self.nome

class Lead(models.Model):
    STATUS_CHOICES = [
        ('Qualificado', 'Qualificado'),
        ('Verificado', 'Verificado'),
        ('Contatado', 'Contatado'),
        ('Respondido', 'Respondido'),
        ('Negociando', 'Em Negociação'),
        ('Ganhamos', 'Ganhamos'),
        ('Perdemos', 'Perdemos'),
        ('Telefone Inexistente', 'Telefone Inexistente'),
    ]
    place_id = models.CharField(max_length=255, unique=True)
    nome = models.CharField(max_length=255)
    endereco = models.CharField(max_length=300, blank=True, null=True)
    telefone = models.CharField(max_length=30, blank=True, null=True)
    whatsapp = models.CharField(max_length=30, blank=True, null=True)
    site = models.URLField(max_length=255, blank=True, null=True)
    rating = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Qualificado')
    
    proprietarios = models.ManyToManyField(User, related_name='leads_adquiridos')

    def __str__(self): return self.nome

class TemplateMensagem(models.Model):
    """Template de mensagem reutilizável, associável a campanhas."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='templates_mensagem')
    nome = models.CharField(max_length=100)
    texto = models.TextField()
    campanhas = models.ManyToManyField('Campanha', related_name='templates', blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nome']
        unique_together = ('user', 'nome')

    def __str__(self):
        return self.nome


class HistoricoBusca(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='historico_buscas')
    tipo_empresa = models.CharField(max_length=255)
    cidade = models.CharField(max_length=255)
    estado = models.CharField(max_length=2)
    data_busca = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'tipo_empresa', 'cidade', 'estado')
        ordering = ['-data_busca']

    def __str__(self):
        return f'{self.tipo_empresa} em {self.cidade}-{self.estado}'
