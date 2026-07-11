from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings


def _should_email(patient):
    """Centralized opt-out check: skip sending if the patient has turned
    off email notifications in their settings. In-app Notification rows
    are unaffected by this — only the email send is skipped."""
    return getattr(patient, 'email_notifications_enabled', True)


def _format_time_or_none(t):
    """Appointments can sit with no time yet while awaiting staff to
    assign one (status == 'Pending Time Assignment'). Callers that build
    an email context need a safe string either way."""
    return t.strftime('%I:%M %p') if t else 'To be confirmed'


def send_verification_email(user, request):
    """Sent right after a password sign-up (and on 'Resend') with the
    signed link that flips CustomUser.email_verified. Google sign-ups never
    receive this — the provider already verified their address. Ignores the
    email_notifications_enabled opt-out: this email IS the account gate,
    not a courtesy notification."""
    from django.urls import reverse
    from accounts.tokens import make_email_verify_token

    token = make_email_verify_token(user)
    verify_url = request.build_absolute_uri(
        reverse('accounts:verify_email', args=[token])
    )
    subject = "Confirm your email — MSHFI"
    ctx = {
        'patient_name': user.get_full_name() or user.username,
        'verify_url':   verify_url,
    }
    message = render_to_string('notifications/email/verify_email.html', ctx)
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL,
              [user.email], fail_silently=True)


def send_booking_received_email(appointment):
    """Sent right after a patient books — no time has been assigned yet,
    so this confirms the date only and explains staff will follow up with
    the time. send_booking_confirmation_email (below) is for an
    already-timed appointment and is no longer used at booking time."""
    if not _should_email(appointment.patient):
        return
    subject = "Appointment Request Received — MSHFI"
    ctx = {
        'patient_name': appointment.patient.get_full_name(),
        'doctor_name':  f"Dr. {appointment.doctor.get_full_name()}",
        'date':         appointment.appointment_date.strftime('%B %d, %Y'),
        'reason':       appointment.reason,
    }
    message = render_to_string('notifications/email/booking_received.html', ctx)
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL,
              [appointment.patient.email], fail_silently=True)


def send_time_assigned_email(appointment):
    """Sent once a doctor or secretary assigns the actual time for a
    pending appointment."""
    if not _should_email(appointment.patient):
        return
    subject = "Your Appointment Time Has Been Set — MSHFI"
    ctx = {
        'patient_name': appointment.patient.get_full_name(),
        'doctor_name':  f"Dr. {appointment.doctor.get_full_name()}",
        'date':         appointment.appointment_date.strftime('%B %d, %Y'),
        'time':         _format_time_or_none(appointment.appointment_time),
        'reason':       appointment.reason,
    }
    message = render_to_string('notifications/email/time_assigned.html', ctx)
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL,
              [appointment.patient.email], fail_silently=True)


def send_booking_confirmation_email(appointment):
    if not _should_email(appointment.patient):
        return
    subject = "Appointment Confirmed — MSHFI"
    ctx = {
        'patient_name': appointment.patient.get_full_name(),
        'doctor_name':  f"Dr. {appointment.doctor.get_full_name()}",
        'date':         appointment.appointment_date.strftime('%B %d, %Y'),
        'time':         _format_time_or_none(appointment.appointment_time),
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
        'time':         _format_time_or_none(appointment.appointment_time),
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
        'time':         _format_time_or_none(appointment.appointment_time),
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
        'time':         _format_time_or_none(appointment.appointment_time),
    }
    message = render_to_string('notifications/email/reminder.html', ctx)
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL,
              [appointment.patient.email], fail_silently=True)
