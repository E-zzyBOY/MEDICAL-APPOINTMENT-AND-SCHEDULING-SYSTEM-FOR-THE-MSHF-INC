from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, PatientProfile, DoctorProfile, SecretaryProfile, ActivityLog


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'is_active']
    list_filter  = ['role', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('Role', {'fields': ('role',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role', {'fields': ('role',)}),
    )


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'gender', 'age', 'contact_number']


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'specialization']


@admin.register(SecretaryProfile)
class SecretaryProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'assigned_doctor', 'date_assigned']


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """Read-only audit trail — rows are written only by the auth signal
    receivers and IdleTimeoutMiddleware, never edited by hand."""
    list_display   = ['timestamp', 'username', 'user', 'action', 'ip_address']
    list_filter    = ['action', 'timestamp']
    search_fields  = ['username', 'user__username', 'ip_address']
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
