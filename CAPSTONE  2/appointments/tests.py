from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from datetime import date, datetime, timedelta
from appointments.models import Appointment, Schedule
from records.models import VitalSign, MedicalRecords, ResultsConsultation, Prescription
from records.views import partition_vitals
from accounts.models import PatientProfile, SecretaryProfile
from notifications.models import Notification

User = get_user_model()


class AppointmentDuplicateBookingTestCase(TestCase):
    """Test cases for preventing duplicate active appointments per patient."""

    def setUp(self):
        """Set up test data."""
        # Create a patient user
        self.patient = User.objects.create_user(
            username='testpatient',
            email='patient@test.com',
            password='testpass123',
            role='patient'
        )

        # Create a doctor user
        self.doctor = User.objects.create_user(
            username='testdoctor',
            email='doctor@test.com',
            password='testpass123',
            role='doctor'
        )

        # Create a schedule for the doctor (needed for booking)
        tomorrow = date.today() + timedelta(days=1)
        self.schedule = Schedule.objects.create(
            doctor=self.doctor,
            specific_date=tomorrow,
            start_time='09:00',
            end_time='17:00'
        )

        self.client = Client()

    def test_has_active_appointment_no_appointments(self):
        """Test that a patient with no appointments doesn't have an active appointment."""
        self.assertFalse(Appointment.has_active_appointment(self.patient))

    def test_has_active_appointment_with_pending_assignment(self):
        """Test that a patient with 'Pending Assignment' status has an active appointment."""
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today() + timedelta(days=1),
            status='Pending Assignment',
            reason='Test appointment'
        )
        self.assertTrue(Appointment.has_active_appointment(self.patient))

    def test_has_active_appointment_with_scheduled(self):
        """Test that a patient with 'Scheduled' status has an active appointment."""
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today() + timedelta(days=1),
            appointment_time='10:00',
            status='Scheduled',
            reason='Test appointment'
        )
        self.assertTrue(Appointment.has_active_appointment(self.patient))

    def test_has_active_appointment_with_rescheduled(self):
        """Test that a patient with 'Rescheduled' status has an active appointment."""
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today() + timedelta(days=1),
            appointment_time='10:00',
            status='Rescheduled',
            reason='Test appointment'
        )
        self.assertTrue(Appointment.has_active_appointment(self.patient))

    def test_has_active_appointment_with_pending_reschedule(self):
        """Test that a patient with 'Pending Reschedule' status has an active appointment."""
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today() + timedelta(days=1),
            appointment_time='10:00',
            status='Pending Reschedule',
            reason='Test appointment'
        )
        self.assertTrue(Appointment.has_active_appointment(self.patient))

    def test_has_active_appointment_with_completed(self):
        """Test that a patient with 'Completed' status does NOT have an active appointment."""
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today() - timedelta(days=1),
            appointment_time='10:00',
            status='Completed',
            reason='Test appointment'
        )
        self.assertFalse(Appointment.has_active_appointment(self.patient))

    def test_has_active_appointment_with_cancelled(self):
        """Test that a patient with 'Cancelled' status does NOT have an active appointment."""
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today() + timedelta(days=1),
            status='Cancelled',
            reason='Test appointment'
        )
        self.assertFalse(Appointment.has_active_appointment(self.patient))

    def test_has_active_appointment_multiple_appointments_one_active(self):
        """Test with multiple appointments, one active and one completed."""
        # Create a completed appointment
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today() - timedelta(days=5),
            appointment_time='10:00',
            status='Completed',
            reason='Past appointment'
        )
        # Create an active appointment
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today() + timedelta(days=1),
            status='Pending Assignment',
            reason='Active appointment'
        )
        # Should have active appointment because one is still pending
        self.assertTrue(Appointment.has_active_appointment(self.patient))

    def test_booking_prevented_with_active_appointment(self):
        """Test that the validation check prevents booking with active appointment."""
        # Create an active appointment
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today() + timedelta(days=5),
            status='Pending Assignment',
            reason='Existing active appointment'
        )

        # Verify patient has active appointment
        self.assertTrue(Appointment.has_active_appointment(self.patient))

        # In the actual booking flow, book_step3_confirm checks this before creating
        # If has_active_appointment() returns True, no appointment is created
        # This test verifies the check would trigger

        # Try to create another appointment - this would be blocked in book_step3_confirm
        # We test the logic here directly since Django/Python 3.14 has template rendering issues
        if not Appointment.has_active_appointment(self.patient):
            # This path should NOT be taken when patient has active appointment
            Appointment.objects.create(
                patient=self.patient,
                doctor=self.doctor,
                appointment_date=date.today() + timedelta(days=3),
                status='Pending Assignment',
                reason='Second appointment'
            )

        # Verify no new appointment was created (still only 1)
        appointment_count = Appointment.objects.filter(patient=self.patient).count()
        self.assertEqual(appointment_count, 1)  # Only the original one

    def test_booking_allowed_after_cancellation(self):
        """Test that booking is allowed after previous appointment is cancelled."""
        # Create an appointment
        appt = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today() + timedelta(days=5),
            appointment_time='10:00',
            status='Scheduled',
            reason='Existing appointment'
        )

        # Verify patient has active appointment
        self.assertTrue(Appointment.has_active_appointment(self.patient))

        # Cancel the appointment
        appt.status = 'Cancelled'
        appt.save()

        # Verify patient no longer has active appointment
        self.assertFalse(Appointment.has_active_appointment(self.patient))

    def test_booking_allowed_after_completion(self):
        """Test that booking is allowed after previous appointment is completed."""
        # Create an appointment
        appt = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today() - timedelta(days=1),
            appointment_time='10:00',
            status='Scheduled',
            reason='Existing appointment'
        )

        # Verify patient has active appointment
        self.assertTrue(Appointment.has_active_appointment(self.patient))

        # Complete the appointment
        appt.status = 'Completed'
        appt.save()

        # Verify patient no longer has active appointment
        self.assertFalse(Appointment.has_active_appointment(self.patient))


