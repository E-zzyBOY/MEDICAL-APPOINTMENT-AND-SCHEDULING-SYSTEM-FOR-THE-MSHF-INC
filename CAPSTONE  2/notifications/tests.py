from datetime import date, time, timedelta

from django.core import mail
from django.test import TestCase
from django.contrib.auth import get_user_model

from appointments.models import Appointment
from notifications.email_utils import (
    send_verification_email, send_time_assigned_email, send_password_reset_email,
    send_staff_new_booking_email,
)

User = get_user_model()


class HtmlEmailFormattingTestCase(TestCase):
    """Every outgoing email must carry BOTH the original plain-text body
    (older clients + the tests that regex-parse .body) and a branded HTML
    alternative that highlights the key information."""

    def setUp(self):
        self.patient = User.objects.create_user(
            username='mailpatient', email='mailpatient@test.com',
            password='testpass123', role='patient',
            first_name='Juan', last_name='Dela Cruz')
        self.doctor = User.objects.create_user(
            username='maildoctor', email='maildoctor@test.com',
            password='testpass123', role='doctor', first_name='Ana', last_name='Reyes')
        self.appt = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            appointment_date=date.today() + timedelta(days=1),
            appointment_time=time(10, 0), status='Scheduled', reason='Check-up')

    def _html_part(self, message):
        self.assertEqual(len(message.alternatives), 1)
        html, mimetype = message.alternatives[0]
        self.assertEqual(mimetype, 'text/html')
        return html

    def test_verification_email_has_html_with_code_in_both_parts(self):
        send_verification_email(self.patient, '123456', ttl_minutes=10)
        msg = mail.outbox[0]
        html = self._html_part(msg)
        self.assertIn('123456', msg.body)          # plain-text part intact
        self.assertIn('123456', html)              # highlighted in HTML part
        self.assertIn('MSHFI', html)

    def test_time_assigned_email_has_html_with_appointment_details(self):
        send_time_assigned_email(self.appt)
        msg = mail.outbox[0]
        html = self._html_part(msg)
        expected_date = self.appt.appointment_date.strftime('%B %d, %Y')
        self.assertIn(expected_date, msg.body)
        self.assertIn(expected_date, html)
        self.assertIn('Dr. Ana Reyes', html)

    def test_password_reset_email_still_returns_true_and_has_html(self):
        result = send_password_reset_email(self.patient, 'NewSecret123')
        self.assertTrue(result)
        msg = mail.outbox[0]
        html = self._html_part(msg)
        # The exact string accounts.tests._new_password_from_outbox parses
        # must survive in the text part.
        self.assertIn('New password: NewSecret123', msg.body)
        self.assertIn('NewSecret123', html)

    def test_staff_email_has_html_alternative(self):
        send_staff_new_booking_email(self.appt)
        self.assertGreaterEqual(len(mail.outbox), 1)
        html = self._html_part(mail.outbox[0])
        self.assertIn('Juan Dela Cruz', html)
