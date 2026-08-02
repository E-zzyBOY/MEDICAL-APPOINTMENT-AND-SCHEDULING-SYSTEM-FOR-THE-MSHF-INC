from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Count, Avg, Q
from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.urls import reverse
from datetime import date, timedelta
from accounts.decorators import role_required
from accounts.models import CustomUser, PatientProfile, DoctorProfile, SecretaryProfile
from accounts.forms import DoctorCreationForm, SecretaryCreationForm, UserEditForm
from appointments.models import Appointment, TIME_NULLS_FIRST
from appointments.forms import AdminAppointmentEditForm
from feedback.models import Feedback
from notifications.forms import BroadcastForm
from notifications.models import Broadcast
from notifications.broadcast import send_broadcast
from notifications.email_utils import send_account_created_email, send_reminder_email
from notifications.models import Notification


def _parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_admin_dashboard_data(request):
    total_patients    = CustomUser.objects.filter(role='patient').count()
    total_doctors     = CustomUser.objects.filter(role='doctor').count()
    total_secretaries = CustomUser.objects.filter(role='secretary').count()
    total_appts       = Appointment.objects.count()
    today_appts       = Appointment.objects.filter(
        appointment_date=date.today(), status__in=['Pending Assignment', 'Scheduled', 'Confirmed', 'Rescheduled']
    ).count()
    avg_rating        = Feedback.objects.aggregate(avg=Avg('rating'))['avg']
    recent_appts      = Appointment.objects.select_related('patient', 'doctor').order_by('-created_at')[:10]

    trend_start = date.today() - timedelta(days=29)
    counts_by_date = {
        row['appointment_date']: row['c']
        for row in Appointment.objects.filter(
            appointment_date__gte=trend_start, appointment_date__lte=date.today(),
        ).exclude(
            status='Pending Assignment'
        ).values('appointment_date').annotate(c=Count('id'))
    }
    trend = [
        {'date': (trend_start + timedelta(days=i)).isoformat(),
         'value': counts_by_date.get(trend_start + timedelta(days=i), 0)}
        for i in range(30)
    ]

    # ── System-wide analytics (admin-only view) ──
    status_order = ['Pending Assignment', 'Scheduled', 'Confirmed', 'Rescheduled',
                    'Pending Reschedule', 'Completed', 'Cancelled', 'No-Show']
    status_counts = {
        row['status']: row['c']
        for row in Appointment.objects.values('status').annotate(c=Count('id'))
    }
    status_breakdown = [
        {'label': s, 'value': status_counts[s]}
        for s in status_order if status_counts.get(s)
    ]

    doctor_load = [
        {'label': f"Dr. {row['doctor__first_name']} {row['doctor__last_name']}".strip(),
         'value': row['c']}
        for row in Appointment.objects.exclude(status='Cancelled').values(
            'doctor__first_name', 'doctor__last_name'
        ).annotate(c=Count('id')).order_by('-c')[:7]
    ]

    rating_counts = {
        row['rating']: row['c']
        for row in Feedback.objects.values('rating').annotate(c=Count('id'))
    }
    rating_dist = [
        {'label': f'{i} star{"s" if i > 1 else ""}', 'value': rating_counts.get(i, 0)}
        for i in range(1, 6)
    ]

    new_patients_30 = CustomUser.objects.filter(
        role='patient', date_joined__date__gte=trend_start
    ).count()

    return {
        'userName': request.user.get_full_name() or request.user.username,
        'stats': [
            {'label': 'Patients', 'value': total_patients},
            {'label': 'Doctors', 'value': total_doctors},
            {'label': 'Secretaries', 'value': total_secretaries},
            {'label': 'Total Appointments', 'value': total_appts},
            {'label': "Today's Appointments", 'value': today_appts},
            {'label': 'New Patients', 'value': new_patients_30, 'hint': 'last 30 days'},
            {'label': 'Average Rating', 'value': round(avg_rating, 1) if avg_rating else None, 'hint': 'out of 5'},
        ],
        'trend': trend,
        'trendLabel': 'Appointments',
        'statusBreakdown': status_breakdown,
        'doctorLoad': doctor_load,
        'ratingDist': rating_dist,
        'appointmentsTitle': 'Recent Appointments',
        'appointmentsHref': '/admin-panel/appointments/',
        'appointments': [
            {
                'primary': a.patient.get_full_name(),
                'secondary': f'Dr. {a.doctor.get_full_name()}',
                'date': a.appointment_date.isoformat(),
                'time': a.appointment_time.strftime('%H:%M') if a.appointment_time else None,
                'status': a.status,
            }
            for a in recent_appts
        ],
        'quickActions': [
            {'title': '+ Doctor', 'href': '/admin-panel/users/create/?role=doctor'},
            {'title': '+ Secretary', 'href': '/admin-panel/users/create/?role=secretary'},
            {'title': 'View Appointments', 'href': '/admin-panel/appointments/'},
            {'title': 'View Feedback', 'href': '/admin-panel/feedback/'},
        ],
    }


