from django.db import models
from django.conf import settings


class Schedule(models.Model):
    doctor         = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='schedules', limit_choices_to={'role': 'doctor'}
    )
    specific_date  = models.DateField()
    start_time     = models.TimeField()
    end_time       = models.TimeField()

    class Meta:
        unique_together = ('doctor', 'specific_date', 'start_time')
        ordering = ['specific_date', 'start_time']

    def __str__(self):
        return f"Dr. {self.doctor.get_full_name()} — {self.specific_date.strftime('%b %d, %Y')} {self.start_time.strftime('%I:%M %p')}–{self.end_time.strftime('%I:%M %p')}"


class AppointmentPatientDetails(models.Model):
    """Snapshot of the patient details entered on the booking form at the
    moment the appointment is confirmed (Patient Details step).

    DATA ISOLATION — This is the ONLY destination for appointment form data:
    These fields are intentionally kept completely separate from the live
    CustomUser / PatientProfile, because a patient may book an appointment
    on behalf of a family member or dependent (e.g. a sibling, parent, or
    child). The person being booked is not necessarily the account owner.

    The booking flow must NEVER write these fields back to CustomUser or
    PatientProfile. The logged-in user's account information (name, email,
    profile) must remain completely unchanged by the booking process.

    This row provides a durable, immutable per-appointment record of who
    the appointment was booked for, independent of any future changes to
    either the account owner's profile or a separate patient profile.
    """
    GENDER_CHOICES = [('M', 'Male'), ('F', 'Female'), ('O', 'Other')]

    appointment   = models.OneToOneField(
        'Appointment', on_delete=models.CASCADE, related_name='patient_details'
    )
    first_name    = models.CharField(max_length=150)
    middle_name   = models.CharField(max_length=150, blank=True)
    last_name     = models.CharField(max_length=150)
    date_of_birth = models.DateField()
    gender        = models.CharField(max_length=1, choices=GENDER_CHOICES)
    address       = models.TextField()
    mobile_number = models.CharField(max_length=20)
    email         = models.EmailField(blank=True)
    chief_complaint = models.TextField(
        help_text='Reason for booking / chief complaint, shown to the assigned doctor.'
    )
    terms_accepted_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)

    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return ' '.join(p for p in parts if p)

    def __str__(self):
        return f"Patient details for appointment #{self.appointment_id}"


class Appointment(models.Model):
    STATUS_CHOICES = [
        ('Pending Assignment',  'Pending Assignment'),
        ('Scheduled',          'Scheduled'),
        ('Confirmed',          'Confirmed'),
        ('Completed',          'Completed'),
        ('Cancelled',          'Cancelled'),
        ('Rescheduled',        'Rescheduled'),
        ('Pending Reschedule', 'Pending Reschedule'),
    ]
    patient          = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='patient_appointments', limit_choices_to={'role': 'patient'}
    )
    doctor           = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='doctor_appointments', limit_choices_to={'role': 'doctor'}
    )
    secretary        = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='secretary_appointments',
        limit_choices_to={'role': 'secretary'}
    )
    appointment_date = models.DateField()
    # Null while the appointment is awaiting a time assignment from staff
    # (status == 'Pending Time Assignment'). Patients only pick a date when
    # booking or requesting a reschedule; the doctor or secretary assigns
    # the actual time afterward, which is when this gets filled in.
    appointment_time = models.TimeField(null=True, blank=True)
    status           = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Pending Assignment')
    reason           = models.TextField(blank=True)

    # When a patient requests a reschedule, the original date/time/reason stay
    # untouched (status flips to 'Pending Reschedule') and the requested new
    # date is held here until staff approves or rejects the request.
    # requested_time is no longer set by the patient (date-only requests) but
    # stays on the model since an approved request still needs to carry a
    # time once staff assigns one.
    requested_date   = models.DateField(null=True, blank=True)
    requested_time   = models.TimeField(null=True, blank=True)
    requested_reason = models.TextField(blank=True)

    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['appointment_date', 'appointment_time']

    @property
    def needs_time_assignment(self):
        return self.status == 'Pending Assignment'

    @classmethod
    def has_active_appointment(cls, patient):
        """Check if a patient has any active/upcoming appointment.
        Active statuses are those that prevent booking a new appointment:
        - Pending Assignment (awaiting staff to assign time)
        - Scheduled (assigned date/time, awaiting check-in)
        - Confirmed (patient has checked in, in progress)
        - Rescheduled (rescheduled appointment, still active)
        - Pending Reschedule (waiting for staff to approve reschedule)

        Patients can only book new appointments once their previous one reaches:
        - Completed (consultation finished)
        - Cancelled (patient or staff cancelled)
        """
        active_statuses = [
            'Pending Assignment',
            'Scheduled',
            'Confirmed',
            'Rescheduled',
            'Pending Reschedule',
        ]
        return cls.objects.filter(
            patient=patient,
            status__in=active_statuses
        ).exists()

    def __str__(self):
        return f"{self.patient.get_full_name()} + Dr. {self.doctor.get_full_name()} on {self.appointment_date} [{self.status}]"
