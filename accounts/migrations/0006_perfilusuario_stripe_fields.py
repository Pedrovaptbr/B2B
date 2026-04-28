from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_add_creditos_plano_perfil'),
    ]

    operations = [
        migrations.AddField(
            model_name='perfilusuario',
            name='stripe_customer_id',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='perfilusuario',
            name='stripe_subscription_id',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