@role_required('admin')
def admin_dashboard(request):
    dashboard_data = _build_admin_dashboard_data(request)
    return render(request, 'admin_panel/dashboard.html', {'dashboard_data': dashboard_data})


@role_required('admin')
def admin_dashboard_data(request):
    return JsonResponse(_build_admin_dashboard_data(request))


@role_required('admin')
def user_list(request):
    role_filter = request.GET.get('role', '')
    search      = request.GET.get('q', '')
    users = CustomUser.objects.exclude(role='admin')
    if role_filter:
        users = users.filter(role=role_filter)
    if search:
        # Apply the search as an OR *within* the already role-filtered
        # queryset (via Q objects), instead of rebuilding fresh querysets
        # per field — the old version only re-applied exclude(role='admin')
        # on the 2nd/3rd clauses, silently dropping any role_filter.
        users = users.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(username__icontains=search)
        )
        users = users.distinct().order_by('role', 'last_name')

    # Doctors/secretaries are bounded by hospital headcount (never large),
    # so they're rendered in full. Patients are the one list that can grow
    # without bound, so that's the one paginated ("Load more" via htmx,
    # same pattern as doctor_patient_records).
    staff_users = [u for u in users if u.role in ('doctor', 'secretary')]
    # Explicit ordering here (unlike the unfiltered `users` above) because a
    # sliced/paginated queryset needs a stable order across "Load more"
    # requests — without one, the DB isn't guaranteed to return rows in the
    # same order twice, which could skip or repeat patients between pages.
    patient_qs  = users.filter(role='patient').order_by('last_name', 'first_name')

    limit = _parse_int(request.GET.get('limit'), 20)
    total_patients = patient_qs.count()
    patient_users  = list(patient_qs[:limit])
    has_more       = total_patients > limit
    load_more_url  = None
    if has_more:
        params = request.GET.copy()
        params['limit'] = str(limit + 20)
        params['partial'] = 'patients'
        load_more_url = reverse('admin_panel:user_list') + '?' + params.urlencode()

    context = {
        'users': users,
        'staff_users': staff_users,
        'patient_users': patient_users,
        'patient_has_more': has_more,
        'patient_load_more_url': load_more_url,
        'role_filter': role_filter, 'search': search,
    }
    if request.htmx and request.GET.get('partial') == 'patients':
        return render(request, 'admin_panel/_patient_users_list.html', context)
    return render(request, 'admin_panel/user_list.html', context)


@role_required('admin')
def user_detail(request, pk):
    from accounts.views import _get_profile
    detail_user = get_object_or_404(CustomUser, pk=pk)
    profile = _get_profile(detail_user)
    return render(request, 'admin_panel/_user_detail_modal.html', {
        'detail_user': detail_user, 'profile': profile, 'title': 'User Details',
    })


