from django import forms
from datetime import date
from .models import Schedule, Appointment
from accounts.models import CustomUser


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
    appointment_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    appointment_time = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}))
    reason           = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)


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
