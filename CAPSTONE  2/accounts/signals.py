"""Security audit logging for auth events.

Every login/logout path in the app (password login, registration,
Google OAuth, the logout view, and IdleTimeoutMiddleware's forced
logout) goes through django.contrib.auth.login()/logout(), so these
signal receivers capture all of them. Imported for side effects from
AccountsConfig.ready().
"""
import random
import time
from datetime import timedelta

from django.contrib.auth.signals import (
    user_logged_in, user_logged_out, user_login_failed,
)
from django.dispatch import receiver
from django.utils import timezone

from .models import ActivityLog

# Rows older than this are pruned opportunistically from log_activity().
RETENTION_DAYS = 180


def _client_ip(request):
    # Render terminates TLS at its proxy, so the real client address is the
    # first entry of X-Forwarded-For; locally REMOTE_ADDR is correct.
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_activity(request, action, user=None, username=''):
    """Write one ActivityLog row. Never raises: an audit-log failure must
    not break login/logout itself."""
    try:
        ActivityLog.objects.create(
            user=user,
            username=username or (user.get_username() if user else ''),
            action=action,
            ip_address=_client_ip(request) if request else None,
            user_agent=(request.META.get('HTTP_USER_AGENT', '') if request else '')[:300],
        )
        # Opportunistic retention pruning (~1 in 100 writes) so the table
        # can't grow unbounded on the free-tier database without a cron job.
        if random.randint(1, 100) == 1:
            cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
            ActivityLog.objects.filter(timestamp__lt=cutoff).delete()
    except Exception:
        pass


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    # Seed the idle clock so a stale pre-login session can't expire the
    # fresh login instantly (IdleTimeoutMiddleware reads this key).
    if request is not None:
        request.session['last_activity'] = time.time()
    log_activity(request, 'login', user=user)


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    if user is None:
        return  # anonymous hit on the logout URL — nothing to record
    if request is not None and getattr(request, '_auto_logout', False):
        return  # IdleTimeoutMiddleware already wrote an 'auto_logout' row
    log_activity(request, 'logout', user=user)


@receiver(user_login_failed)
def on_user_login_failed(sender, credentials, request=None, **kwargs):
    log_activity(request, 'login_failed',
                 username=str(credentials.get('username', ''))[:150])
