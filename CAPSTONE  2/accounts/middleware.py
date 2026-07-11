from django.shortcuts import redirect


class EmailVerificationRequiredMiddleware:
    """Patients who self-registered with a password are fully blocked until
    they click the link emailed to them: every page redirects to the
    'check your email' waiting page except the verification flow itself and
    logout. Staff roles and Google sign-ups (created with
    email_verified=True) never hit this. Must sit after
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
