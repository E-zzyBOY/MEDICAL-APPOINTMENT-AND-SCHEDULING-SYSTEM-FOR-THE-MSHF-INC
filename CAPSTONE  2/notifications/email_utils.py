import logging

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)


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
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL,
                  [user.email], fail_silently=False)
    except Exception:
        # Never let a mail outage break registration itself, but DO leave
        # the real SMTP error in the server logs — a silently missing
        # verification email is undebuggable otherwise.
        logger.exception('Verification email to %s failed to send', user.email)


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


def _staff_recipients(doctor):
    """The doctor plus every secretary assigned to them — mirrors
    _notify_assigned_secretaries_and_doctor() in appointments/views/patient_views.py,
    which fans the equivalent in-app Notification out to the same set."""
    recipients = [doctor]
    for secretary_profile in doctor.assigned_secretaries.select_related('user').all():
        if secretary_profile.user:
            recipients.append(secretary_profile.user)
    return recipients


def _send_staff_email(appointment, subject, template, ctx=None):
    ctx = ctx if ctx is not None else {
        'patient_name': appointment.patient.get_full_name(),
        'doctor_name':  f"Dr. {appointment.doctor.get_full_name()}",
        'date':         appointment.appointment_date.strftime('%B %d, %Y'),
        'time':         _format_time_or_none(appointment.appointment_time),
        'reason':       appointment.reason,
    }
    message = render_to_string(template, ctx)
    for staff_user in _staff_recipients(appointment.doctor):
        if _should_email(staff_user):
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL,
                      [staff_user.email], fail_silently=True)


def send_staff_new_booking_email(appointment):
    """Notifies the doctor and their assigned secretaries by email that a
    patient requested a new appointment awaiting time assignment."""
    _send_staff_email(
        appointment, "New Appointment Request — MSHFI",
        'notifications/email/staff_new_booking.html',
    )


def send_staff_reschedule_request_email(appointment):
    """Notifies the doctor and their assigned secretaries by email that a
    patient requested to reschedule, pending approval. Uses requested_date
    (not appointment_date) since the reschedule hasn't been approved yet —
    mirrors the in-app notification built at the same call site in
    appointments/views/patient_views.py:reschedule_appointment."""
    ctx = {
        'patient_name': appointment.patient.get_full_name(),
        'doctor_name':  f"Dr. {appointment.doctor.get_full_name()}",
        'date':         appointment.requested_date.strftime('%B %d, %Y'),
    }
    _send_staff_email(
        appointment, "Reschedule Request — MSHFI",
        'notifications/email/staff_reschedule_request.html', ctx=ctx,
    )


def send_staff_cancellation_email(appointment):
    """Notifies the doctor and their assigned secretaries by email that a
    patient cancelled their appointment."""
    _send_staff_email(
        appointment, "Appointment Cancelled by Patient — MSHFI",
        'notifications/email/staff_cancellation.html',
    )
