from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0002_alter_lead_status_delete_statuspersonalizado'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TemplateMensagem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=100)),
                ('texto', models.TextField()),
                ('data_criacao', models.DateTimeField(auto_now_add=True)),
                ('campanhas', models.ManyToManyField(blank=True, related_name='templates', to='leads.campanha')),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='templates_mensagem',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['nome'],
                'unique_together': {('user', 'nome')},
            },
        ),
    ]
