import logging

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)


def _send_email(subject, template, ctx, recipients, fail_silently):
    """Single choke point for every outgoing email: sends the existing
    plain-text template as the body PLUS a branded HTML alternative (the
    html/ variant of the same template name), so mail clients that render
    HTML show the important information highlighted while plain-text
    clients — and the tests that regex-parse .body — still get the
    original text."""
    text_body = render_to_string(f'notifications/email/{template}', ctx)
    html_body = render_to_string(f'notifications/email/html/{template}', ctx)
    msg = EmailMultiAlternatives(subject, text_body,
                                 settings.DEFAULT_FROM_EMAIL, recipients)
    msg.attach_alternative(html_body, 'text/html')
    msg.send(fail_silently=fail_silently)


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


def send_verification_email(user, code, ttl_minutes=10):
    """Sent right after a password OR Google sign-up (and on 'Resend') with
    the 6-digit code the user types on the confirmation page to flip
    CustomUser.email_verified — see accounts/otp.py for issuing/checking the
    code. Ignores the email_notifications_enabled opt-out: this email IS the
    account gate, not a courtesy notification."""
    subject = "Confirm your email — MSHFI"
    ctx = {
        'patient_name': user.get_full_name() or user.username,
        'code':         code,
        'ttl_minutes':  ttl_minutes,
    }
    try:
        _send_email(subject, 'verify_email.html', ctx, [user.email], fail_silently=False)
    except Exception:
        # Never let a mail outage break registration itself, but DO leave
        # the real SMTP error in the server logs — a silently missing
        # verification email is undebuggable otherwise.
        logger.exception('Verification email to %s failed to send', user.email)


def send_password_changed_email(user):
    """Security notice sent right after a Settings password change/set.
    Ignores email_notifications_enabled like send_verification_email —
    this is an account-security alert, not a courtesy notification."""
    if not user.email:
        return
    subject = "Your password was changed — MSHFI"
    ctx = {
        'user_name': user.get_full_name() or user.username,
        'username':  user.username,
    }
    try:
        _send_email(subject, 'password_changed.html', ctx, [user.email], fail_silently=False)
    except Exception:
        logger.exception('Password-changed email to %s failed to send', user.email)


def send_account_deactivated_email(user):
    """Security notice sent right after a Settings self-deactivation."""
    if not user.email:
        return
    subject = "Your account was deactivated — MSHFI"
    ctx = {
        'user_name': user.get_full_name() or user.username,
        'username':  user.username,
    }
    try:
        _send_email(subject, 'account_deactivated.html', ctx, [user.email], fail_silently=False)
    except Exception:
        logger.exception('Account-deactivated email to %s failed to send', user.email)


def send_account_created_email(user, plain_password):
    """Sent right after an admin creates a Doctor or Secretary account,
    giving them their login credentials. Ignores email_notifications_enabled
    like send_verification_email — this IS the account gate, not a courtesy
    notification."""
    if not user.email:
        return
    subject = "Your MSHFI Staff Account Has Been Created"
    ctx = {
        'user_name': user.get_full_name() or user.username,
        'username':  user.username,
        'password':  plain_password,
        'role':      user.get_role_display(),
    }
    try:
        _send_email(subject, 'account_created.html', ctx, [user.email], fail_silently=False)
    except Exception:
        logger.exception('Account-created email to %s failed to send', user.email)


def send_password_reset_email(user, new_plain_password):
    """Forgot Password flow. Returns True only if the mail actually left —
    the caller must NOT commit the new password unless it did, or a mail
    outage would lock the account out with nobody holding the new password.
    Ignores email_notifications_enabled: this is account recovery, not a
    courtesy notification."""
    if not user.email:
        return False
    subject = "Your new MSHFI password"
    ctx = {
        'user_name': user.get_full_name() or user.username,
        'username':  user.username,
        'password':  new_plain_password,
    }
    try:
        _send_email(subject, 'password_reset.html', ctx, [user.email], fail_silently=False)
        return True
    except Exception:
        logger.exception('Password-reset email to %s failed to send', user.email)
        return False


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
    _send_email(subject, 'booking_received.html', ctx,
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
    _send_email(subject, 'time_assigned.html', ctx,
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
    _send_email(subject, 'booking_confirmation.html', ctx,
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
    _send_email(subject, 'cancellation_notice.html', ctx,
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
    _send_email(subject, 'reschedule_notice.html', ctx,
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
    _send_email(subject, 'reminder.html', ctx,
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
    """`template` is the basename shared by the text template and its html/
    variant (see _send_email)."""
    ctx = ctx if ctx is not None else {
        'patient_name': appointment.patient.get_full_name(),
        'doctor_name':  f"Dr. {appointment.doctor.get_full_name()}",
        'date':         appointment.appointment_date.strftime('%B %d, %Y'),
        'time':         _format_time_or_none(appointment.appointment_time),
        'reason':       appointment.reason,
    }
    for staff_user in _staff_recipients(appointment.doctor):
        if _should_email(staff_user):
            _send_email(subject, template, ctx, [staff_user.email], fail_silently=True)


def send_staff_new_booking_email(appointment):
    """Notifies the doctor and their assigned secretaries by email that a
    patient requested a new appointment awaiting time assignment."""
    _send_staff_email(
        appointment, "New Appointment Request — MSHFI",
        'staff_new_booking.html',
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
        'staff_reschedule_request.html', ctx=ctx,
    )


def send_staff_cancellation_email(appointment):
    """Notifies the doctor and their assigned secretaries by email that a
    patient cancelled their appointment."""
    _send_staff_email(
        appointment, "Appointment Cancelled by Patient — MSHFI",
        'staff_cancellation.html',
    )


def send_staff_reminder_email(appointment):
    """Notifies the doctor and their assigned secretaries by email that a
    patient has an appointment tomorrow. Companion to send_reminder_email
    (patient-facing) — used by the send_appointment_reminders command."""
    _send_staff_email(
        appointment, "Appointment Reminder — MSHFI (Tomorrow)",
        'staff_reminder.html',
    )
