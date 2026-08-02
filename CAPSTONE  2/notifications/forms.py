from django import forms
from .models import Broadcast


class BroadcastForm(forms.ModelForm):
    class Meta:
        model = Broadcast
        fields = ['subject', 'message', 'scope', 'override_opt_out']
        widgets = {
            'subject': forms.TextInput(attrs={'placeholder': 'Announcement subject'}),
            'message': forms.Textarea(attrs={'rows': 6, 'placeholder': 'Write the announcement...'}),
            'scope': forms.RadioSelect(),
            'override_opt_out': forms.CheckboxInput(attrs={'class': 'mt-0.5 shrink-0'}),
        }
