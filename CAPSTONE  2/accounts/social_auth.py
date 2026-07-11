"""Hand-rolled server-side OAuth 2.0 Authorization Code client.

Deliberately NOT django-allauth or a social-auth package: the login page is
a single custom sliding-panel card, and all we need is the redirect flow —
build an authorization URL, exchange the one-time code, fetch the profile.
Everything here is Python standard library (urllib), no new dependencies.

The browser only ever carries the redirect and the one-time ``code``; this
module talks to the provider directly over HTTPS from the server, so the
returned profile can be trusted without client-side JWT verification.

Only Google is enabled today. Facebook is deferred until the Meta app-review
/ HTTPS-redirect requirements are sorted out — adding it later means adding
an entry to PROVIDERS plus its endpoints in the two provider branches below
(see docs/social-login-setup.md).
"""
import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

# Single source of truth for which providers are live. Views reject anything
# not listed here, so /accounts/social/facebook/... stays inert until the
# day 'facebook' joins this tuple.
PROVIDERS = ('google',)

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'

HTTP_TIMEOUT_SECONDS = 10


class SocialAuthError(Exception):
    """Raised for any provider-side failure. The message is safe to show to
    the user; raw provider responses only ever go to the log."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def provider_is_configured(provider):
    """True only when the provider is enabled AND both its client id and
    secret are present — half-configured providers stay hidden."""
    if provider not in PROVIDERS:
        return False
    if provider == 'google':
        return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)
    return False


def generate_state():
    return secrets.token_urlsafe(32)


def build_authorization_url(provider, redirect_uri, state):
    if provider == 'google':
        params = {
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'openid email profile',
            'state': state,
            # Always show the account chooser — shared/family computers are
            # the norm for this clinic's patients.
            'prompt': 'select_account',
        }
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    raise SocialAuthError('Unsupported sign-in provider.')


def fetch_user_profile(provider, code, redirect_uri):
    """Exchanges the authorization code for the user's profile, normalized to
    {provider_user_id, email, email_verified, first_name, last_name}."""
    if provider == 'google':
        return _fetch_google_profile(code, redirect_uri)
    raise SocialAuthError('Unsupported sign-in provider.')


def _fetch_google_profile(code, redirect_uri):
    token_data = _http_json(
        'google',
        urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=urllib.parse.urlencode({
                'code': code,
                'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
                'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code',
            }).encode(),
        ),
    )
    access_token = token_data.get('access_token')
    if not access_token:
        logger.warning('Google token response had no access_token: keys=%s', list(token_data))
        raise SocialAuthError('Google sign-in failed. Please try again.')

    userinfo = _http_json(
        'google',
        urllib.request.Request(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
        ),
    )
    provider_user_id = userinfo.get('sub')
    if not provider_user_id:
        logger.warning('Google userinfo response had no sub: keys=%s', list(userinfo))
        raise SocialAuthError('Google sign-in failed. Please try again.')

    return {
        'provider_user_id': str(provider_user_id),
        'email': (userinfo.get('email') or '').strip(),
        'email_verified': bool(userinfo.get('email_verified')),
        'first_name': (userinfo.get('given_name') or '').strip(),
        'last_name': (userinfo.get('family_name') or '').strip(),
        # Google avatar URL (lh3.googleusercontent.com/...); may be absent.
        'picture': (userinfo.get('picture') or '').strip(),
    }


# Avatars bigger than this are almost certainly not avatars; refuse rather
# than store megabytes of who-knows-what against a brand-new account.
AVATAR_MAX_BYTES = 2 * 1024 * 1024

# SSRF guard: only fetch avatars from the provider's own image CDN. The URL
# comes from the provider's authenticated userinfo response, but treating it
# as untrusted costs nothing.
AVATAR_ALLOWED_HOST_SUFFIXES = {
    'google': ('googleusercontent.com',),
}


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    # A redirect could hop off the allowlisted host, so don't follow any.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _avatar_host_allowed(provider, url):
    host = (urllib.parse.urlsplit(url).hostname or '').rstrip('.').lower()
    return any(
        host == suffix or host.endswith('.' + suffix)
        for suffix in AVATAR_ALLOWED_HOST_SUFFIXES.get(provider, ())
    )


def fetch_provider_avatar(provider, url):
    """Best-effort download of the provider's avatar image. Returns the raw
    bytes, or None on ANY failure — a missing avatar must never break or
    slow down sign-in beyond the request timeout."""
    if not url or not url.startswith('https://') or not _avatar_host_allowed(provider, url):
        return None
    try:
        opener = urllib.request.build_opener(_NoRedirects())
        with opener.open(url, timeout=HTTP_TIMEOUT_SECONDS) as response:
            data = response.read(AVATAR_MAX_BYTES + 1)
        if not data or len(data) > AVATAR_MAX_BYTES:
            return None
        # Confirm the bytes really are an image before they get stored and
        # served back to browsers as one.
        from io import BytesIO

        from PIL import Image

        Image.open(BytesIO(data)).verify()
        return data
    except Exception as exc:  # noqa: BLE001 - by design: avatar is optional
        logger.info('Avatar download failed (%s): %s', url, exc)
        return None


def _http_json(provider, request):
    """Performs one provider HTTP call, returning the decoded JSON body.
    Every failure mode collapses into SocialAuthError with a user-safe
    message; the interesting details go to the log only."""
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        # Read the body for the log, but never surface it to the browser.
        try:
            body = exc.read().decode('utf-8', errors='replace')[:2000]
        except Exception:
            body = '<unreadable>'
        logger.warning('%s OAuth call failed: HTTP %s %s — %s', provider, exc.code, request.full_url, body)
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.warning('%s OAuth call failed: %s — %s', provider, request.full_url, exc)
    except (ValueError, UnicodeDecodeError) as exc:
        logger.warning('%s OAuth call returned invalid JSON: %s — %s', provider, request.full_url, exc)
    raise SocialAuthError(
        f'Could not reach {provider.title()} to complete sign-in. Please try again.'
    )
