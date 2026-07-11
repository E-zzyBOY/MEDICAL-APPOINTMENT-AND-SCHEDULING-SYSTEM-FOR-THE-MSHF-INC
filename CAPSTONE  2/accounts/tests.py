from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

# Note: rendering templates on Python 3.13+ (test client AND real pages like
# the Django admin changelist) depends on the compatibility patch applied in
# accounts.apps.AccountsConfig.ready() — see the comment there.

from .models import CustomUser, PatientProfile, SocialAccount
from .social_views import STATE_SESSION_KEY
from notifications.models import Notification

# Every callback test overrides these so the Google provider counts as
# configured regardless of what's in the developer's local .env.
GOOGLE_CONFIGURED = {
    'GOOGLE_OAUTH_CLIENT_ID': 'test-client-id',
    'GOOGLE_OAUTH_CLIENT_SECRET': 'test-client-secret',
}

# What accounts.social_auth.fetch_user_profile would return for a normal
# Google account. Individual tests override fields as needed.
GOOGLE_PROFILE = {
    'provider_user_id': '108234567890',
    'email': 'juan.delacruz@gmail.com',
    'email_verified': True,
    'first_name': 'Juan',
    'last_name': 'Dela Cruz',
}


class SocialLoginTestBase(TestCase):
    def setUp(self):
        self.client = Client()
        self.start_url = reverse('accounts:social_start', args=['google'])
        self.callback_url = reverse('accounts:social_callback', args=['google'])

    def _prime_state(self, provider='google', value='teststate123'):
        session = self.client.session
        session[STATE_SESSION_KEY] = {'provider': provider, 'value': value}
        session.save()
        return value

    def _callback(self, profile=None, state='teststate123', code='authcode'):
        """Primes session state and hits the callback with fetch_user_profile
        mocked out — the only network-touching piece of the flow."""
        self._prime_state(value=state)
        with patch('accounts.social_views.fetch_user_profile', return_value=dict(profile or GOOGLE_PROFILE)):
            return self.client.get(self.callback_url, {'state': state, 'code': code})

    def _logged_in_user(self):
        session = self.client.session
        user_id = session.get('_auth_user_id')
        return CustomUser.objects.get(pk=user_id) if user_id else None


