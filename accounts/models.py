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

    def __str__(self):
        return f"Perfil de {self.user.username}"

    @property
    def total_leads_adquiridos(self):
        return self.user.leads_adquiridos.count()

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
