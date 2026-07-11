# Data migration for the specialization standardization (free text -> master
# list dropdown). Maps legacy free-text values ("Neurology", "cardiology",
# "Pediatrics", ...) onto the professional-title form used by the new
# SPECIALIZATIONS master list, so existing doctors keep appearing in the
# patient "Browse by Specialty" filter. Values it can't recognize are left
# untouched — those doctors won't get a specialty chip until an admin
# re-selects a value from the dropdown, but no data is lost.

from django.db import migrations


# Canonical values (must stay in sync with accounts.models.SPECIALIZATIONS —
# duplicated here on purpose so this migration stays frozen even if the
# master list changes later).
_CANONICAL = [
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

# Legacy discipline-form / shorthand values -> canonical title form.
# Keys are compared lowercase/stripped.
_LEGACY_MAP = {
    'general medicine': 'General Practitioner / Family Medicine Physician',
    'general practitioner': 'General Practitioner / Family Medicine Physician',
    'family medicine': 'General Practitioner / Family Medicine Physician',
    'gp': 'General Practitioner / Family Medicine Physician',
    'internal medicine': 'Internist (Internal Medicine)',
    'internist': 'Internist (Internal Medicine)',
    'pediatrics': 'Pediatrician',
    'paediatrics': 'Pediatrician',
    'obstetrics and gynecology': 'Obstetrician-Gynecologist (OB-GYN)',
    'obstetrics & gynecology': 'Obstetrician-Gynecologist (OB-GYN)',
    'ob-gyn': 'Obstetrician-Gynecologist (OB-GYN)',
    'obgyn': 'Obstetrician-Gynecologist (OB-GYN)',
    'general surgery': 'Surgeon (General Surgery)',
    'surgeon': 'Surgeon (General Surgery)',
    'surgery': 'Surgeon (General Surgery)',
    'cardiology': 'Cardiologist',
    'neurology': 'Neurologist',
    'dermatology': 'Dermatologist',
    'psychiatry': 'Psychiatrist',
    'ophthalmology': 'Ophthalmologist',
    'ent': 'Otorhinolaryngologist (ENT)',
    'otorhinolaryngology': 'Otorhinolaryngologist (ENT)',
    'orthopedics': 'Orthopedic Surgeon',
    'orthopaedics': 'Orthopedic Surgeon',
    'urology': 'Urologist',
    'nephrology': 'Nephrologist',
    'endocrinology': 'Endocrinologist',
    'gastroenterology': 'Gastroenterologist',
    'pulmonology': 'Pulmonologist',
    'oncology': 'Oncologist',
    'radiology': 'Radiologist',
    'anesthesiology': 'Anesthesiologist',
    'pathology': 'Pathologist',
    'rheumatology': 'Rheumatologist',
    'hematology': 'Hematologist',
    'infectious disease': 'Infectious Disease Specialist',
    'allergy and immunology': 'Allergist / Immunologist',
    'immunology': 'Allergist / Immunologist',
    'nutrition': 'Nutritionist-Dietitian',
    'nutritionist': 'Nutritionist-Dietitian',
    'dietitian': 'Nutritionist-Dietitian',
    'physical medicine and rehabilitation': 'Physiatrist (Physical Medicine & Rehabilitation)',
    'rehabilitation medicine': 'Physiatrist (Physical Medicine & Rehabilitation)',
    'dentistry': 'Dentist',
}


def _canonicalize(value):
    key = value.strip().lower()
    # Already canonical (any casing) -> canonical casing.
    for canonical in _CANONICAL:
        if key == canonical.lower():
            return canonical
    return _LEGACY_MAP.get(key)


def normalize(apps, schema_editor):
    DoctorProfile = apps.get_model('accounts', 'DoctorProfile')
    for profile in DoctorProfile.objects.exclude(specialization=''):
        canonical = _canonicalize(profile.specialization)
        if canonical and canonical != profile.specialization:
            profile.specialization = canonical
            profile.save(update_fields=['specialization'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_alter_doctorprofile_specialization'),
    ]

    operations = [
        migrations.RunPython(normalize, migrations.RunPython.noop),
    ]
