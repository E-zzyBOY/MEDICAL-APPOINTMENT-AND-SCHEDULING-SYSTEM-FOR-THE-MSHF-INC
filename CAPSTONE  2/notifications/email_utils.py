from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings


def _should_email(patient):
    """Centralized opt-out check: skip sending if the patient has turned
    off email notifications in their settings. In-app Notification rows
    are unaffected by this — only the email send is skipped."""
    return getattr(patient, 'email_notifications_enabled', True)


def send_booking_confirmation_email(appointment):
    if not _should_email(appointment.patient):
        return
    subject = "Appointment Confirmed — MSHFI"
    ctx = {
        'patient_name': appointment.patient.get_full_name(),
        'doctor_name':  f"Dr. {appointment.doctor.get_full_name()}",
        'date':         appointment.appointment_date.strftime('%B %d, %Y'),
        'time':         appointment.appointment_time.strftime('%I:%M %p'),
        'reason':       appointment.reason,
    }
    message = render_to_string('notifications/email/booking_confirmation.html', ctx)
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL,
              [appointment.patient.email], fail_silently=True)


def send_cancellation_email(appointment, reason=''):
    if not _should_email(appointment.patient):
        return
    subject = "Appointment Cancelled — MSHFI"
    ctx = {
        'patient_name': appointment.patient.get_full_name(),
        'doctor_name':  f"Dr. {appointment.doctor.get_full_name()}",
        'date':         appointment.appointment_date.strftime('%B %d, %Y'),
        'time':         appointment.appointment_time.strftime('%I:%M %p'),
        'reason':       reason or 'No reason provided.',
    }
    message = render_to_string('notifications/email/cancellation_notice.html', ctx)
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL,
              [appointment.patient.email], fail_silently=True)


def send_reschedule_email(appointment):
    if not _should_email(appointment.patient):
        return
    subject = "Appointment Rescheduled — MSHFI"
    ctx = {
        'patient_name': appointment.patient.get_full_name(),
        'doctor_name':  f"Dr. {appointment.doctor.get_full_name()}",
        'date':         appointment.appointment_date.strftime('%B %d, %Y'),
        'time':         appointment.appointment_time.strftime('%I:%M %p'),
    }
    message = render_to_string('notifications/email/reschedule_notice.html', ctx)
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL,
              [appointment.patient.email], fail_silently=True)


def send_reminder_email(appointment):
    if not _should_email(appointment.patient):
        return
    subject = "Appointment Reminder — MSHFI (Tomorrow)"
    ctx = {
        'patient_name': appointment.patient.get_full_name(),
        'doctor_name':  f"Dr. {appointment.doctor.get_full_name()}",
        'date':         appointment.appointment_date.strftime('%B %d, %Y'),
        'time':         appointment.appointment_time.strftime('%I:%M %p'),
    }
    message = render_to_string('notifications/email/reminder.html', ctx)
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL,
              [appointment.patient.email], fail_silently=True)
