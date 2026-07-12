import time

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .forms import (
    PatientRegistrationForm, PatientOnboardingForm, PatientProfileEditForm, DoctorProfileEditForm,
    SecretaryProfileEditForm, ProfilePictureForm, EmailNotificationSettingsForm,
)
from .models import CustomUser, PatientProfile, DoctorProfile, SecretaryProfile
from .decorators import role_required
from .social_auth import provider_is_configured
from .tokens import read_email_verify_token
from notifications.email_utils import send_verification_email
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
            send_verification_email(user, request)
            messages.success(request, 'Account created! Please confirm your email to continue.')
            return redirect('accounts:verify_email_pending')
        messages.success(request, 'Account created! Welcome to MSHFI.')
        return redirect('accounts:complete_profile')
    return render(request, 'accounts/register.html', {
        'register_form': form,
        'active_panel': 'register',
        'social_providers': _social_providers(),
    })


RESEND_SESSION_KEY = 'verify_email_last_sent'
RESEND_COOLDOWN_SECONDS = 60
POLL_SESSION_KEY = 'verify_poll_started'
# Abandoned waiting tabs would otherwise poll the server forever; after this
# long the status endpoint replies 286, which tells htmx to stop polling.
POLL_TIMEOUT_SECONDS = 120


@login_required(login_url='/accounts/login/')
def verify_email_pending_view(request):
    """The 'Check your email' waiting page. Polls verify_email_status via
    htmx and auto-advances the moment the link is clicked anywhere. Each
    render restarts the 2-minute polling window."""
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


def verify_email_view(request, token):
    """Target of the link in the confirmation email. Public on purpose —
    the link is often opened on a phone or another browser with no session;
    the signed token itself proves control of the inbox."""
    user = read_email_verify_token(token)
    if user is None:
        messages.error(request, 'This confirmation link is invalid or has expired. Please request a new one.')
        if request.user.is_authenticated and not request.user.email_verified:
            return redirect('accounts:verify_email_pending')
        return redirect('accounts:login')

    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=['email_verified'])

    if request.user.is_authenticated and request.user.pk == user.pk:
        messages.success(request, 'Email confirmed! Let\'s finish setting up your account.')
        return redirect('accounts:complete_profile')
    messages.success(request, 'Email confirmed! You can continue on the tab where you signed up, or log in here.')
    return redirect('accounts:login')


@login_required(login_url='/accounts/login/')
def resend_verification_view(request):
    if request.method != 'POST':
        return redirect('accounts:verify_email_pending')
    if request.user.email_verified:
        return redirect('accounts:complete_profile')
    last_sent = request.session.get(RESEND_SESSION_KEY, 0)
    if time.time() - last_sent < RESEND_COOLDOWN_SECONDS:
        messages.info(request, 'A confirmation email was just sent. Please wait a minute before trying again.')
    else:
        send_verification_email(request.user, request)
        request.session[RESEND_SESSION_KEY] = time.time()
        messages.success(request, f'Confirmation email sent to {request.user.email}.')
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
    if request.method == 'POST' and form.is_valid() and pic_form.is_valid():
        # Also update first/last name on the user object
        first = request.POST.get('first_name', '').strip()
        last  = request.POST.get('last_name', '').strip()
        if first:
            request.user.first_name = first
        if last:
            request.user.last_name = last
        request.user.save()
        form.save()
        pic_form.save()
        messages.success(request, 'Profile updated.')
        if request.htmx:
            response = render(request, modal_template, {'form': form, 'pic_form': pic_form, 'title': 'Edit Profile'})
            response['HX-Redirect'] = '/accounts/profile/'
            return response
        return redirect('accounts:profile_view')
    if request.htmx:
        return render(request, modal_template, {'form': form, 'pic_form': pic_form, 'title': 'Edit Profile'})
    return render(request, template, {'form': form, 'pic_form': pic_form})


@role_required('patient')
def complete_profile_view(request):
    """Shown right after a brand-new patient account is created (regular
    sign-up or first-time Google sign-in) to collect Name and Address —
    the info that used to be gathered at sign-up time, now collected right
    after instead so the sign-up form itself can stay to just Username /
    Email / Password."""
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
    return render(request, template, {'form': form})


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
