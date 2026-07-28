from django.db import models
from django.conf import settings


class Broadcast(models.Model):
    SCOPE_CHOICES = [
        ('all',       'All Users'),
        ('patient',   'All Patients'),
        ('doctor',    'All Doctors'),
        ('secretary', 'All Secretaries'),
    ]
    sender           = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                          null=True, related_name='broadcasts_sent')
    subject          = models.CharField(max_length=200)
    message          = models.TextField()
    scope            = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='all')
    override_opt_out = models.BooleanField(
        default=False,
        help_text='Also email users who disabled email notifications (use only for urgent/critical announcements).',
    )
    recipient_count  = models.PositiveIntegerField(default=0)
    email_sent_count = models.PositiveIntegerField(default=0)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Broadcast: {self.subject} ({self.get_scope_display()})"


class Notification(models.Model):
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message    = models.TextField()
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    broadcast  = models.ForeignKey(Broadcast, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='notifications')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message[:50]}"
