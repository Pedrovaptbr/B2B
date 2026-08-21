from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class PerfilUsuario(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    creditos_disponiveis = models.IntegerField(default=1)
    total_extraido = models.IntegerField(default=0)
    plano_ativo = models.BooleanField(default=False)

    # ── Stripe ────────────────────────────────────────────────────────────────
    stripe_customer_id     = models.CharField(max_length=100, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True, null=True)

    # ── IA (geração/variação de mensagens) ─────────────────────────────────────
    ia_geracoes_usadas_mes = models.IntegerField(default=0)
    ia_mes_referencia = models.CharField(max_length=7, blank=True, null=True)  # "YYYY-MM"
    contexto_negocio = models.TextField(
        blank=True,
        null=True,
        help_text="Breve descrição do negócio do usuário, usada como contexto para a IA gerar mensagens."
    )

    def __str__(self):
        return f"Perfil de {self.user.username}"

    @property
    def total_leads_adquiridos(self):
        return self.user.leads_adquiridos.count()

    def _resetar_ia_se_novo_mes(self):
        from django.utils import timezone
        mes_atual = timezone.localdate().strftime('%Y-%m')
        if self.ia_mes_referencia != mes_atual:
            self.ia_mes_referencia = mes_atual
            self.ia_geracoes_usadas_mes = 0

    def ia_geracoes_restantes(self):
        from django.conf import settings
        self._resetar_ia_se_novo_mes()
        limite = getattr(settings, 'LIMITE_IA_GERACOES_MES', 50)
        return max(0, limite - self.ia_geracoes_usadas_mes)

    def pode_usar_ia(self):
        return self.ia_geracoes_restantes() > 0

    def consumir_ia(self):
        """Incrementa o contador de gerações de IA do mês e persiste. Chamar só após sucesso da chamada à IA."""
        self._resetar_ia_se_novo_mes()
        self.ia_geracoes_usadas_mes += 1
        self.save(update_fields=['ia_geracoes_usadas_mes', 'ia_mes_referencia'])

@receiver(post_save, sender=User)
def criar_ou_atualizar_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        PerfilUsuario.objects.create(user=instance)

class WhatsappInstance(models.Model):
    STATUS_CHOICES = [('DISCONNECTED', 'Desconectado'), ('CONNECTING', 'Conectando'), ('CONNECTED', 'Conectado')]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='whatsapp_instance')
    instance_name = models.CharField(max_length=100, unique=True)
    instance_token = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DISCONNECTED')
    qr_code_base64 = models.TextField(blank=True, null=True)

    # ── Limite diário de envios (anti-bloqueio do número) ──────────────────────
    limite_diario_envios = models.IntegerField(default=40)
    envios_hoje = models.IntegerField(default=0)
    envios_data = models.DateField(null=True, blank=True)
    enviando_campanha = models.BooleanField(default=False)
    disparo_iniciado_em = models.DateTimeField(null=True, blank=True)
    cancelar_disparo = models.BooleanField(default=False)

    def __str__(self): return f"Instância de {self.user.username}"

    def _resetar_contador_se_novo_dia(self):
        from django.utils import timezone
        hoje = timezone.localdate()
        if self.envios_data != hoje:
            self.envios_data = hoje
            self.envios_hoje = 0

    def envios_restantes_hoje(self):
        self._resetar_contador_se_novo_dia()
        return max(0, self.limite_diario_envios - self.envios_hoje)

    def registrar_envio(self):
        """Incrementa o contador de envios do dia e persiste."""
        self._resetar_contador_se_novo_dia()
        self.envios_hoje += 1
        self.save(update_fields=['envios_hoje', 'envios_data'])
