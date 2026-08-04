import time

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .forms import (
    PatientRegistrationForm, PatientOnboardingForm, PatientProfileEditForm, DoctorProfileEditForm,
    SecretaryProfileEditForm, ProfilePictureForm, EmailNotificationSettingsForm, DeactivateAccountForm,
    ForgotPasswordForm, SetCredentialsForm,
)
from .models import CustomUser, PatientProfile, DoctorProfile, SecretaryProfile
from .decorators import role_required
from .social_auth import provider_is_configured
from .signals import log_activity
from .otp import issue_and_send_email_otp, verify_code, MAX_OTP_ATTEMPTS
from .passwords import generate_temp_password
from notifications.email_utils import (
    send_password_changed_email, send_account_deactivated_email,
    send_password_reset_email,
)
from notifications.models import Notification


def signup_redirect(request):
    """Redirect /signup/ to /register/ for backwards compatibility"""
    return redirect('accounts:register')


def _social_providers():
    """Which social sign-in buttons the login/register card should render as
    real links vs. the disabled 'Coming soon' placeholders."""
    return {
        'google': provider_is_configured('google'),
        'facebook': provider_is_configured('facebook'),
    }


def _notify_admins(message):
    """New patient self-registrations happen with nobody on staff in the
    loop, unlike doctor/secretary accounts which admins create themselves.
    Let every admin account know one landed."""
    for admin_user in CustomUser.objects.filter(role='admin'):
        Notification.objects.create(user=admin_user, message=message)


def login_view(request):
    if request.user.is_authenticated:
        return _role_redirect(request.user)
    if request.GET.get('expired'):
        messages.info(request, 'You were logged out due to inactivity. Please log in again.')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return _role_redirect(user)
        messages.error(request, 'Invalid username or password.')
    return render(request, 'accounts/register.html', {
        'register_form': PatientRegistrationForm(),
        'active_panel': 'login',
        'social_providers': _social_providers(),
    })


def logout_view(request):
    if request.method == 'POST':
        logout(request)
    return redirect('accounts:login')


def register_view(request):
    if request.user.is_authenticated:
        return _role_redirect(request.user)
    form = PatientRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        if not settings.EMAIL_VERIFICATION_REQUIRED:
            # Gate disabled (e.g. while email delivery is down): the account
            # counts as verified so re-enabling the gate later can't lock
            # out people who registered during the outage.
            user.email_verified = True
            user.save(update_fields=['email_verified'])
        login(request, user)
        _notify_admins(f"New patient account created: {user.get_full_name() or user.username} ({user.username}).")
        if settings.EMAIL_VERIFICATION_REQUIRED:
            issue_and_send_email_otp(user)
            messages.success(request, 'Account created! Please confirm your email to continue.')
            return redirect('accounts:verify_email_pending')
        messages.success(request, 'Account created! Welcome to MSHFI.')
        return redirect('accounts:complete_profile')
    return render(request, 'accounts/register.html', {
        'register_form': form,
        'active_panel': 'register',
        'social_providers': _social_providers(),
    })


FORGOT_SESSION_KEY = 'forgot_password_last_sent'
FORGOT_COOLDOWN_SECONDS = 60
# One fixed reply for every outcome — matched, unmatched, throttled, or a
# mail-send failure. Anything that varies by outcome tells a stranger which
# email addresses have accounts here.
FORGOT_GENERIC_MESSAGE = (
    "If an account exists for that email, we've sent a new password to it. "
    "Please check your inbox and your spam folder."
)


def forgot_password_view(request):
    """Login card's 'Forgot password?' panel. Generates a fresh random
    password, emails it, and only then saves it — see
    send_password_reset_email for why that order matters."""
    if request.user.is_authenticated:
        return _role_redirect(request.user)

    form = ForgotPasswordForm(request.POST or None)
    sent = False
    if request.method == 'POST' and form.is_valid():
        last_sent = request.session.get(FORGOT_SESSION_KEY, 0)
        if time.time() - last_sent >= FORGOT_COOLDOWN_SECONDS:
            request.session[FORGOT_SESSION_KEY] = time.time()
            _reset_and_email_password(request, form.cleaned_data['email'])
        sent = True
        messages.success(request, FORGOT_GENERIC_MESSAGE)

    return render(request, 'accounts/register.html', {
        'register_form': PatientRegistrationForm(),
        'forgot_form': form,
        'forgot_sent': sent,
        'active_panel': 'forgot',
        'social_providers': _social_providers(),
    })


