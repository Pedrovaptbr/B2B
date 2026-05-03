from django.core.management.base import BaseCommand
from django.db import transaction
from leads.models import Lead

class Command(BaseCommand):
    help = 'Apaga permanentemente todos os leads do banco de dados.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('ATENÇÃO: Este comando apagará permanentemente TODOS os leads.'))
        
        confirm = input('Você tem certeza que quer continuar? [s/N]: ')
        
        if confirm.lower() != 's':
            self.stdout.write(self.style.ERROR('Operação cancelada.'))
            return

        try:
            with transaction.atomic():
                total_leads = Lead.objects.count()
                if total_leads == 0:
                    self.stdout.write(self.style.SUCCESS('Nenhum lead para apagar.'))
                    return

                # Desvincula os leads de todas as campanhas antes de apagar
                for lead in Lead.objects.all():
                    lead.campanhas.clear()

                # Apaga todos os leads
                deleted_count, _ = Lead.objects.all().delete()
                
                self.stdout.write(self.style.SUCCESS(f'{deleted_count} leads foram apagados com sucesso.'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ocorreu um erro: {e}'))
            self.stdout.write(self.style.ERROR('A operação foi revertida.'))
