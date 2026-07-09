from django import forms
from django.utils import timezone
from accounts.psgc import validate_picker_data
from datetime import date, datetime
from .models import Schedule, Appointment, AppointmentPatientDetails
from accounts.models import CustomUser
from accounts.validators import validate_ph_mobile_number, normalize_ph_mobile_number


RELATIONSHIP_CHOICES = [
    ('Self', 'Self'),
    ('Mother', 'Mother'),
    ('Father', 'Father'),
    ('Sibling', 'Sibling'),
    ('Child', 'Child'),
    ('Spouse', 'Spouse'),
    ('Other', 'Other'),
]


class PatientDetailsForm(forms.Form):
    """Step 4 of booking: 'Patient Details'. Pre-filled from the logged-in
    patient's profile where available; the patient can edit anything before
    confirming.

    IMPORTANT — Data Isolation:
    Fields here are the source of truth for ONE write only:
    AppointmentPatientDetails (a permanent snapshot tied to the appointment).
    They must NEVER be written back to CustomUser or PatientProfile, because
    this form may be filled out for a family member or dependent rather than
    the account owner. The logged-in user's account information must always
    remain completely unchanged by the booking flow.
    """
    first_name    = forms.CharField(max_length=150, required=True, label='First Name')
    middle_name   = forms.CharField(max_length=150, required=False, label='Middle Name')
    last_name     = forms.CharField(max_length=150, required=True, label='Last Name')
    date_of_birth = forms.DateField(
        required=True, label='Date of Birth',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    gender        = forms.ChoiceField(
        choices=[('', '-- Select --')] + [('M', 'Male'), ('F', 'Female'), ('O', 'Other')],
        required=True, label='Sex'
    )
    address       = forms.CharField(
        required=True, label='Address', widget=forms.Textarea(attrs={'rows': 2})
    )
    mobile_number = forms.CharField(max_length=20, required=True, label='Mobile Number')
    email         = forms.EmailField(required=False, label='Email Address')
    relationship  = forms.ChoiceField(
        choices=RELATIONSHIP_CHOICES, required=True, label='Relationship to Account Holder',
    )
    reason        = forms.CharField(
        required=True, label='Chief Complaint',
        widget=forms.Textarea(attrs={'rows': 3})
    )
    terms_accepted = forms.BooleanField(
        required=True, label='I agree to the Terms and Conditions and Privacy Policy',
        error_messages={'required': 'You must agree to the Terms and Conditions and Privacy Policy to continue.'}
    )

    def clean(self):
        cleaned = super().clean()
        err = validate_picker_data(self.data, forms)
        if err:
            self.add_error('address', err)
        return cleaned

    def clean_date_of_birth(self):
        dob = self.cleaned_data['date_of_birth']
        if dob and dob >= date.today():
            raise forms.ValidationError('Date of birth must be before today.')
        return dob

    def clean_mobile_number(self):
        value = self.cleaned_data['mobile_number']
        validate_ph_mobile_number(value)
        return normalize_ph_mobile_number(value)


class MultiDateScheduleForm(forms.Form):
    """Add Slot, multi-date version: one start/end time applied to every
    date the doctor selected on the calendar in one submit, instead of
    repeating the whole Add Slot flow once per day. Each date still gets
    its own Schedule row — this form just collects the shared time once.

    Dates arrive as a comma-separated string from a hidden field the
    calendar JS maintains client-side (one toggleable selection set),
    parsed and validated here rather than trusting the client's list of
    dates blindly.
    """
    dates      = forms.CharField(widget=forms.HiddenInput(), required=False)
    start_time = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}))
    end_time   = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}))

    def clean_dates(self):
        raw = self.cleaned_data['dates']
        if not raw:
            raise forms.ValidationError('Select at least one date on the calendar.')
        parsed = []
        today = date.today()
        for part in raw.split(','):
            part = part.strip()
            if not part:
                continue
            try:
                d = datetime.strptime(part, '%Y-%m-%d').date()
            except ValueError:
                raise forms.ValidationError(f"'{part}' is not a valid date.")
            if d < today:
                raise forms.ValidationError(f"{d.strftime('%b %d, %Y')} is in the past.")
            parsed.append(d)
        if not parsed:
            raise forms.ValidationError('Select at least one date on the calendar.')
        # De-duplicate while preserving order, in case the client sent the
        # same date twice.
        seen = set()
        unique = []
        for d in parsed:
            if d not in seen:
                seen.add(d)
                unique.append(d)
        return unique

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_time')
        end   = cleaned.get('end_time')
        dates = cleaned.get('dates', [])
        if start and end and end <= start:
            raise forms.ValidationError('End time must be after start time.')
        if start and any(d == date.today() for d in dates):
            now_time = timezone.localtime().time()
            if start <= now_time:
                raise forms.ValidationError('The start time has already passed today. Please choose a future time.')
        return cleaned


class ScheduleForm(forms.ModelForm):
    class Meta:
        model  = Schedule
        fields = ['specific_date', 'start_time', 'end_time']
        widgets = {
            'specific_date': forms.HiddenInput(),
            'start_time':    forms.TimeInput(attrs={'type': 'time'}),
            'end_time':      forms.TimeInput(attrs={'type': 'time'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_time')
        end   = cleaned.get('end_time')
        specific_date = cleaned.get('specific_date')
        if start and end and end <= start:
            raise forms.ValidationError('End time must be after start time.')
        if specific_date and specific_date < date.today():
            raise forms.ValidationError('Cannot add a schedule slot for a past date.')
        if specific_date and start and specific_date == date.today():
            if start <= timezone.localtime().time():
                raise forms.ValidationError('The start time has already passed today. Please choose a future time.')
        return cleaned


class RescheduleForm(forms.Form):
    """Used when a doctor directly reschedules one of their own appointments
    (separate from a patient's reschedule *request*, which is handled in
    patient_views). Date-only: the actual time is set afterward through
    AssignTimeForm by whichever staff member gets to it first."""
    appointment_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    reason           = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)

    def clean_appointment_date(self):
        new_date = self.cleaned_data['appointment_date']
        if new_date < date.today():
            raise forms.ValidationError('Cannot reschedule to a past date.')
        return new_date


class AssignTimeForm(forms.Form):
    """Used by a doctor or secretary to set the actual time on an
    appointment sitting in 'Pending Time Assignment'. The time itself is
    validated against the doctor's working hours for that date and checked
    for conflicts in the view, since both depend on which doctor/date this
    particular appointment is for — info the form alone doesn't have."""
    appointment_time = forms.TimeField(
        required=True, label='Appointment Time',
        widget=forms.TimeInput(attrs={'type': 'time'})
    )


class AdminAppointmentEditForm(forms.ModelForm):
    class Meta:
        model  = Appointment
        fields = ['doctor', 'appointment_date', 'appointment_time', 'status']
        widgets = {
            'appointment_date': forms.DateInput(attrs={'type': 'date'}),
            'appointment_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['doctor'].queryset = CustomUser.objects.filter(role='doctor')
