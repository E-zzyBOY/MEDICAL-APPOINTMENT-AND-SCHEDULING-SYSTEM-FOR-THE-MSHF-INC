from datetime import date
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from appointments.models import Appointment
from records.models import Prescription, ResultsConsultation

User = get_user_model()


class PrescriptionAttachmentAccessTestCase(TestCase):
    """A prescription attachment is viewable by any doctor who has had an
    appointment with the patient, not just the doctor who uploaded it —
    matching the access rule used by the doctor's patient-records page."""

    def setUp(self):
        self.patient = User.objects.create_user(
            username='patient', email='patient@test.com', password='pass12345', role='patient'
        )
        self.uploader = User.objects.create_user(
            username='doc_a', email='doca@test.com', password='pass12345', role='doctor'
        )
        self.attending = User.objects.create_user(
            username='doc_b', email='docb@test.com', password='pass12345', role='doctor'
        )
        self.stranger = User.objects.create_user(
            username='doc_c', email='docc@test.com', password='pass12345', role='doctor'
        )
        self.secretary = User.objects.create_user(
            username='secretary', email='sec@test.com', password='pass12345', role='secretary'
        )

        appt = Appointment.objects.create(
            patient=self.patient, doctor=self.uploader,
            appointment_date=date.today(), status='Completed'
        )
        self.results = ResultsConsultation.objects.create(
            appointment=appt, diagnosis='Test diagnosis'
        )

        # Attending doctor B also has an appointment with this patient.
        Appointment.objects.create(
            patient=self.patient, doctor=self.attending,
            appointment_date=date.today(), status='Completed'
        )

        self.rx = Prescription.objects.create(
            results_consultation=self.results,
            date_issued=date.today(),
            medication_names='Paracetamol 500mg',
            attachment=SimpleUploadedFile(
                'result.jpg', b'\xff\xd8\xff\xe0 fake jpeg bytes', content_type='image/jpeg'
            ),
        )
        self.rx_no_attachment = Prescription.objects.create(
            results_consultation=self.results,
            date_issued=date.today(),
            medication_names='Amoxicillin 500mg',
        )
        self.url = reverse('records:prescription_attachment', args=[self.rx.pk])
        self.client = Client()

    def test_uploading_doctor_can_view(self):
        self.client.force_login(self.uploader)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_any_attending_doctor_can_view(self):
        self.client.force_login(self.attending)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_doctor_without_appointment_gets_404(self):
        self.client.force_login(self.stranger)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 404)

    def test_missing_attachment_returns_404_even_for_authorized_doctor(self):
        self.client.force_login(self.uploader)
        resp = self.client.get(reverse('records:prescription_attachment', args=[self.rx_no_attachment.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_secretary_cannot_view(self):
        self.client.force_login(self.secretary)
        resp = self.client.get(self.url)
        self.assertNotEqual(resp.status_code, 200)