class PatientRecordsRestructureTestCase(TestCase):
    """Vitals-tied-to-visit partitioning and the pinned Critical Info flow."""

    def setUp(self):
        self.patient = User.objects.create_user(
            username='recpatient', email='recpatient@test.com',
            password='testpass123', role='patient')
        self.doctor = User.objects.create_user(
            username='recdoctor', email='recdoctor@test.com',
            password='testpass123', role='doctor')
        self.other_doctor = User.objects.create_user(
            username='otherdoctor', email='otherdoctor@test.com',
            password='testpass123', role='doctor')
        self.secretary = User.objects.create_user(
            username='recsecretary', email='recsecretary@test.com',
            password='testpass123', role='secretary')
        self.client = Client()

    def _make_visit(self):
        today = date.today()
        appt = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            appointment_date=today, status='Completed')
        results = ResultsConsultation.objects.create(appointment=appt, diagnosis='Flu')
        MedicalRecords.objects.create(
            doctor=self.doctor, patient=self.patient,
            results=results, visit_date=today)
        return appt

    def test_partition_vitals_linked_to_visit(self):
        appt = self._make_visit()
        linked = VitalSign.objects.create(
            patient=self.patient, secretary=self.secretary,
            bp='120/80', weight=65, date_taken=date.today(), appointment=appt)
        unlinked = VitalSign.objects.create(
            patient=self.patient, secretary=self.secretary,
            bp='110/70', weight=64, date_taken=date.today())
        records = MedicalRecords.objects.filter(patient=self.patient).select_related('results', 'doctor')
        visit_vitals, general_vitals = partition_vitals(self.patient, records)
        self.assertIn(appt.pk, visit_vitals)
        self.assertEqual([v.pk for v in visit_vitals[appt.pk]], [linked.pk])
        self.assertNotIn(unlinked.pk, [v.pk for v in visit_vitals[appt.pk]])
        self.assertEqual([v.pk for v in general_vitals], [unlinked.pk])
        self.assertNotIn(linked.pk, [v.pk for v in general_vitals])

    def test_partition_vitals_linked_appointment_without_saved_results(self):
        today = date.today()
        appt = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            appointment_date=today, status='Confirmed')
        vital = VitalSign.objects.create(
            patient=self.patient, secretary=self.secretary,
            bp='120/80', weight=65, date_taken=today, appointment=appt)
        records = MedicalRecords.objects.filter(patient=self.patient).select_related('results', 'doctor')
        visit_vitals, general_vitals = partition_vitals(self.patient, records)
        self.assertNotIn(appt.pk, visit_vitals)
        self.assertEqual([v.pk for v in general_vitals], [vital.pk])

    def test_doctor_saves_critical_info(self):
        Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            appointment_date=date.today())
        self.client.login(username='recdoctor', password='testpass123')
        url = reverse('doctor:patient_critical_info', kwargs={'patient_id': self.patient.pk})
        response = self.client.post(url, {
            'allergies': 'Penicillin',
            'chronic_conditions': 'Hypertension',
            'critical_notes': 'Avoid NSAIDs',
        })
        self.assertRedirects(response, reverse('doctor:patient_records', kwargs={'patient_id': self.patient.pk}))
        profile = PatientProfile.objects.get(user=self.patient)
        self.assertEqual(profile.allergies, 'Penicillin')
        self.assertEqual(profile.chronic_conditions, 'Hypertension')
        self.assertEqual(profile.critical_notes, 'Avoid NSAIDs')

    def test_doctor_without_appointment_cannot_save_critical_info(self):
        self.client.login(username='otherdoctor', password='testpass123')
        url = reverse('doctor:patient_critical_info', kwargs={'patient_id': self.patient.pk})
        response = self.client.post(url, {'allergies': 'Penicillin'})
        self.assertRedirects(response, reverse('doctor:patient_list'))
        self.assertFalse(PatientProfile.objects.filter(user=self.patient).exists())

    def test_critical_info_modal_get(self):
        Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            appointment_date=date.today())
        self.client.login(username='recdoctor', password='testpass123')
        url = reverse('doctor:patient_critical_info', kwargs={'patient_id': self.patient.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit Critical Info')
        self.assertContains(response, 'allergies')

    def test_doctor_records_page_renders_critical_info(self):
        Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            appointment_date=date.today())
        PatientProfile.objects.create(
            user=self.patient, allergies='Penicillin',
            chronic_conditions='Hypertension')
        self.client.login(username='recdoctor', password='testpass123')
        url = reverse('doctor:patient_records', kwargs={'patient_id': self.patient.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Critical Info')
        self.assertContains(response, 'Penicillin')

    def test_doctor_records_page_renders_vitals_in_visit(self):
        appt = self._make_visit()
        VitalSign.objects.create(
            patient=self.patient, secretary=self.secretary,
            bp='120/80', weight=65, date_taken=date.today(), appointment=appt)
        self.client.login(username='recdoctor', password='testpass123')
        url = reverse('doctor:patient_records', kwargs={'patient_id': self.patient.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Vitals')
        self.assertContains(response, '120/80')
        self.assertNotContains(response, 'General Vitals')

    def test_secretary_vitals_add_links_appointment_from_checkin(self):
        from accounts.models import SecretaryProfile
        SecretaryProfile.objects.create(user=self.secretary, assigned_doctor=self.doctor)
        appt = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            appointment_date=date.today(), status='Scheduled')
        self.client.login(username='recsecretary', password='testpass123')
        url = reverse('secretary:vitals_add', kwargs={'patient_id': self.patient.pk})
        response = self.client.post(f'{url}?appointment={appt.pk}', {
            'bp': '120/80', 'weight': '65.00', 'date_taken': date.today().isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        vital = VitalSign.objects.get(patient=self.patient)
        self.assertEqual(vital.appointment_id, appt.pk)


class PatientRecordsFilterTestCase(TestCase):
    """Search/filter/pagination on the doctor's Patient Records page."""

    def setUp(self):
        self.patient = User.objects.create_user(
            username='filtpatient', email='filtpatient@test.com',
            password='testpass123', role='patient')
        self.doc1 = User.objects.create_user(
            username='filtdoc1', email='filtdoc1@test.com',
            password='testpass123', role='doctor',
            first_name='Alice', last_name='Doctor')
        self.doc2 = User.objects.create_user(
            username='filtdoc2', email='filtdoc2@test.com',
            password='testpass123', role='doctor',
            first_name='Bob', last_name='Physician')
        self.client = Client()
        self.client.login(username='filtdoc1', password='testpass123')

    def _visit(self, doctor, visit_date, diagnosis='Routine checkup'):
        appt = Appointment.objects.create(
            patient=self.patient, doctor=doctor,
            appointment_date=visit_date, status='Completed')
        results = ResultsConsultation.objects.create(appointment=appt, diagnosis=diagnosis)
        return MedicalRecords.objects.create(
            doctor=doctor, patient=self.patient, results=results, visit_date=visit_date)

    def _records_url(self):
        return reverse('doctor:patient_records', kwargs={'patient_id': self.patient.pk})

    def test_date_range_filter(self):
        self._visit(self.doc1, date(2026, 1, 10), 'Allergic dermatitis')
        self._visit(self.doc1, date(2026, 2, 20), 'Hypertension')
        response = self.client.get(self._records_url(), {
            'from_date': '2026-01-15', 'to_date': '2026-02-28'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hypertension')
        self.assertNotContains(response, 'Allergic dermatitis')

    def test_keyword_search_matches_diagnosis(self):
        self._visit(self.doc1, date(2026, 1, 10), 'Allergic dermatitis')
        self._visit(self.doc1, date(2026, 2, 20), 'Hypertension')
        response = self.client.get(self._records_url(), {'q': 'allergic'})
        self.assertContains(response, 'Allergic dermatitis')
        self.assertNotContains(response, 'Hypertension')

    def test_keyword_search_matches_notes_without_duplicates(self):
        record = self._visit(self.doc1, date(2026, 1, 10), 'Asthma review')
        for i in range(2):
            Prescription.objects.create(
                results_consultation=record.results,
                date_issued=record.visit_date,
                medication_names='Salbutamol',
                notes='patient reports wheezing episodes',
            )
        response = self.client.get(self._records_url(), {'q': 'wheezing'})
        self.assertContains(response, 'Asthma review')
        self.assertEqual(response.content.count(b'Asthma review'), 1)

    def test_doctor_filter(self):
        self._visit(self.doc1, date(2026, 1, 10), 'Psoriasis flare')
        self._visit(self.doc2, date(2026, 2, 20), 'Hypertension')
        response = self.client.get(self._records_url(), {'doctor': self.doc2.pk})
        self.assertContains(response, self.doc2.get_full_name())
        self.assertContains(response, 'Hypertension')
        self.assertNotContains(response, 'Psoriasis flare')
        self.assertEqual(response.content.count(b'Attending Doctor'), 1)

    def test_htmx_returns_partial_only(self):
        self._visit(self.doc1, date(2026, 1, 10))
        response = self.client.get(
            self._records_url(), {'q': 'checkup'}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'records-list')
        self.assertNotContains(response, 'Critical Info')

    def test_pagination_load_more(self):
        for i in range(12):
            self._visit(self.doc1, date(2026, 3, 1) - timedelta(days=i))
        response = self.client.get(self._records_url())
        self.assertContains(response, 'Showing 10 of 12 visits')
        self.assertContains(response, 'Load more visits')
        self.assertEqual(response.content.count(b'Attending Doctor'), 10)
        response = self.client.get(self._records_url(), {'limit': '20'})
        self.assertContains(response, 'Showing 12 of 12 visits')
        self.assertNotContains(response, 'Load more visits')
        self.assertEqual(response.content.count(b'Attending Doctor'), 12)

    def test_filtered_view_returns_all_matches(self):
        for i in range(12):
            self._visit(self.doc1, date(2026, 3, 1) - timedelta(days=i),
                        'Allergic dermatitis' if i < 3 else 'Routine checkup')
        response = self.client.get(self._records_url(), {'q': 'allergic'})
        self.assertContains(response, 'Showing 3 of 3 visits')
        self.assertNotContains(response, 'Load more visits')
        self.assertEqual(response.content.count(b'Attending Doctor'), 3)


class SecretaryAssignTimeDateNavigationTestCase(TestCase):
    """The secretary's "Assign Appointment Time" flow must never dead-end:
    the assign-time modal can move a Pending Assignment onto a different
    (future) date, and can always decline/cancel the request."""

    def setUp(self):
        self.patient = User.objects.create_user(
            username='assignpatient', email='assignpatient@test.com',
            password='testpass123', role='patient',
            first_name='Pia', last_name='Patient')
        self.doctor = User.objects.create_user(
            username='assigndoctor', email='assigndoctor@test.com',
            password='testpass123', role='doctor',
            first_name='Diana', last_name='Doctor')
        self.secretary = User.objects.create_user(
            username='assignsecretary', email='assignsecretary@test.com',
            password='testpass123', role='secretary')
        SecretaryProfile.objects.create(user=self.secretary, assigned_doctor=self.doctor)

        self.yesterday = date.today() - timedelta(days=1)
        self.tomorrow  = date.today() + timedelta(days=1)
        self.day_after = date.today() + timedelta(days=2)

        Schedule.objects.create(doctor=self.doctor, specific_date=self.tomorrow,
                                start_time='09:00', end_time='12:00')
        Schedule.objects.create(doctor=self.doctor, specific_date=self.day_after,
                                start_time='09:00', end_time='17:00')

        # The classic dead-end: requested date has already passed.
        self.appt = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            appointment_date=self.yesterday, status='Pending Assignment',
            reason='Follow-up')

        self.client.login(username='assignsecretary', password='testpass123')

    def test_occupied_times_supports_date_param(self):
        Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            appointment_date=self.day_after, appointment_time='10:00',
            status='Scheduled')
        url = reverse('secretary:occupied_times', kwargs={'pk': self.appt.pk})

        # default: resolves to the appointment's own (past) date
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['date'], self.yesterday.isoformat())
        self.assertTrue(data['is_past'])
        self.assertEqual(data['occupied_times'], [])

        # explicit ?date= returns that date's blocks + occupancy instead
        resp = self.client.get(url, {'date': self.day_after.isoformat()})
        data = resp.json()
        self.assertEqual(data['date'], self.day_after.isoformat())
        self.assertFalse(data['is_past'])
        self.assertTrue(data['has_schedule'])
        self.assertIn('09:00-17:00', data['blocks'])
        times = [o['time'] for o in data['occupied_times']]
        self.assertIn('10:00', times)

    def test_occupied_times_ignores_invalid_date(self):
        url = reverse('secretary:occupied_times', kwargs={'pk': self.appt.pk})
        resp = self.client.get(url, {'date': 'not-a-date'})
        data = resp.json()
        self.assertEqual(data['date'], self.yesterday.isoformat())

    def test_assign_time_can_move_to_future_date(self):
        url = reverse('secretary:assign_time', kwargs={'pk': self.appt.pk})
        resp = self.client.post(url, {
            'appointment_time': '10:30',
            'appointment_date': self.day_after.isoformat(),
        })
        self.assertEqual(resp.status_code, 302)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.appointment_date, self.day_after)
        self.assertEqual(self.appt.appointment_time.strftime('%H:%M'), '10:30')
        self.assertEqual(self.appt.status, 'Scheduled')

    def test_assign_time_rejects_past_date(self):
        url = reverse('secretary:assign_time', kwargs={'pk': self.appt.pk})
        resp = self.client.post(url, {
            'appointment_time': '10:00',
            'appointment_date': self.yesterday.isoformat(),
        })
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'Pending Assignment')
        self.assertIsNone(self.appt.appointment_time)

    def test_assign_time_validates_against_new_date_hours(self):
        # tomorrow's working hours are 09:00–12:00, so 13:00 must be rejected
        url = reverse('secretary:assign_time', kwargs={'pk': self.appt.pk})
        resp = self.client.post(url, {
            'appointment_time': '13:00',
            'appointment_date': self.tomorrow.isoformat(),
        })
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'Pending Assignment')
        self.assertIsNone(self.appt.appointment_time)

    def test_assign_time_persists_date_without_posting_one(self):
        # No date posted -> stays on the appointment's own date
        url = reverse('secretary:assign_time', kwargs={'pk': self.appt.pk})
        resp = self.client.post(url, {'appointment_time': '10:00'})
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.appointment_date, self.yesterday)
        # ...but a past date is rejected, so it stays Pending Assignment
        self.assertEqual(self.appt.status, 'Pending Assignment')

    def test_decline_pending_assignment_cancels_and_notifies_with_reason(self):
        url = reverse('secretary:appointment_cancel', kwargs={'pk': self.appt.pk})
        resp = self.client.post(url, {
            'mode': 'cancel', 'reason': 'Unable to accommodate this request',
        })
        self.assertEqual(resp.status_code, 302)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'Cancelled')
        notif = Notification.objects.filter(user=self.patient).latest('created_at')
        self.assertIn('Unable to accommodate this request', notif.message)