def _reset_and_email_password(request, email):
    """Email has no unique constraint on CustomUser (staff-registered
    walk-ins may even share or omit one), so reset every active account on
    the address and send one email each — each names its own username so
    the recipient can tell them apart."""
    for user in CustomUser.objects.filter(email__iexact=email, is_active=True):
        new_password = generate_temp_password()
        if send_password_reset_email(user, new_password):
            user.set_password(new_password)
            user.save(update_fields=['password'])
            log_activity(request, 'password_change', user=user)


RESEND_SESSION_KEY = 'verify_email_last_sent'
RESEND_COOLDOWN_SECONDS = 60
POLL_SESSION_KEY = 'verify_poll_started'
# Abandoned waiting tabs would otherwise poll the server forever; after this
# long the status endpoint replies 286, which tells htmx to stop polling.
POLL_TIMEOUT_SECONDS = 120


@login_required(login_url='/accounts/login/')
def verify_email_pending_view(request):
    """The 'Enter your code' page — renders the OTP-entry form. Each render
    restarts the 2-minute polling window used by verify_email_status_view
    (kept for IdleTimeoutMiddleware's non-activity check, though its
    cross-device auto-advance no longer applies to the OTP flow)."""
    if request.user.email_verified:
        return redirect('accounts:complete_profile')
    request.session[POLL_SESSION_KEY] = time.time()
    return render(request, 'accounts/verify_email_pending.html')


@login_required(login_url='/accounts/login/')
def verify_email_status_view(request):
    """htmx polling target for the waiting page. 204 = keep waiting;
    once verified, an HX-Redirect moves the original tab onward; after
    POLL_TIMEOUT_SECONDS a 286 stops htmx polling and swaps in the
    timed-out fragment (a missing timer counts as timed out, so stale
    pollers from before a restart also stop)."""
    if request.user.email_verified:
        response = HttpResponse()
        response['HX-Redirect'] = '/accounts/complete-profile/'
        return response
    started = request.session.get(POLL_SESSION_KEY, 0)
    if time.time() - started > POLL_TIMEOUT_SECONDS:
        return render(request, 'accounts/_verify_poll_expired.html', status=286)
    return HttpResponse(status=204)


@login_required(login_url='/accounts/login/')
def verify_email_confirm_view(request):
    """Target of the OTP-entry form on the pending page. Acts only on
    request.user — never a target user chosen by the request — which is
    what makes a 6-digit code acceptable: brute-forcing it requires an
    already-authenticated session for that account. One consequence: unlike
    the old link, this can't be completed from a different device/tab than
    the one used to sign up."""
    if request.method != 'POST':
        return redirect('accounts:verify_email_pending')

    outcome = verify_code(request.user, request.POST.get('code', '').strip())
    if outcome == 'ok':
        messages.success(request, 'Email confirmed! Let\'s finish setting up your account.')
        return redirect('accounts:complete_profile')
    if outcome == 'expired':
        messages.error(request, 'That code has expired. Press Resend to get a new one.')
    elif outcome == 'locked':
        messages.error(request, 'Too many incorrect attempts. Press Resend to get a new code.')
    else:
        remaining = MAX_OTP_ATTEMPTS - request.user.email_otp_attempts
        messages.error(request, f'Incorrect code. {remaining} attempt(s) remaining.')
    return redirect('accounts:verify_email_pending')


@login_required(login_url='/accounts/login/')
def resend_verification_view(request):
    if request.method != 'POST':
        return redirect('accounts:verify_email_pending')
    if request.user.email_verified:
        return redirect('accounts:complete_profile')
    last_sent = request.session.get(RESEND_SESSION_KEY, 0)
    if time.time() - last_sent < RESEND_COOLDOWN_SECONDS:
        messages.info(request, 'A verification code was just sent. Please wait a minute before trying again.')
    else:
        issue_and_send_email_otp(request.user)
        request.session[RESEND_SESSION_KEY] = time.time()
        messages.success(request, f'Verification code sent to {request.user.email}.')
    return redirect('accounts:verify_email_pending')


PROFILE_VIEW_TEMPLATES = {
    'patient': 'accounts/profile_view_patient.html',
    'doctor': 'accounts/profile_view_doctor.html',
    'secretary': 'accounts/profile_view_secretary.html',
    'admin': 'accounts/profile_view_admin.html',
}

PROFILE_EDIT_TEMPLATES = {
    'patient': 'accounts/profile_edit_patient.html',
    'doctor': 'accounts/profile_edit_doctor.html',
    'secretary': 'accounts/profile_edit_secretary.html',
    'admin': 'accounts/profile_edit_admin.html',
}


@role_required('patient', 'doctor', 'secretary', 'admin')
def profile_view(request):
    profile = _get_profile(request.user)
    template = PROFILE_VIEW_TEMPLATES.get(request.user.role, 'accounts/profile_view_patient.html')
    return render(request, template, {'profile': profile})


