from django import forms
from .models import Schedule, Appointment
from accounts.models import CustomUser


class ScheduleForm(forms.ModelForm):
    class Meta:
        model  = Schedule
        fields = ['day_of_week', 'start_time', 'end_time']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time':   forms.TimeInput(attrs={'type': 'time'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_time')
        end   = cleaned.get('end_time')
        if start and end and end <= start:
            raise forms.ValidationError('End time must be after start time.')
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
