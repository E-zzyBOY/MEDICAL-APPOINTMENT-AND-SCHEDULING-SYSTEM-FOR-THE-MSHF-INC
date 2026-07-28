from django.core.management.base import BaseCommand
from datetime import date, timedelta
from appointments.models import Appointment
from notifications.email_utils import send_reminder_email, send_staff_reminder_email, _staff_recipients
from notifications.models import Notification


class Command(BaseCommand):
    help = 'Send day-before appointment reminders to patients, doctors, and their assigned secretaries'

    def handle(self, *args, **options):
        tomorrow = date.today() + timedelta(days=1)
        appointments = Appointment.objects.filter(
            appointment_date=tomorrow,
            status__in=['Scheduled', 'Rescheduled']
        ).select_related('patient', 'doctor')

        count = 0
        for appt in appointments:
            time_str = appt.appointment_time.strftime('%I:%M %p')

            try:
                send_reminder_email(appt)
            except Exception as e:
                self.stderr.write(f'Patient email failed for appt #{appt.pk}: {e}')
            Notification.objects.create(
                user=appt.patient,
                message=(
                    f"Reminder: You have an appointment with Dr. {appt.doctor.get_full_name()} "
                    f"tomorrow at {time_str}."
                )
            )

            try:
                send_staff_reminder_email(appt)
            except Exception as e:
                self.stderr.write(f'Staff email failed for appt #{appt.pk}: {e}')
            staff_message = (
                f"Reminder: {appt.patient.get_full_name()} has an appointment with "
                f"Dr. {appt.doctor.get_full_name()} tomorrow at {time_str}."
            )
            for staff_user in _staff_recipients(appt.doctor):
                Notification.objects.create(user=staff_user, message=staff_message)

            count += 1
            self.stdout.write(f'  Reminder sent for appointment #{appt.pk} — {appt.patient.get_full_name()}')

        self.stdout.write(self.style.SUCCESS(f'Done. Sent {count} reminder(s) for {tomorrow}.'))