@role_required('patient', 'doctor', 'secretary', 'admin')
def profile_edit_view(request):
    profile = _get_profile(request.user)
    FormClass = _get_profile_form(request.user)
    pic_form = ProfilePictureForm(request.POST or None, request.FILES or None, instance=request.user)
    template = PROFILE_EDIT_TEMPLATES.get(request.user.role, 'accounts/profile_edit_patient.html')
    modal_template = 'accounts/_profile_edit_modal.html'
    if FormClass is None:
        if request.method == 'POST' and pic_form.is_valid():
            pic_form.save()
            messages.success(request, 'Profile picture updated.')
            if request.htmx:
                response = render(request, modal_template, {'form': None, 'pic_form': pic_form, 'title': 'Edit Profile'})
                response['HX-Redirect'] = '/accounts/profile/'
                return response
            return redirect('accounts:profile_view')
        if request.htmx:
            return render(request, modal_template, {'form': None, 'pic_form': pic_form, 'title': 'Edit Profile'})
        return render(request, template, {'form': None, 'pic_form': pic_form})
    form = FormClass(request.POST or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        # Also update first/last name on the user object
        first = request.POST.get('first_name', '').strip()
        last  = request.POST.get('last_name', '').strip()
        if first:
            request.user.first_name = first
        if last:
            request.user.last_name = last
        request.user.save()
        form.save()
        # The picture upload is validated/saved independently: a rejected
        # photo (bad format, too large, etc.) must never discard the just
        # saved profile fields above, which is what happened when both
        # forms were required to be valid together — the whole POST would
        # silently no-op and the page would redisplay the typed values as
        # if they'd been saved, even though nothing reached the database.
        if pic_form.is_valid():
            pic_form.save()
            messages.success(request, 'Profile updated.')
        else:
            messages.warning(
                request,
                'Profile updated, but the profile picture could not be saved: '
                + ' '.join(pic_form.errors.get('profile_picture', ['Invalid file.']))
            )
        if request.htmx:
            response = render(request, modal_template, {'form': form, 'pic_form': pic_form, 'title': 'Edit Profile'})
            response['HX-Redirect'] = '/accounts/profile/'
            return response
        return redirect('accounts:profile_view')
    if request.htmx:
        return render(request, modal_template, {'form': form, 'pic_form': pic_form, 'title': 'Edit Profile'})
    return render(request, template, {'form': form, 'pic_form': pic_form})


@role_required('patient')
def set_credentials_view(request):
    """Mandatory stop between email verification and Complete Your Profile
    for patients who signed up via Google (social_views.py's Case C leaves
    them with set_unusable_password() and an auto-generated username, so
    there's no username/password combo that works on a device where
    they're not already signed into that Google account). Deliberately has
    no skip link — complete_profile_view's gate below is what funnels every
    onboarding path through here exactly once."""
    if request.user.has_usable_password():
        # Already done (or a password-signup patient who should never see
        # this at all) — nothing to collect.
        return redirect('accounts:complete_profile')

    form = SetCredentialsForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        # Mirrors password_change_view: set_password() rotates the session
        # auth hash, so without this the user gets logged out mid-onboarding
        # right after typing their new password in.
        update_session_auth_hash(request, user)
        log_activity(request, 'password_change', user=user)
        send_password_changed_email(user)
        messages.success(request, 'Your username and password are set.')
        return redirect('accounts:complete_profile')
    return render(request, 'accounts/set_credentials.html', {'form': form})


@role_required('patient')
def complete_profile_view(request):
    """Shown right after a brand-new patient account is created (regular
    sign-up or first-time Google sign-in) to collect Name and Address —
    the info that used to be gathered at sign-up time, now collected right
    after instead so the sign-up form itself can stay to just Username /
    Email / Password."""
    if not request.user.has_usable_password():
        # Google sign-up who hasn't set real credentials yet — finish that
        # first. Covers every path that lands here (OTP gate on/off, the
        # htmx OTP-status redirect); password-signup patients already have
        # a usable password and fall straight through.
        return redirect('accounts:set_credentials')

    profile = _get_profile(request.user)
    if profile is None:
        return redirect('patient:dashboard')

    # Already filled in (e.g. someone revisits this URL after finishing it,
    # or hits Back) — nothing more to collect, send them on their way.
    if request.method == 'GET' and profile.address:
        return redirect('patient:dashboard')

    form = PatientOnboardingForm(request.POST or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        first = request.POST.get('first_name', '').strip()
        last  = request.POST.get('last_name', '').strip()
        if first:
            request.user.first_name = first
        if last:
            request.user.last_name = last
        request.user.save()
        form.save()
        messages.success(request, 'Thanks! Your profile is all set.')
        return redirect('patient:dashboard')
    return render(request, 'accounts/complete_profile.html', {'form': form})


SETTINGS_TEMPLATES = {
    'patient': 'accounts/settings_patient.html',
    'doctor': 'accounts/settings_doctor.html',
    'secretary': 'accounts/settings_secretary.html',
    'admin': 'accounts/settings_admin.html',
}

HELP_TEMPLATES = {
    'patient': 'accounts/help_patient.html',
    'doctor': 'accounts/help_doctor.html',
    'secretary': 'accounts/help_secretary.html',
    'admin': 'accounts/help_admin.html',
}


@role_required('patient', 'doctor', 'secretary', 'admin')
def settings_view(request):
    if request.method == 'POST':
        form = EmailNotificationSettingsForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Settings updated.')
            return redirect('accounts:settings')
    else:
        form = EmailNotificationSettingsForm(instance=request.user)
    template = SETTINGS_TEMPLATES.get(request.user.role, 'accounts/settings_patient.html')
    context = {
        'form': form,
        'password_form': (PasswordChangeForm if request.user.has_usable_password() else SetPasswordForm)(request.user),
        'deactivate_form': DeactivateAccountForm(user=request.user),
        'activity_logs': request.user.activity_logs.all()[:10],
    }
    return render(request, template, context)


@role_required('patient', 'doctor', 'secretary', 'admin')
def password_change_view(request):
    """Handles both 'change my password' (has one already) and 'set a
    password' (Google-linked patients who've never had one) — same form
    swap logic as settings_view uses to render the field set."""
    form_class = PasswordChangeForm if request.user.has_usable_password() else SetPasswordForm
    if request.method == 'POST':
        form = form_class(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            log_activity(request, 'password_change', user=user)
            send_password_changed_email(user)
            messages.success(request, 'Your password has been updated.')
            return redirect('accounts:settings')
        messages.error(request, 'Please fix the errors below.')
    template = SETTINGS_TEMPLATES.get(request.user.role, 'accounts/settings_patient.html')
    context = {
        'form': EmailNotificationSettingsForm(instance=request.user),
        'password_form': form,
        'deactivate_form': DeactivateAccountForm(user=request.user),
        'activity_logs': request.user.activity_logs.all()[:10],
        'password_form_open': True,
    }
    return render(request, template, context)


@role_required('patient', 'doctor', 'secretary', 'admin')
def deactivate_account_view(request):
    if request.method != 'POST':
        return redirect('accounts:settings')
    form = DeactivateAccountForm(request.POST, user=request.user)
    if form.is_valid():
        user = request.user
        user.is_active = False
        user.save(update_fields=['is_active'])
        log_activity(request, 'account_deactivated', user=user)
        send_account_deactivated_email(user)
        logout(request)
        messages.info(request, 'Your account has been deactivated. Contact the clinic staff if you want it reactivated.')
        return redirect('accounts:login')
    messages.error(request, form.errors.get('password', form.errors.get('confirm', ['Could not deactivate your account.']))[0])
    template = SETTINGS_TEMPLATES.get(request.user.role, 'accounts/settings_patient.html')
    context = {
        'form': EmailNotificationSettingsForm(instance=request.user),
        'password_form': (PasswordChangeForm if request.user.has_usable_password() else SetPasswordForm)(request.user),
        'deactivate_form': form,
        'activity_logs': request.user.activity_logs.all()[:10],
        'deactivate_form_open': True,
    }
    return render(request, template, context)


@role_required('patient', 'doctor', 'secretary', 'admin')
def help_view(request):
    template = HELP_TEMPLATES.get(request.user.role, 'accounts/help_patient.html')
    return render(request, template)


def _role_redirect(user):
    mapping = {
        'patient':   '/patient/',
        'doctor':    '/doctor/',
        'secretary': '/secretary/',
        'admin':     '/admin-panel/',
    }
    from django.shortcuts import redirect as _redirect
    return _redirect(mapping.get(user.role, '/'))


def _get_profile(user):
    if user.role == 'patient':
        return getattr(user, 'patient_profile', None)
    if user.role == 'doctor':
        return getattr(user, 'doctor_profile', None)
    if user.role == 'secretary':
        return getattr(user, 'secretary_profile', None)
    return None


def _get_profile_form(user):
    if user.role == 'patient':
        return PatientProfileEditForm
    if user.role == 'doctor':
        return DoctorProfileEditForm
    if user.role == 'secretary':
        return SecretaryProfileEditForm
    return None