@role_required('admin')
def user_create(request):
    role = request.GET.get('role', 'doctor')
    FormClass = DoctorCreationForm if role == 'doctor' else SecretaryCreationForm
    form = FormClass(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        try:
            send_account_created_email(user, form.cleaned_data['password1'])
        except Exception:
            pass
        messages.success(request, f'{user.get_full_name()} ({user.role}) account created.')
        if request.htmx:
            response = render(request, 'admin_panel/_user_create_modal.html', {'form': form, 'role': role})
            response['HX-Redirect'] = '/admin-panel/users/'
            return response
        return redirect('admin_panel:user_list')
    if request.htmx:
        return render(request, 'admin_panel/_user_create_modal.html', {'form': form, 'role': role})
    return render(request, 'admin_panel/user_create.html', {'form': form, 'role': role})


@role_required('admin')
def user_edit(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    form = UserEditForm(request.POST or None, instance=user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'User updated.')
        if request.htmx:
            response = render(request, 'admin_panel/_user_edit_modal.html', {'form': form, 'edited_user': user})
            response['HX-Redirect'] = '/admin-panel/users/'
            return response
        return redirect('admin_panel:user_list')
    if request.htmx:
        return render(request, 'admin_panel/_user_edit_modal.html', {'form': form, 'edited_user': user})
    return render(request, 'admin_panel/user_edit.html', {'form': form, 'edited_user': user})


@role_required('admin')
def user_toggle_active(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if request.method == 'POST':
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        status = 'activated' if user.is_active else 'deactivated'
        messages.success(request, f'{user.get_full_name()} {status}.')
        if request.htmx:
            response = HttpResponse('')
            response['HX-Redirect'] = '/admin-panel/users/'
            return response
        return redirect('admin_panel:user_list')
    return HttpResponseNotAllowed(['POST'])


@role_required('admin')
def user_delete(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if request.method == 'POST':
        name = user.get_full_name()
        user.delete()
        messages.success(request, f'User {name} deleted.')
        if request.htmx:
            # Don't re-render _user_delete_modal.html here: it builds a URL
            # from edited_user.pk, but Django sets pk to None on an instance
            # right after .delete() succeeds, which would throw a
            # NoReverseMatch. HX-Redirect makes htmx navigate away
            # immediately anyway, so the response body just needs to be
            # valid HTML — its content is never shown to the user.
            response = HttpResponse('')
            response['HX-Redirect'] = '/admin-panel/users/'
            return response
        return redirect('admin_panel:user_list')
    if request.htmx:
        return render(request, 'admin_panel/_user_delete_modal.html', {'edited_user': user})
    return render(request, 'admin_panel/user_confirm_delete.html', {'edited_user': user})


@role_required('admin')
def admin_appointment_list(request):
    qs = Appointment.objects.all().select_related('patient', 'doctor', 'secretary', 'patient_details').order_by('-appointment_date', TIME_NULLS_FIRST)
    today = date.today()
    # "Scheduled" bucket covers every appointment that hasn't finished or
    # been cancelled yet (Pending Assignment, Scheduled, Confirmed,
    # Rescheduled, Pending Reschedule) — mirrors the patient-facing
    # "Upcoming" tab. Past-dated rows move to "Past" instead of
    # lingering here indefinitely.
    buckets = {
        'scheduled': qs.exclude(status__in=['Completed', 'Cancelled']).filter(appointment_date__gte=today),
        'past': qs.exclude(status__in=['Completed', 'Cancelled']).filter(appointment_date__lt=today),
        'completed': qs.filter(status='Completed'),
        'cancelled': qs.filter(status='Cancelled'),
    }

    # Each tab is paginated independently ("Load more" via htmx, same
    # pattern as doctor_patient_records) since these lists grow without
    # bound over the life of the hospital and previously rendered every
    # row unpaginated.
    context = {}
    for name, bucket_qs in buckets.items():
        limit = _parse_int(request.GET.get(f'limit_{name}'), 10)
        total = bucket_qs.count()
        items = list(bucket_qs[:limit])
        has_more = total > limit
        load_more_url = None
        if has_more:
            params = request.GET.copy()
            params[f'limit_{name}'] = str(limit + 10)
            params['tab'] = name
            load_more_url = reverse('admin_panel:appointment_list') + '?' + params.urlencode()
        context[name] = items
        context[f'{name}_has_more'] = has_more
        context[f'{name}_load_more_url'] = load_more_url

    if request.htmx:
        tab = request.GET.get('tab')
        if tab in buckets:
            return render(request, 'admin_panel/_appointment_tab_list.html', {
                'tab': tab,
                'appts': context[tab],
                'has_more': context[f'{tab}_has_more'],
                'load_more_url': context[f'{tab}_load_more_url'],
            })
    return render(request, 'admin_panel/appointment_list.html', context)


@role_required('admin')
def admin_appointment_detail(request, pk):
    appt = get_object_or_404(Appointment.objects.select_related('patient', 'doctor', 'secretary', 'patient_details'), pk=pk)
    return render(request, 'admin_panel/_appointment_detail_modal.html', {
        'appt': appt, 'title': 'Appointment Details',
    })


@role_required('admin')
def admin_resend_reminder(request, pk):
    """Lets an admin manually re-send the day-before reminder email to the
    patient on demand, instead of only ever firing automatically from the
    send_appointment_reminders cron job."""
    appt = get_object_or_404(Appointment, pk=pk)
    if request.method == 'POST':
        if not appt.can_resend_reminder:
            messages.error(request, 'Reminders can only be resent for upcoming scheduled appointments.')
        else:
            try:
                send_reminder_email(appt)
            except Exception:
                pass
            Notification.objects.create(
                user=appt.patient,
                message=f"Reminder: your appointment reminder for "
                        f"{appt.appointment_date.strftime('%B %d, %Y')} was resent."
            )
            messages.success(request, 'Reminder email resent to the patient.')
        if request.htmx:
            response = HttpResponse('')
            response['HX-Redirect'] = request.META.get('HTTP_REFERER', '/admin-panel/appointments/')
            return response
        return redirect('admin_panel:appointment_list')
    return HttpResponseNotAllowed(['POST'])


@role_required('admin')
def admin_appointment_edit(request, pk):
    appt = get_object_or_404(Appointment, pk=pk)
    form = AdminAppointmentEditForm(request.POST or None, instance=appt)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Appointment updated.')
        if request.htmx:
            response = render(request, 'admin_panel/_appointment_edit_modal.html', {'form': form, 'appt': appt, 'title': 'Edit Appointment'})
            response['HX-Redirect'] = '/admin-panel/appointments/'
            return response
        return redirect('admin_panel:appointment_list')
    return render(request, 'admin_panel/_appointment_edit_modal.html', {
        'form': form, 'appt': appt, 'title': 'Edit Appointment',
    })


@role_required('admin')
def admin_feedback_list(request):
    doctors = CustomUser.objects.filter(
        role='doctor',
        doctor_appointments__feedback__isnull=False,
    ).annotate(
        avg_rating=Avg('doctor_appointments__feedback__rating'),
        review_count=Count('doctor_appointments__feedback'),
    ).select_related('doctor_profile').distinct()
    return render(request, 'admin_panel/feedback_list.html', {
        'doctors': doctors,
    })


@role_required('admin')
def admin_feedback_by_doctor(request, pk):
    doctor = get_object_or_404(CustomUser.objects.select_related('doctor_profile'), pk=pk, role='doctor')
    feedbacks = Feedback.objects.filter(
        appointment__doctor=doctor
    ).select_related('patient', 'appointment').order_by('-date_submitted')
    avg_rating = feedbacks.aggregate(avg=Avg('rating'))['avg']
    return render(request, 'admin_panel/feedback_by_doctor.html', {
        'doctor': doctor, 'feedbacks': feedbacks, 'avg_rating': avg_rating,
    })


@role_required('admin')
def admin_feedback_detail(request, pk):
    fb = get_object_or_404(Feedback.objects.select_related('patient', 'appointment', 'appointment__doctor'), pk=pk)
    return render(request, 'admin_panel/_feedback_detail_modal.html', {
        'fb': fb, 'title': 'Feedback Details',
    })


@role_required('admin')
def broadcast_list(request):
    form = BroadcastForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        broadcast = form.save(commit=False)
        broadcast.sender = request.user
        broadcast.save()
        send_broadcast(broadcast)
        messages.success(
            request,
            f'Announcement sent to {broadcast.recipient_count} user(s) '
            f'({broadcast.email_sent_count} email(s) delivered).'
        )
        return redirect('admin_panel:broadcast_list')
    history = Broadcast.objects.select_related('sender').all()[:20]
    return render(request, 'admin_panel/broadcast_list.html', {
        'form': form, 'history': history,
    })
