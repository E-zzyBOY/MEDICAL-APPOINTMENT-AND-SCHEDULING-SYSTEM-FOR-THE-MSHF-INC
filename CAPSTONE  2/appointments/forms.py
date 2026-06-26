from django import forms
from datetime import date
from .models import Schedule, Appointment, AppointmentPatientDetails
from accounts.models import CustomUser
from accounts.validators import validate_ph_mobile_number, normalize_ph_mobile_number


class PatientDetailsForm(forms.Form):
    """Step 4 of booking: 'Patient Details'. Pre-filled from the logged-in
    patient's profile where available; the patient can edit anything before
    confirming. Fields here double as the source of truth for two writes —
    AppointmentPatientDetails (a permanent snapshot tied to the appointment)
    and the live CustomUser / PatientProfile (so profile edits made here
    stick around for next time), per the spec's data-handling requirements.
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
    reason        = forms.CharField(
        required=True, label='Reason for Booking / Chief Complaint',
        widget=forms.Textarea(attrs={'rows': 3})
    )
    terms_accepted = forms.BooleanField(
        required=True, label='I agree to the Terms and Conditions and Privacy Policy',
        error_messages={'required': 'You must agree to the Terms and Conditions and Privacy Policy to continue.'}
    )

    def clean_date_of_birth(self):
        dob = self.cleaned_data['date_of_birth']
        if dob and dob > date.today():
            raise forms.ValidationError('Date of birth cannot be a future date.')
        return dob

    def clean_mobile_number(self):
        value = self.cleaned_data['mobile_number']
        validate_ph_mobile_number(value)
        return normalize_ph_mobile_number(value)


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