class SocialButtonVisibilityTests(SocialLoginTestBase):
    @override_settings(GOOGLE_OAUTH_CLIENT_ID='', GOOGLE_OAUTH_CLIENT_SECRET='')
    def test_google_button_disabled_when_unconfigured(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertNotContains(response, self.start_url)
        self.assertContains(response, 'Coming soon')

    @override_settings(**GOOGLE_CONFIGURED)
    def test_google_button_links_when_configured_facebook_stays_disabled(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertContains(response, self.start_url)
        # Facebook has no button at all until Meta app review is sorted out.
        self.assertNotContains(response, reverse('accounts:social_start', args=['facebook']))


class SocialStartTests(SocialLoginTestBase):
    @override_settings(**GOOGLE_CONFIGURED)
    def test_start_sets_state_and_redirects_to_google(self):
        response = self.client.get(self.start_url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('https://accounts.google.com/o/oauth2/v2/auth?'))
        stored = self.client.session.get(STATE_SESSION_KEY)
        self.assertEqual(stored['provider'], 'google')
        self.assertIn(stored['value'], response['Location'])

    @override_settings(GOOGLE_OAUTH_CLIENT_ID='', GOOGLE_OAUTH_CLIENT_SECRET='')
    def test_start_refused_when_unconfigured(self):
        response = self.client.get(self.start_url)
        self.assertRedirects(response, reverse('accounts:login'))

    @override_settings(**GOOGLE_CONFIGURED)
    def test_facebook_start_rejected_while_deferred(self):
        response = self.client.get(reverse('accounts:social_start', args=['facebook']))
        self.assertRedirects(response, reverse('accounts:login'))
        self.assertIsNone(self.client.session.get(STATE_SESSION_KEY))


@override_settings(**GOOGLE_CONFIGURED)
class SocialCallbackTests(SocialLoginTestBase):
    def test_state_mismatch_rejected(self):
        self._prime_state(value='expected-state')
        with patch('accounts.social_views.fetch_user_profile') as fetch:
            response = self.client.get(self.callback_url, {'state': 'tampered-state', 'code': 'authcode'})
        fetch.assert_not_called()
        self.assertRedirects(response, reverse('accounts:login'))
        self.assertIsNone(self._logged_in_user())

    def test_missing_state_rejected(self):
        # No session state at all (e.g. replayed callback URL).
        with patch('accounts.social_views.fetch_user_profile') as fetch:
            response = self.client.get(self.callback_url, {'state': 'anything', 'code': 'authcode'})
        fetch.assert_not_called()
        self.assertRedirects(response, reverse('accounts:login'))
        self.assertIsNone(self._logged_in_user())

    def test_state_is_single_use(self):
        self._callback()
        self.client.logout()
        # Same state again — the first callback consumed it.
        with patch('accounts.social_views.fetch_user_profile') as fetch:
            response = self.client.get(self.callback_url, {'state': 'teststate123', 'code': 'authcode'})
        fetch.assert_not_called()
        self.assertRedirects(response, reverse('accounts:login'))

    def test_user_cancelled_consent_returns_gracefully(self):
        self._prime_state()
        response = self.client.get(self.callback_url, {'error': 'access_denied'})
        self.assertRedirects(response, reverse('accounts:login'))
        self.assertIsNone(self._logged_in_user())

    def test_new_user_created_as_patient(self):
        from django.core import mail
        admin = CustomUser.objects.create_user(username='admin1', password='x', role='admin')
        response = self._callback()
        self.assertEqual(response.status_code, 302)
        # Brand-new social accounts get the same "was this really you?"
        # confirmation email as password sign-ups and start on the
        # waiting page.
        self.assertEqual(response['Location'], reverse('accounts:verify_email_pending'))

        user = CustomUser.objects.get(username='google-juan-delacruz')
        self.assertEqual(user.role, 'patient')
        self.assertEqual(user.email, GOOGLE_PROFILE['email'])
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [GOOGLE_PROFILE['email']])
        self.assertFalse(user.has_usable_password())
        self.assertEqual(self._logged_in_user(), user)

        profile = user.patient_profile
        self.assertEqual(profile.address, '')
        self.assertEqual(profile.place_of_birth, '')

        link = SocialAccount.objects.get(user=user)
        self.assertEqual(link.provider, 'google')
        self.assertEqual(link.provider_user_id, GOOGLE_PROFILE['provider_user_id'])
        self.assertEqual(link.email_at_link, GOOGLE_PROFILE['email'])

        self.assertTrue(
            Notification.objects.filter(user=admin, message__contains=user.username).exists()
        )

    def test_returning_user_logs_in_without_duplicates(self):
        self._callback()
        self.client.logout()
        response = self._callback(state='secondvisit')
        self.assertEqual(response['Location'], '/patient/')
        self.assertEqual(CustomUser.objects.filter(username__startswith='google-').count(), 1)
        self.assertEqual(SocialAccount.objects.count(), 1)
        self.assertIsNotNone(self._logged_in_user())

    def test_username_collision_gets_numeric_suffix(self):
        CustomUser.objects.create_user(username='google-juan-delacruz', password='x', role='patient')
        self._callback()
        self.assertTrue(CustomUser.objects.filter(username='google-juan-delacruz-2').exists())

    def test_staff_email_match_refused_not_linked(self):
        staff = CustomUser.objects.create_user(
            username='sec1', password='x', role='secretary', email=GOOGLE_PROFILE['email'],
        )
        response = self._callback()
        self.assertRedirects(response, reverse('accounts:login'))
        self.assertIsNone(self._logged_in_user())
        self.assertFalse(SocialAccount.objects.exists())
        # And no shadow patient account was created either.
        self.assertEqual(CustomUser.objects.count(), 1)

    def test_existing_patient_email_match_auto_linked(self):
        patient = CustomUser.objects.create_user(
            username='juan', password='x', role='patient', email=GOOGLE_PROFILE['email'].upper(),
            email_verified=True,  # realistic: existing accounts predate the gate
        )
        PatientProfile.objects.create(user=patient)
        response = self._callback()
        self.assertEqual(response['Location'], '/patient/')
        self.assertEqual(self._logged_in_user(), patient)
        link = SocialAccount.objects.get(user=patient)
        self.assertEqual(link.provider_user_id, GOOGLE_PROFILE['provider_user_id'])
        # Linked, not duplicated.
        self.assertEqual(CustomUser.objects.count(), 1)

    def test_unverified_email_refused_toward_manual_register(self):
        profile = dict(GOOGLE_PROFILE, email_verified=False)
        response = self._callback(profile=profile)
        self.assertRedirects(response, reverse('accounts:register'))
        self.assertIsNone(self._logged_in_user())
        self.assertFalse(CustomUser.objects.exists())

    def test_missing_email_refused_toward_manual_register(self):
        profile = dict(GOOGLE_PROFILE, email='')
        response = self._callback(profile=profile)
        self.assertRedirects(response, reverse('accounts:register'))
        self.assertIsNone(self._logged_in_user())
        self.assertFalse(CustomUser.objects.exists())

    def test_new_user_gets_google_avatar(self):
        import tempfile
        profile = dict(GOOGLE_PROFILE, picture='https://lh3.googleusercontent.com/a/test-avatar')
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                with patch('accounts.social_views.fetch_provider_avatar',
                           return_value=b'fake-image-bytes') as fetch_avatar:
                    self._callback(profile=profile)
        fetch_avatar.assert_called_once_with('google', profile['picture'])
        user = CustomUser.objects.get(username='google-juan-delacruz')
        self.assertTrue(user.profile_picture.name)
        self.assertIn('profile_pics/', user.profile_picture.name)

    def test_avatar_failure_does_not_break_signup(self):
        profile = dict(GOOGLE_PROFILE, picture='https://lh3.googleusercontent.com/a/test-avatar')
        with patch('accounts.social_views.fetch_provider_avatar', return_value=None):
            response = self._callback(profile=profile)
        self.assertEqual(response.status_code, 302)
        user = CustomUser.objects.get(username='google-juan-delacruz')
        self.assertFalse(user.profile_picture)

    def test_avatar_downloader_rejects_untrusted_hosts(self):
        # Host allowlist is checked before any network I/O, so these calls
        # are fully offline. Only the provider's own image CDN is allowed.
        from accounts.social_auth import fetch_provider_avatar
        self.assertIsNone(fetch_provider_avatar('google', 'https://evil.example.com/a.png'))
        self.assertIsNone(fetch_provider_avatar('google', 'https://googleusercontent.com.evil.example/a.png'))
        self.assertIsNone(fetch_provider_avatar('google', 'http://lh3.googleusercontent.com/a.png'))  # not https
        self.assertIsNone(fetch_provider_avatar('google', ''))

    def test_deactivated_linked_patient_cannot_log_in(self):
        self._callback()
        user = self._logged_in_user()
        self.client.logout()
        user.is_active = False
        user.save()
        response = self._callback(state='afterdeactivation')
        self.assertRedirects(response, reverse('accounts:login'))
        self.assertIsNone(self._logged_in_user())


class DjangoAdminSmokeTests(TestCase):
    """The Django admin user changelist crashed in production on Python 3.14
    (Django 4.2's BaseContext.__copy__ incompatibility, patched in
    accounts/apps.py). Keep a request against that exact page so a regression
    shows up in CI instead of on the deployed site."""

    def test_customuser_changelist_renders(self):
        CustomUser.objects.create_superuser(username='boss', password='x', email='boss@example.com')
        self.client.login(username='boss', password='x')
        response = self.client.get('/django-admin/accounts/customuser/')
        self.assertEqual(response.status_code, 200)


class EmailVerificationTests(TestCase):
    """Self sign-ups (password here; Google covered in the social tests
    above) are gated until the emailed confirmation link is clicked; the
    waiting page polls and auto-advances. Staff never see the gate."""

    REGISTER_DATA = {
        'username': 'newpatient',
        'email': 'newpatient@example.com',
        'password1': 'stray-hippo-42-lantern',
        'password2': 'stray-hippo-42-lantern',
    }

    def _register(self):
        return self.client.post(reverse('accounts:register'), self.REGISTER_DATA)

    def _verify_link_from_outbox(self):
        from django.core import mail
        import re
        body = mail.outbox[-1].body
        match = re.search(r'/accounts/verify-email/[^\s/]+/', body)
        self.assertIsNotNone(match, f'No verify link found in email body:\n{body}')
        return match.group(0)

    def test_register_sends_email_and_lands_on_waiting_page(self):
        from django.core import mail
        response = self._register()
        self.assertRedirects(response, reverse('accounts:verify_email_pending'))
        user = CustomUser.objects.get(username='newpatient')
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['newpatient@example.com'])
        self._verify_link_from_outbox()

    def test_unverified_patient_fully_blocked(self):
        self._register()
        for url in ('/patient/', reverse('accounts:complete_profile'), reverse('accounts:profile_view')):
            response = self.client.get(url)
            self.assertRedirects(
                response, reverse('accounts:verify_email_pending'),
                msg_prefix=f'{url} should be blocked until the email is confirmed',
            )

    def test_clicking_link_verifies_and_continues_to_setup(self):
        self._register()
        response = self.client.get(self._verify_link_from_outbox())
        self.assertRedirects(response, reverse('accounts:complete_profile'))
        user = CustomUser.objects.get(username='newpatient')
        self.assertTrue(user.email_verified)

    def test_link_clicked_on_another_device_still_verifies(self):
        self._register()
        link = self._verify_link_from_outbox()
        other_device = Client()
        response = other_device.get(link)
        self.assertRedirects(response, reverse('accounts:login'))
        self.assertTrue(CustomUser.objects.get(username='newpatient').email_verified)

    def test_garbage_token_rejected(self):
        self._register()
        response = self.client.get('/accounts/verify-email/not-a-real-token/')
        self.assertRedirects(response, reverse('accounts:verify_email_pending'))
        self.assertFalse(CustomUser.objects.get(username='newpatient').email_verified)

    def test_status_endpoint_polls_then_redirects(self):
        self._register()
        # Rendering the waiting page starts the 2-minute polling window.
        self.client.get(reverse('accounts:verify_email_pending'))
        response = self.client.get(reverse('accounts:verify_email_status'))
        self.assertEqual(response.status_code, 204)
        CustomUser.objects.filter(username='newpatient').update(email_verified=True)
        response = self.client.get(reverse('accounts:verify_email_status'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['HX-Redirect'], reverse('accounts:complete_profile'))

    def test_status_times_out_after_two_minutes(self):
        import time as time_module
        from accounts.views import POLL_SESSION_KEY, POLL_TIMEOUT_SECONDS
        self._register()
        self.client.get(reverse('accounts:verify_email_pending'))
        session = self.client.session
        session[POLL_SESSION_KEY] = time_module.time() - POLL_TIMEOUT_SECONDS - 1
        session.save()
        response = self.client.get(reverse('accounts:verify_email_status'))
        self.assertEqual(response.status_code, 286)  # htmx: stop polling
        self.assertContains(response, 'Waiting timed out', status_code=286)

    def test_status_without_timer_counts_as_timed_out(self):
        # Status hit without ever rendering the waiting page (stale poller
        # from before a restart, or a hand-crafted request) must not poll on.
        self._register()
        response = self.client.get(reverse('accounts:verify_email_status'))
        self.assertEqual(response.status_code, 286)

    def test_verified_wins_over_expired_timer(self):
        self._register()
        CustomUser.objects.filter(username='newpatient').update(email_verified=True)
        # No pending-page visit, so the timer is missing/expired — verified
        # still takes priority and redirects onward.
        response = self.client.get(reverse('accounts:verify_email_status'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['HX-Redirect'], reverse('accounts:complete_profile'))

    def test_pending_page_restarts_poll_timer(self):
        import time as time_module
        from accounts.views import POLL_SESSION_KEY
        self._register()
        session = self.client.session
        session[POLL_SESSION_KEY] = time_module.time() - 999
        session.save()
        self.client.get(reverse('accounts:verify_email_pending'))
        self.assertAlmostEqual(
            self.client.session[POLL_SESSION_KEY], time_module.time(), delta=5,
        )

    def test_resend_is_throttled(self):
        from django.core import mail
        self._register()
        self.client.post(reverse('accounts:resend_verification'))
        self.assertEqual(len(mail.outbox), 2)  # sign-up email + first resend
        self.client.post(reverse('accounts:resend_verification'))
        self.assertEqual(len(mail.outbox), 2)  # second resend inside cooldown: skipped

    def test_staff_never_gated(self):
        CustomUser.objects.create_user(
            username='sec-unverified', password='x', role='secretary', email_verified=False,
        )
        self.client.login(username='sec-unverified', password='x')
        response = self.client.get('/secretary/')
        self.assertNotEqual(
            response.headers.get('Location'), reverse('accounts:verify_email_pending'),
        )

    def test_superuser_never_gated(self):
        CustomUser.objects.create_superuser(username='root', password='x', email='root@example.com')
        self.client.login(username='root', password='x')
        response = self.client.get('/django-admin/')
        self.assertNotEqual(
            response.headers.get('Location'), reverse('accounts:verify_email_pending'),
        )


@override_settings(**GOOGLE_CONFIGURED)
class BookingProfileGateTests(SocialLoginTestBase):
    """A Google-created patient has an empty profile; booking must bounce
    them to profile edit until address and place of birth are filled in."""

    def setUp(self):
        super().setUp()
        self._callback()  # logs in a freshly created social patient
        self.user = self._logged_in_user()
        # These tests target the profile-completeness gate, so get the
        # email-confirmation gate out of the way (as if the link was clicked).
        self.user.email_verified = True
        self.user.save(update_fields=['email_verified'])

    def test_booking_first_step_blocked_until_profile_completed(self):
        response = self.client.get(reverse('patient:book_step1'))
        self.assertRedirects(response, reverse('accounts:profile_edit'))

        profile = self.user.patient_profile
        profile.address = '123 Mabini St., Quezon City'
        profile.place_of_birth = 'Quezon City'
        profile.save()

        response = self.client.get(reverse('patient:book_step1'))
        self.assertEqual(response.status_code, 200)

    def test_final_confirm_post_backstop_blocked(self):
        response = self.client.post(reverse('patient:book_confirm'), {
            'doctor_id': '999', 'appointment_date': '2030-01-01',
        })
        self.assertRedirects(response, reverse('accounts:profile_edit'))
