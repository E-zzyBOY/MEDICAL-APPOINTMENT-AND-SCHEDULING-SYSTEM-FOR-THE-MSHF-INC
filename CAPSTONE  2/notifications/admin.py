from django.contrib import admin
from .models import Notification, Broadcast

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'message', 'is_read', 'created_at']
    list_filter  = ['is_read']

@admin.register(Broadcast)
class BroadcastAdmin(admin.ModelAdmin):
    list_display = ['subject', 'scope', 'sender', 'recipient_count', 'email_sent_count', 'created_at']
    list_filter  = ['scope']
