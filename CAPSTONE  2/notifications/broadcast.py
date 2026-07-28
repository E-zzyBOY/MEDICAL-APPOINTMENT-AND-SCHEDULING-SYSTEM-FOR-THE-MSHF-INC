import logging

from django.conf import settings
from django.core.mail import get_connection, EmailMessage
from django.template.loader import render_to_string

from accounts.models import CustomUser
from .models import Notification
from .email_utils import _should_email

logger = logging.getLogger(__name__)

EMAIL_CHUNK_SIZE = 50
ANNOUNCEMENT_MARKER = "\U0001F4E2"  # megaphone — lets the bell dropdown tell broadcasts apart from appointment notifications


def _recipients_for_scope(scope):
    qs = CustomUser.objects.exclude(role='admin').filter(is_active=True).exclude(email='')
    if scope != 'all':
        qs = qs.filter(role=scope)
    return qs


def send_broadcast(broadcast):
    """Fan a Broadcast out to every matching user as an in-app Notification
    (always) plus an email (unless the recipient opted out). Runs
    synchronously inside the admin's request since there's no task queue in
    this project, but batches emails in fixed-size chunks reusing one
    connection per chunk instead of opening a new one per recipient."""
    recipients = list(_recipients_for_scope(broadcast.scope))
    notif_message = f"{ANNOUNCEMENT_MARKER} {broadcast.subject}\n\n{broadcast.message}"

    Notification.objects.bulk_create(
        [Notification(user=u, message=notif_message, broadcast=broadcast) for u in recipients],
        batch_size=500,
    )

    emailable = [u for u in recipients if broadcast.override_opt_out or _should_email(u)]
    email_body = render_to_string('notifications/email/announcement.html', {
        'subject': broadcast.subject,
        'body': broadcast.message,
    })

    sent = 0
    for i in range(0, len(emailable), EMAIL_CHUNK_SIZE):
        chunk = emailable[i:i + EMAIL_CHUNK_SIZE]
        connection = get_connection(fail_silently=True)
        try:
            connection.open()
            messages = [
                EmailMessage(broadcast.subject, email_body, settings.DEFAULT_FROM_EMAIL,
                             [u.email], connection=connection)
                for u in chunk
            ]
            sent += connection.send_messages(messages) or 0
        except Exception:
            logger.exception('Broadcast #%s: email batch starting at %s failed', broadcast.pk, i)
        finally:
            connection.close()

    broadcast.recipient_count = len(recipients)
    broadcast.email_sent_count = sent
    broadcast.save(update_fields=['recipient_count', 'email_sent_count'])
    return broadcast
