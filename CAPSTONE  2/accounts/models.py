from django.contrib.auth.models import AbstractUser
from django.db import models

# Bump this when the Terms & Conditions / Privacy Policy text changes in a
# way that requires patients to re-consent. Patients whose
# PatientProfile.terms_accepted_version doesn't match are asked to check
# the box again on their next booking, even if they'd accepted a prior
# version before.
TERMS_VERSION = '2026-06'


class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('patient',   'Patient'),
        ('doctor',    'Doctor'),
        ('secretary', 'Secretary'),
        ('admin',     'Admin'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='patient')
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    email_notifications_enabled = models.BooleanField(default=True)
    # Self-registered patients (password OR Google sign-up) must click the
    # link emailed to them before using the app (see
    # EmailVerificationRequiredMiddleware). Staff accounts and walk-in
    # patients registered by staff are never gated on it.
    email_verified = models.BooleanField(default=False)

    def is_patient(self):    return self.role == 'patient'
    def is_doctor(self):     return self.role == 'doctor'
    def is_secretary(self):  return self.role == 'secretary'
    def is_admin_role(self): return self.role == 'admin'

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"


class PatientProfile(models.Model):
    GENDER_CHOICES = [('M', 'Male'), ('F', 'Female'), ('O', 'Other')]
    BLOOD_TYPE_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-'),
    ]
    user           = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='patient_profile')
    middle_name    = models.CharField(max_length=150, blank=True)
    contact_number = models.CharField(max_length=20, blank=True)
    age            = models.PositiveIntegerField(null=True, blank=True)
    gender         = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    date_of_birth  = models.DateField(null=True, blank=True)
    place_of_birth = models.CharField(max_length=150, blank=True)
    address        = models.TextField(blank=True)
    guardian       = models.CharField(max_length=150, blank=True)
    emergency_contact_name   = models.CharField(max_length=150, blank=True)
    emergency_contact_number = models.CharField(max_length=20, blank=True)
    blood_type     = models.CharField(max_length=3, choices=BLOOD_TYPE_CHOICES, blank=True)
    # Set the first time the patient checks the Terms & Conditions / Privacy
    # Policy box during booking. Once set, the booking flow treats consent
    # as already on file and doesn't force a re-check on every visit unless
    # the policy version changes (see TERMS_VERSION below).
    terms_accepted_at      = models.DateTimeField(null=True, blank=True)
    terms_accepted_version = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"Profile: {self.user.get_full_name()}"


# Single master list of doctor specializations, in professional-title form
# ("Neurologist", not "Neurology"). This is the ONE source used both by the
# admin Create/Edit Doctor dropdowns and by the patient "Browse by Specialty"
# filter, so the two can never drift apart (the original bug: admin typed
# "Neurology" free-text, patient filter looked for "Neurologist").
SPECIALIZATIONS = [
    'General Practitioner / Family Medicine Physician',
    'Internist (Internal Medicine)',
    'Pediatrician',
    'Obstetrician-Gynecologist (OB-GYN)',
    'Surgeon (General Surgery)',
    'Cardiologist',
    'Neurologist',
    'Dermatologist',
    'Psychiatrist',
    'Ophthalmologist',
    'Otorhinolaryngologist (ENT)',
    'Orthopedic Surgeon',
    'Urologist',
    'Nephrologist',
    'Endocrinologist',
    'Gastroenterologist',
    'Pulmonologist',
    'Oncologist',
    'Radiologist',
    'Anesthesiologist',
    'Pathologist',
    'Rheumatologist',
    'Hematologist',
    'Infectious Disease Specialist',
    'Allergist / Immunologist',
    'Nutritionist-Dietitian',
    'Physiatrist (Physical Medicine & Rehabilitation)',
    'Dentist',
]
SPECIALIZATION_CHOICES = [(s, s) for s in SPECIALIZATIONS]


class DoctorProfile(models.Model):
    user                = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='doctor_profile')
    specialization      = models.CharField(max_length=150, blank=True, choices=SPECIALIZATION_CHOICES)
    years_of_experience = models.PositiveIntegerField(null=True, blank=True)
    license_number      = models.CharField(max_length=100, blank=True)
    bio                 = models.TextField(blank=True, help_text="Short professional bio shown on your public doctor profile.")

    def __str__(self):
        return f"Dr. {self.user.get_full_name()} — {self.specialization}"


class SocialAccount(models.Model):
    """Links a CustomUser to an external identity provider (Google for now;
    'facebook' is reserved for when Meta app review is sorted out). Login
    matching is ALWAYS by (provider, provider_user_id) — the provider's own
    stable subject ID — never by email, since emails can change hands or be
    recycled on the provider's side. Only patient accounts ever get linked;
    staff must keep using username/password."""
    PROVIDER_CHOICES = [
        ('google',   'Google'),
        ('facebook', 'Facebook'),
    ]
    user             = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='social_accounts')
    provider         = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    provider_user_id = models.CharField(max_length=255)
    # Snapshot of the email the provider reported when the link was made.
    # Informational only (support/debugging) — never used for matching.
    email_at_link    = models.CharField(max_length=254, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['provider', 'provider_user_id'], name='unique_provider_identity'),
            models.UniqueConstraint(fields=['provider', 'user'], name='unique_provider_per_user'),
        ]

    def __str__(self):
        return f"{self.get_provider_display()} link for {self.user.username}"


class SecretaryProfile(models.Model):
    user            = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='secretary_profile')
    assigned_doctor = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_secretaries',
        limit_choices_to={'role': 'doctor'}
    )
    date_assigned   = models.DateField(null=True, blank=True)
    contact_number  = models.CharField(max_length=20, blank=True)
    employee_id     = models.CharField(max_length=30, blank=True, verbose_name='Employee/Staff ID')

    def __str__(self):
        return f"Secretary: {self.user.get_full_name()}"


class ActivityLog(models.Model):
    """Security audit trail: one row per auth event, written by the
    receivers in accounts/signals.py and by IdleTimeoutMiddleware."""
    ACTION_CHOICES = [
        ('login',        'Login'),
        ('logout',       'Logout'),
        ('auto_logout',  'Auto logout (inactivity)'),
        ('login_failed', 'Failed login'),
    ]
    user = models.ForeignKey(
        CustomUser, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='activity_logs')
    # Kept as plain text so the row survives user deletion; on login_failed
    # it holds the username that was attempted.
    username   = models.CharField(max_length=150, blank=True)
    action     = models.CharField(max_length=20, choices=ACTION_CHOICES)
    timestamp  = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.get_action_display()} — {self.username or 'unknown'} @ {self.timestamp:%Y-%m-%d %H:%M}"
