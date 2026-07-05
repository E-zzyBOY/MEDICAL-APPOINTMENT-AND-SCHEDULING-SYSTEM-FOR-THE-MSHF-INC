import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from appointments.models import Appointment, Schedule, AppointmentPatientDetails
from records.models import VitalSign, ResultsConsultation, Prescription, MedicalRecords
from accounts.models import PatientProfile, DoctorProfile, SecretaryProfile
from notifications.models import Notification
from feedback.models import Feedback

CustomUser = get_user_model()


class Command(BaseCommand):
    help = 'Clear all records and keep only admin account'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm database reset (required)',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(self.style.ERROR(
                '[!] WARNING: This will DELETE ALL RECORDS and USERS (except admin)!\n'
                '    To proceed, run: python manage.py reset_db --confirm'
            ))
            return

        self.stdout.write(self.style.WARNING('Starting database reset...'))

        # Delete all records from all models
        self.stdout.write('Deleting appointments...')
        Appointment.objects.all().delete()
        AppointmentPatientDetails.objects.all().delete()

        self.stdout.write('Deleting schedules...')
        Schedule.objects.all().delete()

        self.stdout.write('Deleting vital signs...')
        VitalSign.objects.all().delete()

        self.stdout.write('Deleting prescriptions and consultation results...')
        Prescription.objects.all().delete()
        ResultsConsultation.objects.all().delete()

        self.stdout.write('Deleting medical records...')
        MedicalRecords.objects.all().delete()

        self.stdout.write('Deleting notifications...')
        Notification.objects.all().delete()

        self.stdout.write('Deleting feedback...')
        Feedback.objects.all().delete()

        self.stdout.write('Deleting user profiles...')
        PatientProfile.objects.all().delete()
        DoctorProfile.objects.all().delete()
        SecretaryProfile.objects.all().delete()

        self.stdout.write('Deleting all users except admin...')
        # Keep only the admin user
        admin_user = CustomUser.objects.filter(username='ADMIN2026').first()

        # Delete all other users
        CustomUser.objects.exclude(username='ADMIN2026').delete()

        self.stdout.write(self.style.SUCCESS('All records deleted.'))

        # Create or update admin user
        self.stdout.write('Setting up admin account...')

        admin_password = os.environ.get('ADMIN_PASSWORD', '@dmin2026')

        admin, created = CustomUser.objects.get_or_create(
            username='ADMIN2026',
            defaults={
                'email': 'admin@mshfi.com',
                'first_name': 'Admin',
                'last_name': 'User',
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True,
            }
        )

        admin.set_password(admin_password)
        admin.save()

        if created:
            self.stdout.write(self.style.SUCCESS('[+] Admin account created successfully'))
        else:
            self.stdout.write(self.style.SUCCESS('[+] Admin account updated successfully'))

        self.stdout.write(self.style.SUCCESS('\n[+] Database reset complete!'))
        self.stdout.write(self.style.WARNING('\n[!] Store admin password in ADMIN_PASSWORD environment variable for security.'))
