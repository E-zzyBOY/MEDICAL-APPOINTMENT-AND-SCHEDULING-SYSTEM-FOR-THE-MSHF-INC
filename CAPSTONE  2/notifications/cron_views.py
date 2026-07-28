import hmac
import io
import logging

from django.conf import settings
from django.http import JsonResponse, HttpResponseForbidden
from django.core.management import call_command
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


def _token_is_valid(request):
    """Fails closed: an unset CRON_SECRET (the default) never matches
    anything, so this endpoint is inert until explicitly configured.
    Reads the token from the Authorization header rather than the query
    string so it doesn't end up in access/proxy logs."""
    expected = settings.CRON_SECRET
    auth = request.headers.get('Authorization', '')
    provided = auth[7:] if auth.startswith('Bearer ') else ''
    return bool(expected) and hmac.compare_digest(expected, provided)


@require_GET
def send_appointment_reminders(request):
    """Free-tier substitute for a Render Cron Job: an external scheduler
    (GitHub Actions, cron-job.org, ...) hits this URL with an
    "Authorization: Bearer <CRON_SECRET>" header once a day to run the
    same day-before reminder command a paid Cron Job would otherwise run
    directly on Render."""
    if not _token_is_valid(request):
        return HttpResponseForbidden('Forbidden')

    out = io.StringIO()
    err = io.StringIO()
    try:
        call_command('send_appointment_reminders', stdout=out, stderr=err)
    except Exception:
        logger.exception('send_appointment_reminders failed via cron endpoint')
        return JsonResponse({'ok': False, 'output': out.getvalue(), 'error': err.getvalue()}, status=500)

    return JsonResponse({'ok': True, 'output': out.getvalue(), 'error': err.getvalue()})
