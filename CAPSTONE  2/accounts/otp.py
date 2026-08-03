"""6-digit OTP email verification (GCash-style code entry, replacing the
old signed-link flow in the now-removed accounts/tokens.py).

The code is stored plaintext on CustomUser rather than hashed: it lives for
only OTP_TTL_SECONDS, is cleared the moment it's used, and a DB compromise
already exposes far more sensitive data than this code. Swap in
django.contrib.auth.hashers.make_password/check_password here if that
tradeoff ever needs revisiting.
"""
import secrets

from django.utils import timezone
from datetime import timedelta

from notifications.email_utils import send_verification_email

OTP_TTL_SECONDS = 10 * 60
MAX_OTP_ATTEMPTS = 5


def generate_code():
    return f'{secrets.randbelow(1_000_000):06d}'


def issue_and_send_email_otp(user):
    """Single entry point used by registration, resend, and Google sign-up.
    Overwriting email_otp on every call means resending automatically
    invalidates whatever code was issued before it."""
    code = generate_code()
    user.email_otp = code
    user.email_otp_expires_at = timezone.now() + timedelta(seconds=OTP_TTL_SECONDS)
    user.email_otp_attempts = 0
    user.save(update_fields=['email_otp', 'email_otp_expires_at', 'email_otp_attempts'])
    send_verification_email(user, code, ttl_minutes=OTP_TTL_SECONDS // 60)


def verify_code(user, submitted):
    """Returns 'ok' | 'expired' | 'invalid' | 'locked'. Only ever called on
    request.user (never a target user chosen by the caller) — that's what
    makes a 6-digit space acceptable, since brute-forcing it already
    requires an authenticated session for the account."""
    if not user.email_otp or not user.email_otp_expires_at or timezone.now() >= user.email_otp_expires_at:
        return 'expired'
    if user.email_otp_attempts >= MAX_OTP_ATTEMPTS:
        return 'locked'
    if secrets.compare_digest(user.email_otp, submitted):
        user.email_verified = True
        user.email_otp = ''
        user.email_otp_expires_at = None
        user.email_otp_attempts = 0
        user.save(update_fields=['email_verified', 'email_otp', 'email_otp_expires_at', 'email_otp_attempts'])
        return 'ok'
    user.email_otp_attempts += 1
    user.save(update_fields=['email_otp_attempts'])
    return 'invalid'
