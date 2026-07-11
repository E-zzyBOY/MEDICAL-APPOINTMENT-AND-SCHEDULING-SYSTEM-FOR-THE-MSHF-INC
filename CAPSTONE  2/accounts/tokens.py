"""Signed, self-expiring tokens for the email-verification link.

django.core.signing carries the payload inside the token itself, so no
database table is needed and tokens survive across processes/dynos. A token
stops working when it expires, when SECRET_KEY changes, or when the user
changes their email address (the signed email must still match).
"""
from django.core import signing

from .models import CustomUser

SALT = 'accounts.email-verify'
MAX_AGE_SECONDS = 60 * 60  # links are good for 1 hour; Resend issues a fresh one


def make_email_verify_token(user):
    return signing.dumps({'uid': user.pk, 'email': user.email}, salt=SALT)


def read_email_verify_token(token):
    """Return the CustomUser the token was issued to, or None if the token
    is malformed, expired, or no longer matches the account's email."""
    try:
        payload = signing.loads(token, salt=SALT, max_age=MAX_AGE_SECONDS)
    except signing.BadSignature:
        return None
    user = CustomUser.objects.filter(pk=payload.get('uid')).first()
    if user is None or user.email != payload.get('email'):
        return None
    return user
