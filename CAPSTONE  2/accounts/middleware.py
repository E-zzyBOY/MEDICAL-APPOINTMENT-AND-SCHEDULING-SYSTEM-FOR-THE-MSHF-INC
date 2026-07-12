import time

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect


class EmailVerificationRequiredMiddleware:
    """Self-registered patients (password or Google sign-up) are fully
    blocked until they click the link emailed to them: every page redirects
    to the 'check your email' waiting page except the verification flow
    itself and logout. Staff roles never hit this. Must sit after
    AuthenticationMiddleware in settings.MIDDLEWARE."""

    ALLOWED_PREFIXES = (
        '/accounts/verify-email/',  # pending page, status poll, resend, link target
        '/accounts/logout/',
        '/static/',
        '/media/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.EMAIL_VERIFICATION_REQUIRED:
            return self.get_response(request)
        user = request.user
        # is_superuser is excluded because `createsuperuser` (e.g. the one
        # build.sh runs on Render) leaves role at its 'patient' default and
        # never goes through the email-confirmation flow.
        if (
            user.is_authenticated
            and user.role == 'patient'
            and not user.is_superuser
            and not user.email_verified
            and not request.path.startswith(self.ALLOWED_PREFIXES)
        ):
            return redirect('accounts:verify_email_pending')
        return self.get_response(request)


class IdleTimeoutMiddleware:
    """Logs the user out after settings.IDLE_TIMEOUT_SECONDS without real
    activity and records an 'auto_logout' ActivityLog row. Background polls
    (React dashboard widgets, the verify-email status check) are still
    checked for expiry but never refresh the idle clock — otherwise a
    dashboard left open would stay 'active' forever. Writing last_activity
    marks the session modified, which also refreshes the SESSION_COOKIE_AGE
    expiry, so the DB session dies on the same sliding 1-hour window. Must
    sit after AuthenticationMiddleware in settings.MIDDLEWARE."""

    LOGIN_URL_EXPIRED = '/accounts/login/?expired=1'
    # Checked for expiry, but requests here don't count as user activity.
    NON_ACTIVITY_SUFFIXES = ('/dashboard/data/',)
    NON_ACTIVITY_PREFIXES = ('/accounts/verify-email/status/', '/static/', '/media/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = time.time()
            last = request.session.get('last_activity', now)
            if now - last > settings.IDLE_TIMEOUT_SECONDS:
                from .signals import log_activity
                log_activity(request, 'auto_logout', user=request.user)
                request._auto_logout = True  # stops the user_logged_out receiver double-logging
                logout(request)
                return self._expired_response(request)
            if not self._is_background(request.path):
                request.session['last_activity'] = now
        return self.get_response(request)

    def _is_background(self, path):
        return (path.endswith(self.NON_ACTIVITY_SUFFIXES)
                or path.startswith(self.NON_ACTIVITY_PREFIXES))

    def _expired_response(self, request):
        if request.headers.get('HX-Request'):
            # HTMX performs a full-page redirect when it sees HX-Redirect,
            # instead of swapping the login page into a fragment.
            response = HttpResponse(status=204)
            response['HX-Redirect'] = self.LOGIN_URL_EXPIRED
            return response
        if request.path.endswith(self.NON_ACTIVITY_SUFFIXES):
            # React dashboard poll: the hook ignores non-OK responses, so
            # the widgets just freeze until the user navigates.
            return JsonResponse({'expired': True}, status=401)
        return redirect(self.LOGIN_URL_EXPIRED)


class NoCacheMiddleware:
    """Forces the browser to revalidate with the server instead of serving a
    page from disk/back-forward cache, so the Back button after logout hits
    role_required/RoleRequiredMixin again rather than showing a stale page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith('/static/') and not request.path.startswith('/media/'):
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response
