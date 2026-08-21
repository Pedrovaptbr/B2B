from django.db import models
from django.contrib.auth.models import User

class ConfiguracaoDisparo(models.Model):
    """
    Trava global (singleton) que o admin pode ligar a qualquer momento para
    impedir novos disparos de campanha em toda a plataforma — ex: enquanto
    se investiga um bloqueio em massa pelo WhatsApp/Meta.
    """
    bloqueado = models.BooleanField(
        default=False,
        help_text="Se marcado, nenhum usuário consegue iniciar disparos de campanha."
    )
    mensagem_bloqueio = models.TextField(
        default="Disparos de campanha temporariamente pausados para manutenção do sistema. Tente novamente mais tarde.",
        help_text="Mensagem exibida ao usuário quando ele tentar disparar uma campanha com a trava ativa."
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração de Disparo'
        verbose_name_plural = 'Configuração de Disparo'

    def __str__(self):
        return 'Disparos bloqueados' if self.bloqueado else 'Disparos liberados'

    @classmethod
    def atual(cls):
        """Retorna (criando se necessário) a única instância desta configuração."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


class ConfiguracaoIA(models.Model):
    """
    Prompts de sistema (singleton) usados nas chamadas à IA local (Ollama)
    para gerar mensagem de campanha e variações. Editáveis pelo admin sem
    precisar de deploy, para ajustar tom/regras conforme a IA "aprende"
    (ou erra) na prática.
    """
    prompt_mensagem_base = models.TextField(
        default=(
            "Você escreve mensagens curtas de prospecção B2B via WhatsApp em português do Brasil, "
            "como se fosse uma pessoa real mandando um WhatsApp pra outra — nunca uma carta ou e-mail. "
            "Regras rígidas: no máximo 4 frases curtas no total. Tom direto e natural, sem clichês de "
            "vendas nem floreios poéticos. Sem emojis em excesso. "
            "NUNCA termine com saudação de despedida ou assinatura — nada de 'Atenciosamente', 'Att', "
            "'Cordialmente', 'Abraços' ou '[Seu Nome]' no final; a mensagem termina na última frase útil. "
            "Use o placeholder literal [nome] onde o nome do lead deve entrar — só esse, "
            "nenhum outro placeholder entre colchetes (nunca invente algo como '[número]', "
            "'[telefone]', '[link]', '[endereço]'; se faltar uma informação, não a mencione). "
            "Não invente NENHUM dado que não esteja explicitamente no contexto do negócio "
            "fornecido — nada de tempo de experiência ('há X anos', 'desde X anos'), número de "
            "telefone, canais de atendimento (chat, visita presencial, loja física) ou qualquer "
            "outro detalhe que o usuário não tenha informado. "
            "Também não reformule nem exagere um fato do contexto de um jeito que mude o "
            "significado dele — por exemplo, se o contexto diz 'receita tradicional italiana', "
            "NÃO escreva que o produto 'vem da Itália' ou é 'importado'; mantenha o fato exatamente "
            "como foi descrito, só reescrevendo o estilo da frase. "
            "O contexto do negócio pode não incluir um nome de empresa — NUNCA tente se "
            "apresentar como 'sou da [empresa]' ou 'somos a [empresa]' se nenhum nome foi "
            "dado; fale direto sobre o que o negócio faz/vende, sem se apresentar por nome. "
            "Não inclua hashtags. Não invente preços ou links. "
            "Responda só com a mensagem, sem explicações, sem aspas ao redor do texto."
        ),
        help_text="Instrução de sistema usada ao gerar uma mensagem de campanha do zero (botão 'Gerar com IA')."
    )
    prompt_variacoes = models.TextField(
        default=(
            "Você gera variações curtas de uma frase ou mensagem em português do Brasil, para um "
            "sistema de spintax de WhatsApp. As variações devem ter o MESMO sentido e função do "
            "original, só mudando o texto/tom, para que as mensagens não pareçam repetidas — sempre "
            "como se fosse uma mensagem de WhatsApp real, nunca uma carta ou e-mail. "
            "Se o trecho original for uma saudação de ABERTURA (como 'Olá', 'Oi', 'Bom dia', 'Boa "
            "tarde'), as variações devem ser OUTRAS saudações de abertura equivalentes — nunca "
            "despedida ('Tchau', 'Até logo', 'Falou') nem qualquer encerramento. "
            "Nenhuma variação deve terminar com despedida ou assinatura formal (nada de "
            "'Atenciosamente', 'Att', 'Cordialmente', 'Abraços', '[Seu Nome]'). "
            "Não invente nenhum placeholder novo entre colchetes nem nenhum dado (telefone, anos de "
            "experiência, canais de atendimento) que não esteja no trecho original. Também não "
            "exagere nem reformule um fato de um jeito que mude o significado dele (ex: 'receita "
            "tradicional italiana' não pode virar 'vem da Itália' ou 'importado'). "
            "Preserve exatamente qualquer placeholder entre colchetes, como [nome], se aparecer no trecho. "
            "Responda só com as variações, uma por linha, sem numeração, sem aspas, sem explicações."
        ),
        help_text="Instrução de sistema usada ao gerar variações de mensagem (manual, ou automática no disparo)."
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração de IA'
        verbose_name_plural = 'Configuração de IA'

    def __str__(self):
        return 'Prompts da IA'

    @classmethod
    def atual(cls):
        """Retorna (criando se necessário) a única instância desta configuração."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


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
    hashtags_finais = models.TextField(
        blank=True,
        null=True,
        help_text="Opções de hashtag para adicionar ao final da mensagem, uma por linha. Uma delas é escolhida aleatoriamente a cada envio."
    )

    @property
    def hashtags_finais_lista(self):
        if not self.hashtags_finais:
            return []
        return [linha.strip() for linha in self.hashtags_finais.splitlines() if linha.strip()]

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
